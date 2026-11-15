"""WebSocket tests for the lobby list, a lobby room, and a table."""

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from fools.models import Game, GamePlayer, Lobby, LobbyPlayer, LobbySettings, PlayerHand
from fools.tests.test_game_api import _card
from Fools_Arena.routing import websocket_application


def _communicator(path, user):
    communicator = WebsocketCommunicator(websocket_application, path)
    communicator.scope["user"] = user
    return communicator


@pytest.mark.django_db(transaction=True)
def test_guest_cannot_watch_the_lobby_list():
    async def open_socket():
        communicator = _communicator("/ws/lobbies/", AnonymousUser())
        return await communicator.connect()

    connected, code = async_to_sync(open_socket)()
    assert connected is False
    assert code == 4401


@pytest.mark.django_db(transaction=True)
def test_signed_in_user_receives_lobby_list_events(test_user):
    """Membership is not required. A list broadcast reaches the socket."""

    async def watch():
        communicator = _communicator("/ws/lobbies/", test_user)
        connected, _code = await communicator.connect()
        await get_channel_layer().group_send(
            "lobby_list",
            {"type": "fools.event", "message": {"event": "lobby_upsert", "payload": {"id": "room-1"}}},
        )
        payload = await communicator.receive_json_from()
        await communicator.disconnect()
        return connected, payload

    connected, payload = async_to_sync(watch)()
    assert connected is True
    assert payload == {"event": "lobby_upsert", "payload": {"id": "room-1"}}


@pytest.mark.django_db(transaction=True)
def test_outsider_cannot_join_a_lobby_socket(test_user):
    lobby = Lobby.objects.create(owner=test_user, name="closed", status="waiting")

    async def open_socket():
        communicator = _communicator(f"/ws/lobbies/{lobby.id}/", test_user)
        return await communicator.connect()

    connected, code = async_to_sync(open_socket)()
    assert connected is False
    assert code == 4403


@pytest.mark.django_db(transaction=True)
def test_lobby_member_receives_room_events(test_user):
    lobby = Lobby.objects.create(owner=test_user, name="open", status="waiting")
    LobbyPlayer.objects.create(lobby=lobby, user=test_user, status="waiting")

    async def watch():
        communicator = _communicator(f"/ws/lobbies/{lobby.id}/", test_user)
        connected, _code = await communicator.connect()
        await get_channel_layer().group_send(
            f"lobby_{lobby.id}",
            {
                "type": "fools.event",
                "message": {"event": "player_joined", "payload": {"user_id": str(test_user.id)}},
            },
        )
        payload = await communicator.receive_json_from()
        await communicator.disconnect()
        return connected, payload

    connected, payload = async_to_sync(watch)()
    assert connected is True
    assert payload["event"] == "player_joined"
    assert payload["payload"]["user_id"] == str(test_user.id)


@pytest.mark.django_db(transaction=True)
def test_outsider_cannot_join_a_game_socket(test_user, durak_deck_36):
    lobby = Lobby.objects.create(owner=test_user, name="table", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=2, card_count=36)
    game = Game.objects.create(
        lobby=lobby, trump_card=_card("Spades", 14), status="in_progress"
    )

    async def open_socket():
        communicator = _communicator(f"/ws/games/{game.id}/", test_user)
        return await communicator.connect()

    connected, code = async_to_sync(open_socket)()
    assert connected is False
    assert code == 4403


@pytest.mark.django_db(transaction=True)
def test_seated_player_receives_game_events(test_user, durak_deck_36):
    lobby = Lobby.objects.create(owner=test_user, name="table", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=2, card_count=36)
    game = Game.objects.create(
        lobby=lobby, trump_card=_card("Spades", 14), status="in_progress"
    )
    GamePlayer.objects.create(fools=game, user=test_user, seat_position=1, cards_remaining=0)

    async def watch():
        communicator = _communicator(f"/ws/games/{game.id}/", test_user)
        connected, _code = await communicator.connect()
        await get_channel_layer().group_send(
            f"game_{game.id}",
            {"type": "fools.event", "message": {"event": "game_update", "payload": {}}},
        )
        payload = await communicator.receive_json_from()
        await communicator.disconnect()
        return connected, payload

    connected, payload = async_to_sync(watch)()
    assert connected is True
    assert payload == {"event": "game_update", "payload": {}}


@pytest.mark.django_db(transaction=True)
def test_hand_signal_broadcasts_indexes_only(test_user, durak_deck_36):
    """A lifted-card tell carries positions, not card identities."""
    lobby = Lobby.objects.create(owner=test_user, name="tells", status="playing")
    LobbySettings.objects.create(
        lobby=lobby, max_players=2, card_count=36, share_hand_signals=True
    )
    game = Game.objects.create(
        lobby=lobby, trump_card=_card("Spades", 14), status="in_progress"
    )
    GamePlayer.objects.create(fools=game, user=test_user, seat_position=1, cards_remaining=1)
    PlayerHand.objects.create(
        fools=game, player=test_user, card=_card("Hearts", 6), order_in_hand=1
    )

    async def signal():
        communicator = _communicator(f"/ws/games/{game.id}/", test_user)
        connected, _code = await communicator.connect()
        await communicator.send_json_to(
            {"action": "hand_signal", "sort": "dealt", "selected": [0], "card_id": "secret"}
        )
        payload = await communicator.receive_json_from()
        await communicator.disconnect()
        return connected, payload

    connected, payload = async_to_sync(signal)()
    assert connected is True
    assert payload["event"] == "hand_signal"
    assert payload["payload"]["selected"] == [0]
    assert payload["payload"]["user_id"] == str(test_user.id)
    assert "card_id" not in payload["payload"]
    assert "secret" not in str(payload)
