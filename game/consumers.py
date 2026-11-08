"""Async Channels consumers for lobby and per-game WebSocket channels.

Clients connect with session authentication (see ``AuthMiddlewareStack``). Each
connection joins a single group and receives ``game.event`` fan-out messages
originating from :mod:`game.realtime`.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from game.models import Game, LobbyPlayer


@database_sync_to_async
def user_in_lobby(user_id, lobby_id):
    """Return whether the user has a non-left membership in the lobby.

    Args:
        user_id: Primary key of :class:`~django.contrib.auth.models.User`.
        lobby_id: Lobby UUID string or UUID.

    Returns:
        True if an active :class:`~game.models.LobbyPlayer` row exists.
    """
    return LobbyPlayer.objects.filter(
        lobby_id=lobby_id, user_id=user_id
    ).exclude(status="left").exists()


@database_sync_to_async
def user_in_game(user_id, game_id):
    """Return whether the user participates in the given game.

    Args:
        user_id: User primary key.
        game_id: Game UUID.

    Returns:
        True if a :class:`~game.models.GamePlayer` row links the pair.
    """
    return Game.objects.filter(id=game_id, players__user_id=user_id).exists()


class LobbyConsumer(AsyncJsonWebsocketConsumer):
    """Stream lobby-scoped events (chat, membership, game start) to members."""

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

    async def game_event(self, event):
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

    async def disconnect(self, code):
        """Detach from the game broadcast group."""
        await self.channel_layer.group_discard(f"game_{self.game_id}", self.channel_name)

    async def game_event(self, event):
        """Push server events (moves, phase changes) to the client."""
        await self.send_json(event["message"])
