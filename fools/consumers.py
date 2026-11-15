"""Async Channels consumers for lobby and per-fools WebSocket channels.

Clients connect with session authentication (see ``AuthMiddlewareStack``). Each
connection joins a single group and receives ``fools.event`` fan-out messages
originating from :mod:`fools.realtime`.

The match socket also accepts a ``hand_signal`` action: a sort mode and the
indexes of lifted cards. Those tells are checked in :mod:`fools.hand_signals`
and relayed to the same group. Card identities are not part of that message.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from fools.hand_signals import accept_hand_signal, hand_signal_snapshot
from fools.models import Game, LobbyPlayer


@database_sync_to_async
def user_in_lobby(user_id, lobby_id):
    """Return whether the user has a non-left membership in the lobby.

    Args:
        user_id: Primary key of :class:`~django.contrib.auth.models.User`.
        lobby_id: Lobby UUID string or UUID.

    Returns:
        True if an active :class:`~fools.models.LobbyPlayer` row exists.
    """
    return LobbyPlayer.objects.filter(
        lobby_id=lobby_id, user_id=user_id
    ).exclude(status="left").exists()


@database_sync_to_async
def user_in_game(user_id, game_id):
    """Return whether the user participates in the given fools.

    Args:
        user_id: User primary key.
        game_id: Game UUID.

    Returns:
        True if a :class:`~fools.models.GamePlayer` row links the pair.
    """
    return Game.objects.filter(id=game_id, players__user_id=user_id).exists()


class LobbyListConsumer(AsyncJsonWebsocketConsumer):
    """Stream public lobby-list changes to any signed-in user.

    Unlike :class:`LobbyConsumer`, membership in a particular lobby is not
    required. Payloads are the same public snapshots as the list API.
    """

    async def connect(self):
        """Accept signed-in users onto the shared list group."""
        user = self.scope["user"]
        if isinstance(user, AnonymousUser) or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return
        await self.channel_layer.group_add("lobby_list", self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        """Leave the list group when the socket closes."""
        await self.channel_layer.group_discard("lobby_list", self.channel_name)

    async def fools_event(self, event):
        """Forward a list upsert or removal to the browser."""
        await self.send_json(event["message"])


class LobbyConsumer(AsyncJsonWebsocketConsumer):
    """Stream lobby-scoped events (chat, membership, fools start) to members."""

    async def connect(self):
        """Accept the socket after auth + membership checks."""
        self.lobby_id = str(self.scope["url_route"]["kwargs"]["lobby_id"])
        user = self.scope["user"]
        if isinstance(user, AnonymousUser):
            await self.close(code=4401)
            return
        if not await user_in_lobby(user.id, self.lobby_id):
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(f"lobby_{self.lobby_id}", self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        """Leave the lobby group when the socket closes."""
        await self.channel_layer.group_discard(f"lobby_{self.lobby_id}", self.channel_name)

    async def fools_event(self, event):
        """Forward channel-layer messages to the browser as JSON."""
        await self.send_json(event["message"])


class GameConsumer(AsyncJsonWebsocketConsumer):
    """Stream table updates to everyone seated in the same ``Game``."""

    async def connect(self):
        """Accept after verifying the user is one of the game's players."""
        self.game_id = str(self.scope["url_route"]["kwargs"]["game_id"])
        user = self.scope["user"]
        if isinstance(user, AnonymousUser):
            await self.close(code=4401)
            return
        if not await user_in_game(user.id, self.game_id):
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(f"game_{self.game_id}", self.channel_name)
        await self.accept()
        snapshot = await database_sync_to_async(hand_signal_snapshot)(self.game_id)
        if snapshot:
            await self.send_json({"event": "hand_signals", "payload": {"signals": snapshot}})

    async def disconnect(self, code):
        """Detach from the game broadcast group."""
        await self.channel_layer.group_discard(f"game_{self.game_id}", self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Relay a lifted-card or reorder tell when the lobby allows it.

        Args:
            content: Parsed client JSON. Only ``action`` ``hand_signal`` is
                handled. Any card identity in the object is ignored.
            **kwargs: Unused Channels arguments.
        """
        if not isinstance(content, dict) or content.get("action") != "hand_signal":
            return
        payload = await database_sync_to_async(accept_hand_signal)(
            self.game_id,
            self.scope["user"].id,
            content,
        )
        if payload is None:
            return
        await self.channel_layer.group_send(
            f"game_{self.game_id}",
            {
                "type": "fools.event",
                "message": {"event": "hand_signal", "payload": payload},
            },
        )

    async def fools_event(self, event):
        """Push server events (moves, phase changes, hand tells) to the client."""
        await self.send_json(event["message"])
