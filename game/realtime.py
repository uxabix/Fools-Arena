"""Synchronous helpers that publish JSON events to Django Channels groups.

Consumers subscribe to ``lobby_{uuid}`` and ``game_{uuid}``; these helpers use
``group_send`` with type ``game.event`` so :class:`game.consumers.LobbyConsumer`
and :class:`game.consumers.GameConsumer` can relay payloads to browsers.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _send_group(group: str, message: dict):
    """Deliver ``message`` to every socket in ``group``.

    Args:
        group: Channel layer group name (e.g. ``lobby_<uuid>``).
        message: JSON-serializable dict forwarded to clients.

    Returns:
        None: No-op when the channel layer is not configured.
    """
    layer = get_channel_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        group,
        {
            "type": "game.event",
            "message": message,
        },
    )


def broadcast_lobby(lobby_id, event: str, payload: dict | None = None):
    """Notify every subscriber of a lobby room.

    Args:
        lobby_id: UUID of the :class:`~game.models.Lobby`.
        event: Short event name (e.g. ``player_joined``).
        payload: Optional extra fields merged into the outbound message.
    """
    _send_group(
        f"lobby_{lobby_id}",
        {"event": event, "payload": payload or {}},
    )


def broadcast_game(game_id, event: str, payload: dict | None = None):
    """Notify every subscriber of a running table.

    Args:
        game_id: UUID of the :class:`~game.models.Game`.
        event: Short event name (e.g. ``\"game_update\"``).
        payload: Optional extra fields for clients.
    """
    _send_group(
        f"game_{game_id}",
        {"event": event, "payload": payload or {}},
    )
