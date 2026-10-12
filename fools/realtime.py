"""Synchronous helpers that publish JSON events to Django Channels groups.

Consumers subscribe to ``lobby_{uuid}`` and ``game_{uuid}``; these helpers use
``group_send`` with type ``fools.event`` so :class:`fools.consumers.LobbyConsumer`
and :class:`fools.consumers.GameConsumer` can relay payloads to browsers.
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
            "type": "fools.event",
            "message": message,
        },
    )


def broadcast_lobby_list(event: str, payload: dict | None = None):
    """Notify browsers that are watching the public lobby list.

    The group is ``lobby_list``. Payloads are public waiting lobbies only;
    callers omit private rooms.

    Args:
        event: ``lobby_upsert`` or ``lobby_removed``.
        payload: Lobby snapshot, or ``{"id": ...}`` when a row should go.
    """
    _send_group("lobby_list", {"event": event, "payload": payload or {}})


def broadcast_lobby(lobby_id, event: str, payload: dict | None = None):
    """Notify every subscriber of a lobby room.

    Args:
        lobby_id: UUID of the :class:`~fools.models.Lobby`.
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
        game_id: UUID of the :class:`~fools.models.Game`.
        event: Short event name (e.g. ``\"game_update\"``).
        payload: Optional extra fields for clients.
    """
    _send_group(
        f"game_{game_id}",
        {"event": event, "payload": payload or {}},
    )
