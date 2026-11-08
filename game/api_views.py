"""REST API for lobbies, gameplay, and lobby chat.

Gameplay delegates to :mod:`game.services`. Lobby-scoped lines use the shared
:class:`chat.models.Chat` (``is_lobby=True``, FK to :class:`game.models.Lobby`)
and :class:`chat.models.Message`; HTTP echoes are also pushed on the lobby
WebSocket group for the game UI.
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.models import Message
from chat.services import assert_can_send_message, get_lobby_chat
from game.models import Game, Lobby, LobbyPlayer
from game.realtime import broadcast_lobby
from game.serializers import (
    AttackSerializer,
    DefendSerializer,
    LobbyCreateSerializer,
    LobbyJoinSerializer,
    LobbyMessageSerializer,
    ReadySerializer,
)
from game.services import (
    GameError,
    bito,
    create_lobby,
    defend,
    join_lobby,
    leave_lobby,
    play_attack,
    seal_attack,
    serialize_game,
    serialize_lobby,
    set_ready,
    start_game,
    take_table,
)


def _err(e: GameError):
    """Map :class:`~game.services.GameError` to a DRF 400 response.

    Args:
        e: Domain error from the service layer.

    Returns:
        ``Response`` with ``detail`` and ``code`` keys.
    """
    return Response(
        {"detail": e.message, "code": e.code},
        status=status.HTTP_400_BAD_REQUEST,
    )


class LobbyListCreateAPI(APIView):
    """GET public waiting lobbies; POST creates a lobby for the current user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = (
            Lobby.objects.filter(status="waiting", is_private=False)
            .annotate(
                active_n=Count("players", filter=~Q(players__status="left")),
            )
            .filter(active_n__gt=0)
            .select_related("settings", "owner")
            .order_by("-created_at")
        )
        return Response([serialize_lobby(x) for x in qs])

    def post(self, request):
        ser = LobbyCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            lobby = create_lobby(
                request.user,
                d["name"],
                is_private=d["is_private"],
                password=d.get("password") or None,
                max_players=d["max_players"],
                card_count=d["card_count"],
                is_transferable=d["is_transferable"],
                neighbor_throw_only=d["neighbor_throw_only"],
                allow_jokers=d["allow_jokers"],
                turn_time_limit=d.get("turn_time_limit"),
            )
        except GameError as e:
            return _err(e)
        return Response(serialize_lobby(lobby), status=status.HTTP_201_CREATED)


class LobbyDetailAPI(APIView):
    """Retrieve a single lobby; private lobbies require membership (or ownership)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, lobby_id):
        lobby = get_object_or_404(Lobby, id=lobby_id)
        if lobby.is_private:
            if not lobby.players.filter(user=request.user).exclude(status="left").exists():
                if lobby.owner_id != request.user.id:
                    return Response(
                        {"detail": "Not a member of this private lobby"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
        return Response(serialize_lobby(lobby))


class LobbyJoinAPI(APIView):
    """Join (or idempotently re-enter) a lobby, optionally supplying a password."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, lobby_id):
        lobby = get_object_or_404(Lobby, id=lobby_id)
        if LobbyPlayer.objects.filter(lobby=lobby, user=request.user).exclude(
            status="left"
        ).exists():
            return Response(serialize_lobby(lobby))
        ser = LobbyJoinSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            join_lobby(lobby, request.user, ser.validated_data.get("password"))
        except GameError as e:
            return _err(e)
        return Response(serialize_lobby(lobby))


class LobbyLeaveAPI(APIView):
    """Mark the caller as left for this lobby."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, lobby_id):
        lobby = get_object_or_404(Lobby, id=lobby_id)
        try:
            info = leave_lobby(lobby, request.user)
        except GameError as e:
            return _err(e)
        return Response(
            {
                "detail": "left",
                "lobby_closed": info["lobby_closed"],
                "new_owner_id": info.get("new_owner_id"),
            }
        )


class LobbyReadyAPI(APIView):
    """Toggle the caller's waiting/ready flag."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, lobby_id):
        lobby = get_object_or_404(Lobby, id=lobby_id)
        ser = ReadySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            set_ready(lobby, request.user, ser.validated_data["ready"])
        except GameError as e:
            return _err(e)
        return Response(serialize_lobby(lobby))


class LobbyStartAPI(APIView):
    """Owner-only endpoint to deal the first hand and open the table."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, lobby_id):
        lobby = get_object_or_404(Lobby, id=lobby_id)
        try:
            game = start_game(lobby, request.user)
        except GameError as e:
            return _err(e)
        return Response(serialize_game(game, request.user), status=status.HTTP_201_CREATED)


class GameStateAPI(APIView):
    """Return masked game JSON for the authenticated participant."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not game.players.filter(user=request.user).exists():
            return Response(
                {"detail": "Not a player in this game"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(serialize_game(game, request.user))


class GameAttackAPI(APIView):
    """Attack or throw-in: play one or more cards from the actor's hand."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not game.players.filter(user=request.user).exists():
            return Response(status=status.HTTP_403_FORBIDDEN)
        ser = AttackSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            play_attack(game, request.user, ser.validated_data["card_ids"])
        except GameError as e:
            return _err(e)
        return Response(serialize_game(game, request.user))


class GameSealAPI(APIView):
    """Primary attacker closes the attack wave (move to defend phase)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not game.players.filter(user=request.user).exists():
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            seal_attack(game, request.user)
        except GameError as e:
            return _err(e)
        return Response(serialize_game(game, request.user))


class GameDefendAPI(APIView):
    """Defender beats a single table row with a chosen hand card."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not game.players.filter(user=request.user).exists():
            return Response(status=status.HTTP_403_FORBIDDEN)
        ser = DefendSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            defend(game, request.user, d["table_card_id"], d["card_id"])
        except GameError as e:
            return _err(e)
        return Response(serialize_game(game, request.user))


class GameTakeAPI(APIView):
    """Defender takes the whole table into hand and draws from stock."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not game.players.filter(user=request.user).exists():
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            take_table(game, request.user)
        except GameError as e:
            return _err(e)
        return Response(serialize_game(game, request.user))


class GameBitoAPI(APIView):
    """Successful round: discard defended cards and rotate attacker/defender."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(Game, id=game_id)
        if not game.players.filter(user=request.user).exists():
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            bito(game, request.user)
        except GameError as e:
            return _err(e)
        return Response(serialize_game(game, request.user))


class LobbyMessagesAPI(APIView):
    """List recent lobby chat messages or append a new one (members only)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, lobby_id):
        lobby = get_object_or_404(Lobby, id=lobby_id)
        if not lobby.players.filter(user=request.user).exclude(status="left").exists():
            return Response(status=status.HTTP_403_FORBIDDEN)
        chat = get_lobby_chat(lobby)
        msgs = list(Message.objects.filter(chat=chat).order_by("-sent_at")[:100])
        msgs.reverse()
        return Response(
            [
                {
                    "id": str(m.id),
                    "sender_id": str(m.sender_id),
                    "username": m.sender.username,
                    "content": m.content,
                    "sent_at": m.sent_at.isoformat(),
                }
                for m in msgs
            ]
        )

    def post(self, request, lobby_id):
        lobby = get_object_or_404(Lobby, id=lobby_id)
        if not lobby.players.filter(user=request.user).exclude(status="left").exists():
            return Response(status=status.HTTP_403_FORBIDDEN)
        ser = LobbyMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        chat = get_lobby_chat(lobby)
        try:
            assert_can_send_message(chat, request.user)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        m = Message.objects.create(
            sender=request.user,
            chat=chat,
            content=ser.validated_data["content"],
        )
        broadcast_lobby(
            lobby.id,
            "lobby_chat",
            {
                "id": str(m.id),
                "sender_id": str(m.sender_id),
                "username": m.sender.username,
                "content": m.content,
                "sent_at": m.sent_at.isoformat(),
            },
        )
        return Response(
            {
                "id": str(m.id),
                "sender_id": str(m.sender_id),
                "username": m.sender.username,
                "content": m.content,
                "sent_at": m.sent_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )
