"""Server-rendered views for chat (same behaviour as the REST API layer)."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ChatMessageForm, StartDirectChatForm
from .models import Chat, Message
from .services import assert_can_send_message

User = get_user_model()


def _chat_display_title(chat, viewer):
    """Return a short title for a chat row or room header.

    Args:
        chat (Chat): Chat instance.
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
            return f"DM — {other.get_username()}"
        return "Direct message"
    if chat.is_group:
        return chat.name or "Group chat"
    return chat.name or str(chat.pk)


@login_required
def chat_inbox(request):
    """Render the chat inbox for the signed-in user.

    Uses the same participant filter as the JSON list endpoint so template and
    API stay in sync.

    Args:
        request (HttpRequest): Current request; ``request.user`` must be
            authenticated (enforced by ``@login_required``).

    Returns:
        HttpResponse: Rendered ``chat/inbox.html`` with ``chat_rows``.
    """
    chat_list = (
        Chat.objects.filter(chatparticipant__user=request.user)
        .distinct()
        .order_by("-created_at")
    )
    rows = [
        {
            "chat": c,
            "title": _chat_display_title(c, request.user),
        }
        for c in chat_list
    ]
    return render(
        request,
        "chat/inbox.html",
        {
            "chat_rows": rows,
        },
    )


@login_required
def start_direct_chat(request):
    """Show the \"start direct chat\" form or process username submission.

    On success, redirects to the shared :func:`chat_room` for that DM.

    Args:
        request (HttpRequest): GET shows the form; POST expects
            ``other_username``.

    Returns:
        HttpResponse: Form page or redirect to the DM room.
    """
    if request.method == "POST":
        form = StartDirectChatForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["other_username"]
            if not name:
                messages.error(request, "Enter a username.")
                return render(
                    request,
                    "chat/start_direct.html",
                    {"form": StartDirectChatForm()},
                )

            other = User.objects.filter(username__iexact=name).first()
            if other is None:
                messages.error(request, "No user with that username.")
                return render(
                    request,
                    "chat/start_direct.html",
                    {"form": form},
                )

            if other.pk == request.user.pk:
                messages.error(request, "You cannot open a direct chat with yourself.")
                return render(
                    request,
                    "chat/start_direct.html",
                    {"form": StartDirectChatForm()},
                )

            chat, _created = Chat.objects.get_or_create_direct(request.user, other)
            return redirect("chat:room", chat_id=chat.pk)

    form = StartDirectChatForm()
    return render(request, "chat/start_direct.html", {"form": form})


@login_required
def chat_room(request, chat_id):
    """Display chronological messages and accept HTTP POST for new lines.

    Live updates use the same Channels consumer as API/WebSocket clients.

    Args:
        request (HttpRequest): GET loads history; POST validates and saves.
        chat_id (uuid.UUID): Primary key of the :class:`~chat.models.Chat`.

    Returns:
        HttpResponse: Room template, redirect after successful send, or redirect
            away if the user is not a participant.
    """
    chat = get_object_or_404(Chat, pk=chat_id)
    if not chat.has_participant(request.user):
        messages.error(request, "You are not a member of this chat.")
        return redirect("chat:inbox")

    if request.method == "POST":
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            try:
                assert_can_send_message(chat, request.user)
            except PermissionError as exc:
                messages.error(request, str(exc))
            else:
                Message.objects.create(
                    sender=request.user,
                    chat=chat,
                    content=form.cleaned_data["content"],
                )
                return redirect("chat:room", chat_id=chat.pk)
    else:
        form = ChatMessageForm()

    msg_list = list(
        Message.objects.filter(chat=chat).select_related("sender").order_by("sent_at")
    )
    return render(
        request,
        "chat/room.html",
        {
            "chat": chat,
            "title": _chat_display_title(chat, request.user),
            "messages_list": msg_list,
            "form": form,
            "ws_scheme": "wss" if request.is_secure() else "ws",
            "ws_host": request.get_host(),
        },
    )
