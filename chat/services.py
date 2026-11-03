"""Messaging rules and permission checks for the chat application.

This module centralizes direct-message blocking using ``accounts.Block``
and validation before messages are stored or broadcast.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import Block

if TYPE_CHECKING:
    from fools.models import Lobby

logger = logging.getLogger(__name__)

HISTORY_PAGE = 40
HISTORY_MAX = 50
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def is_direct_message_blocked(sender, recipient):
    """Return True if ``recipient`` has blocked ``sender`` (sender cannot DM).

    Args:
        sender: User attempting to send a message.
        recipient: The other party in a direct chat.

    Returns:
        bool: True when a block prevents ``sender`` from messaging ``recipient``.
    """
    if sender.pk == recipient.pk:
        return False
    return Block.objects.filter(blocker=recipient, blocked=sender).exists()


def get_lobby_chat(lobby: Lobby):
    """Return the lobby-linked :class:`~chat.models.Chat`, syncing active players.

    Creates ``is_lobby=True`` chat on first use and ensures every non-left
    :class:`~fools.models.LobbyPlayer` is a :class:`~chat.models.ChatParticipant`.

    Args:
        lobby: :class:`~fools.models.Lobby` instance.

    Returns:
        Chat: The canonical lobby chat for this lobby.
    """
    from fools.models import LobbyPlayer

    from .models import Chat

    chat = (
        Chat.objects.filter(lobby=lobby, is_lobby=True).order_by("created_at").first()
    )
    if chat is None:
        chat = Chat.objects.create(
            lobby=lobby,
            is_lobby=True,
            is_group=True,
            name=(lobby.name or "Lobby chat")[:100],
        )
    for lp in LobbyPlayer.objects.filter(lobby=lobby).exclude(status="left"):
        chat.add_participant(lp.user)
    return chat


def remove_user_from_lobby_chat(lobby: Lobby, user):
    """Drop ``user`` from the lobby chat when they leave the lobby table.

    Args:
        lobby: Lobby the user left.
        user: Participant to remove from the linked chat (if any).
    """
    from .models import Chat

    chat = Chat.objects.filter(lobby=lobby, is_lobby=True).first()
    if chat:
        chat.remove_participant(user)


def message_public(message) -> dict:
    """JSON fields shared by the chat API, the lobby API, and WebSocket fans.

    Args:
        message: Stored chat line. ``sender`` is read for the display name.

    Returns:
        Dict with string ids, both ``sender`` and ``username``, ``kind``,
        and an ISO timestamp.
    """
    username = message.sender.username
    return {
        "id": str(message.id),
        "sender_id": str(message.sender_id),
        "sender": username,
        "username": username,
        "content": message.content,
        "sent_at": message.sent_at.isoformat(),
        "kind": message.kind,
    }


def message_payload(message) -> dict:
    """JSON fields the lobby chat sends to browsers.

    Args:
        message: Stored chat line. ``sender`` is read for the display name.

    Returns:
        Dict with string ids, ``kind``, and an ISO timestamp.
    """
    return message_public(message)


def broadcast_chat_message(message):
    """Publish one stored line to the ``chat_<id>`` channel group.

    The HTTP create path and the WebSocket receive path both call this so a
    connected browser sees the same payload. A channel-layer failure is logged
    and does not remove the row that was already saved.

    Args:
        message: Stored :class:`~chat.models.Message`. ``sender`` must be loaded.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if not layer:
        return
    try:
        async_to_sync(layer.group_send)(
            f"chat_{message.chat_id}",
            {"type": "chat_message", "message": message_public(message)},
        )
    except Exception:
        logger.warning(
            "Chat broadcast failed chat=%s message=%s",
            message.chat_id,
            message.pk,
            exc_info=True,
        )


def format_chat_time(value):
    """Format a chat timestamp the same way the thread script does.

    Today is ``HH:MM``. Older moments in this year add ``Mon D``. A different
    year adds the year. The clock is 24-hour local time.

    Args:
        value: Aware datetime, or None.

    Returns:
        str: Display label, or an empty string when ``value`` is missing.
    """
    if not value:
        return ""
    local = timezone.localtime(value)
    now = timezone.localtime()
    clock = local.strftime("%H:%M")
    if local.date() == now.date():
        return clock
    stamp = f"{_MONTHS[local.month - 1]} {local.day}"
    if local.year != now.year:
        stamp = f"{stamp}, {local.year}"
    return f"{stamp} {clock}"


def preview_text(content, limit=90):
    """Collapse whitespace and shorten a message for the inbox row.

    Args:
        content (str): Raw message body.
        limit (int): Maximum characters, including the ellipsis.

    Returns:
        str: Single-line preview.
    """
    text = " ".join((content or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def unread_badge_label(count):
    """Return the short badge text for an unread total.

    Args:
        count (int): Unread messages.

    Returns:
        str: Empty when there is nothing to show, otherwise the number or ``99+``.
    """
    count = int(count or 0)
    if count <= 0:
        return ""
    if count > 99:
        return "99+"
    return str(count)


def page_limit(raw, default=HISTORY_PAGE):
    """Clamp a history page size to the allowed range.

    Args:
        raw: Query value, or None to use ``default``.
        default (int): Size used when ``raw`` is missing or not an integer.

    Returns:
        int: A page size from 1 through :data:`HISTORY_MAX`.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, HISTORY_MAX))


def parse_message_id(raw):
    """Parse an optional message id query or body field.

    Args:
        raw: Incoming value.

    Returns:
        uuid.UUID | None: None when ``raw`` is empty.

    Raises:
        ValueError: When ``raw`` is present but not a UUID.
    """
    if raw in (None, ""):
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid message id.") from exc


def message_page(chat, *, before_id=None, limit=HISTORY_PAGE, text=None):
    """Return one chronological page of messages, newest page first.

    Args:
        chat: Chat whose messages are listed.
        before_id: When set, return messages older than this row.
        limit (int): Maximum rows in the page.
        text: When set, keep lines whose content contains this text.

    Returns:
        tuple[list, bool]: Messages from oldest to newest, and whether an
        older page exists. An unknown ``before_id`` yields an empty page.
    """
    from .models import Message

    limit = page_limit(limit)
    qs = (
        Message.objects.filter(chat=chat)
        .select_related("sender")
        .order_by("-sent_at", "-pk")
    )
    needle = " ".join((text or "").split())[:80]
    if needle:
        qs = qs.filter(content__icontains=needle)
    if before_id:
        anchor = (
            Message.objects.filter(pk=before_id, chat=chat)
            .only("sent_at", "pk")
            .first()
        )
        if anchor is None:
            return [], False
        qs = qs.filter(
            Q(sent_at__lt=anchor.sent_at) | Q(sent_at=anchor.sent_at, pk__lt=anchor.pk)
        )
    rows = list(qs[: limit + 1])
    has_older = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()
    return rows, has_older


def mark_chat_read(chat, user, *, at=None):
    """Move this member's read mark forward.

    The mark never moves backward. Passing a message time marks everything
    up to that message and leaves anything newer unread.

    Args:
        chat: Chat the user belongs to.
        user: Reader.
        at: Aware datetime to store. Defaults to now.

    Returns:
        ChatParticipant | None: Updated row, or None when the user is not a member.
    """
    from .models import ChatParticipant

    participant = ChatParticipant.objects.filter(chat=chat, user=user).first()
    if participant is None:
        return None
    moment = at or timezone.now()
    if participant.last_read_at and participant.last_read_at >= moment:
        return participant
    participant.last_read_at = moment
    participant.save(update_fields=["last_read_at"])
    return participant


def _unread_count_subquery(user):
    """Count other people's messages newer than this user's read mark."""
    from .models import ChatParticipant, Message

    read_at = ChatParticipant.objects.filter(
        chat_id=OuterRef("chat_id"),
        user_id=user.pk,
    ).values("last_read_at")[:1]
    return (
        Message.objects.filter(chat_id=OuterRef("pk"))
        .exclude(sender_id=user.pk)
        .annotate(_read_at=Subquery(read_at))
        .filter(Q(_read_at__isnull=True) | Q(sent_at__gt=F("_read_at")))
        .order_by()
        .values("chat_id")
        .annotate(_c=Count("pk"))
        .values("_c")[:1]
    )


def chats_for_viewer(user):
    """Return the user's chats, newest activity first.

    Empty chats sort after chats that have messages. Each row is annotated
    with the latest message preview fields and ``unread_count``.

    Args:
        user: Authenticated user.

    Returns:
        QuerySet[Chat]: Annotated chats for inbox and the list API.
    """
    from .models import Chat, Message

    last = Message.objects.filter(chat_id=OuterRef("pk")).order_by("-sent_at", "-pk")
    return (
        Chat.objects.filter(chatparticipant__user=user)
        .annotate(
            last_sent_at=Subquery(last.values("sent_at")[:1]),
            last_content=Subquery(last.values("content")[:1]),
            last_sender_id=Subquery(last.values("sender_id")[:1]),
            last_sender_name=Subquery(last.values("sender__username")[:1]),
            last_kind=Subquery(last.values("kind")[:1]),
            unread_count=Coalesce(
                Subquery(_unread_count_subquery(user), output_field=IntegerField()),
                Value(0),
            ),
        )
        .order_by(F("last_sent_at").desc(nulls_last=True), "-created_at")
    )


CHAT_FOLDERS = ("all", "direct", "lobby", "game")
CHAT_SORTS = ("activity", "unread", "name")


def chat_list_params(request):
    """Read the inbox tab, search, unread filter, and sort from the query string.

    Unknown values fall back to the defaults. The search text is capped at
    80 characters. This does not search inside message bodies.

    Args:
        request: HTTP request.

    Returns:
        dict: ``tab``, ``sort``, ``q``, and ``unread``.
    """
    tab = request.GET.get("tab") or "all"
    if tab not in CHAT_FOLDERS:
        tab = "all"
    sort = request.GET.get("sort") or "activity"
    if sort not in CHAT_SORTS:
        sort = "activity"
    query = " ".join((request.GET.get("q") or "").split())[:80]
    return {
        "tab": tab,
        "sort": sort,
        "q": query,
        "unread": request.GET.get("unread") == "1",
    }


def chat_querystring(params, **overrides):
    """Build a query string, omitting default tab, sort, and empty search.

    Args:
        params (dict): Current list parameters.
        **overrides: Keys to replace before encoding.

    Returns:
        str: Query string without a leading ``?``, or an empty string.
    """
    from urllib.parse import urlencode

    data = dict(params)
    data.update(overrides)
    pairs = []
    if data.get("tab") not in (None, "", "all"):
        pairs.append(("tab", data["tab"]))
    if data.get("q"):
        pairs.append(("q", data["q"]))
    if data.get("unread"):
        pairs.append(("unread", "1"))
    if data.get("sort") not in (None, "", "activity"):
        pairs.append(("sort", data["sort"]))
    return urlencode(pairs)


def chat_folder(chat):
    """Return which inbox tab a chat belongs to.

    A lobby chat stays in ``lobby`` until that lobby's status is ``playing``.
    The table uses the same chat, so a match does not create a second room.
    Anything that is not a direct message or a lobby chat is ``other`` and
    appears only on the All tab.

    Args:
        chat: Chat instance. ``lobby`` should be loaded when ``is_lobby`` is set.

    Returns:
        str: ``direct``, ``lobby``, ``game``, or ``other``.
    """
    if chat.is_direct_message():
        return "direct"
    if chat.is_lobby:
        status = ""
        lobby = getattr(chat, "lobby", None)
        if lobby is not None:
            status = lobby.status or ""
        return "game" if status == "playing" else "lobby"
    return "other"


def chat_title(chat, viewer):
    """Return the name shown for a chat row or thread header.

    Direct chats use the other player's username. Lobby chats use the lobby
    name stored on the chat.

    Args:
        chat: Chat instance.
        viewer: Current user.

    Returns:
        str: Human-readable title.
    """
    if chat.is_lobby:
        return chat.name or "Lobby chat"
    if chat.is_global:
        return chat.name or "Global chat"
    if chat.is_direct_message():
        other = chat.get_other_participant(viewer)
        if other:
            return other.get_username()
        return "Direct message"
    if chat.is_group:
        return chat.name or "Group chat"
    return chat.name or str(chat.pk)


def visible_chats(user, params):
    """Return this user's chats after the inbox tab, search, and sort.

    Search matches the chat name and other participants' usernames. It does
    not scan message text. Unread keeps chats with ``unread_count`` above zero.

    Args:
        user: Authenticated user.
        params (dict): Result of :func:`chat_list_params`.

    Returns:
        list[Chat]: Filtered chats in the requested order.
    """
    from django.db.models import Prefetch

    from .models import ChatParticipant

    chats = list(
        chats_for_viewer(user)
        .select_related("lobby")
        .prefetch_related(
            Prefetch(
                "chatparticipant_set",
                queryset=ChatParticipant.objects.select_related("user"),
            )
        )
    )
    query = (params.get("q") or "").casefold()
    folder = params.get("tab") or "all"
    unread_only = bool(params.get("unread"))
    kept = []
    for chat in chats:
        kind = chat_folder(chat)
        if folder != "all" and kind != folder:
            continue
        if unread_only and int(chat.unread_count or 0) <= 0:
            continue
        if query:
            names = [chat.name or "", chat_title(chat, user)]
            cached = getattr(chat, "_prefetched_objects_cache", {}).get("chatparticipant_set") or []
            for row in cached:
                if row.user_id != user.pk and not getattr(row.user, "is_bot", False):
                    names.append(row.user.username or "")
            if not any(query in name.casefold() for name in names if name):
                continue
        kept.append(chat)

    sort = params.get("sort") or "activity"
    if sort == "unread":
        kept.sort(key=lambda chat: (-int(chat.unread_count or 0), _activity_key(chat)))
    elif sort == "name":
        kept.sort(key=lambda chat: chat_title(chat, user).casefold())
    else:
        kept.sort(key=_activity_key)
    return kept


def _activity_key(chat):
    """Sort newest activity first, with empty chats after chats that have messages."""
    if chat.last_sent_at:
        return (0, -chat.last_sent_at.timestamp())
    created = chat.created_at.timestamp() if chat.created_at else 0
    return (1, -created)


def unread_message_count(user):
    """Return how many messages this user has not caught up with.

    Args:
        user: Authenticated user.

    Returns:
        int: Sum of per-chat unread counts. Own messages are not included.
    """
    total = chats_for_viewer(user).aggregate(total=Sum("unread_count"))["total"]
    return int(total or 0)


def record_lobby_notice(lobby: Lobby, sender, content: str):
    """Store a system notice in the lobby chat.

    ``sender`` is the member who caused the notice. ``kind`` is ``system``,
    so clients do not show the line as that person typing in chat.

    Args:
        lobby: Lobby whose chat receives the line.
        sender: Member who caused the notice.
        content: Plain text already written for players.

    Returns:
        The created message.
    """
    from .models import Message

    chat = get_lobby_chat(lobby)
    return Message.objects.create(
        sender=sender,
        chat=chat,
        content=content,
        kind=Message.KIND_SYSTEM,
    )


def assert_can_send_message(chat, sender):
    """Raise ``PermissionError`` if ``sender`` may not post in ``chat``.

    Lobby and global channels ignore pairwise blocks so existing behaviour stays
    unchanged.

    Args:
        chat: Target ``Chat`` instance.
        sender: Authenticated user posting the message.

    Raises:
        PermissionError: If the direct counterpart has blocked the sender or the
            chat configuration is invalid for DM.
    """
    if not chat.is_direct_message():
        return

    other = chat.get_other_participant(sender)
    if other is None:
        raise PermissionError("Direct chat has no valid counterpart.")

    if is_direct_message_blocked(sender, other):
        raise PermissionError("You cannot send messages to this user.")
