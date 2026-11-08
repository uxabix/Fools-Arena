"""Messaging rules and permission checks for the chat application.

This module centralizes direct-message blocking using ``accounts.Block``
and validation before messages are stored or broadcast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from accounts.models import Block

if TYPE_CHECKING:
    from game.models import Lobby


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
    :class:`~game.models.LobbyPlayer` is a :class:`~chat.models.ChatParticipant`.

    Args:
        lobby: :class:`~game.models.Lobby` instance.

    Returns:
        Chat: The canonical lobby chat for this lobby.
    """
    from game.models import LobbyPlayer

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
