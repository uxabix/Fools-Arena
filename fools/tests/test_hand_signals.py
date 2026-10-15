"""Hand tells expose positions only, and only when the lobby allows them."""

import asyncio

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from fools.hand_signals import (
    HAND_SIGNAL_LIMIT,
    accept_hand_signal,
    hand_signal_snapshot,
    normalize_hand_signal,
)
from fools.models import GamePlayer, PlayerHand
from fools.routing import websocket_urlpatterns
from fools.services import serialize_game


def _seat(game, user, cards):
    """Seat ``user`` and put ``cards`` in that hand."""
    GamePlayer.objects.create(
        fools=game,
        user=user,
        seat_position=1,
        cards_remaining=len(cards),
    )
    for index, card in enumerate(cards):
        PlayerHand.objects.create(
            fools=game,
            player=user,
            card=card,
            order_in_hand=index,
        )


@pytest.mark.django_db
def test_normalize_keeps_indexes_and_drops_anything_else():
    """A legal tell is a sort mode plus unique indexes inside the hand."""
    parsed = normalize_hand_signal(
        {
            "sort": "rank-ltr",
            "selected": [2, 0],
            "card_ids": ["not-a-card"],
            "user_id": 99,
        },
        4,
    )
    assert parsed == {"sort": "rank-ltr", "selected": [0, 2]}
    assert normalize_hand_signal({"sort": "dealt", "selected": [True]}, 2) is None
    assert normalize_hand_signal({"sort": "dealt", "selected": [0, 0]}, 2) is None
    assert normalize_hand_signal({"sort": "dealt", "selected": [2]}, 2) is None
    assert normalize_hand_signal({"sort": "nope", "selected": []}, 2) is None


@pytest.mark.django_db
def test_accept_stores_positions_for_the_socket_user(basic_game, test_user, basic_cards):
    """The tell is attributed to the seated user, not to an id in the payload."""
    cache.clear()
    _seat(basic_game, test_user, [basic_cards["seven_hearts"], basic_cards["king_spades"]])
    payload = accept_hand_signal(
        basic_game.id,
        test_user.id,
        {
            "action": "hand_signal",
            "sort": "suit-left",
            "selected": [1],
            "card_ids": [str(basic_cards["king_spades"].id)],
            "user_id": 0,
        },
    )
    assert payload == {
        "user_id": str(test_user.id),
        "sort": "suit-left",
        "selected": [1],
    }
    assert hand_signal_snapshot(basic_game.id) == [payload]
    stored = cache.get(f"fools-hand-signals:{basic_game.id}")
    assert stored[str(test_user.id)] == {"sort": "suit-left", "selected": [1]}


@pytest.mark.django_db
def test_accept_drops_tells_when_the_lobby_turns_them_off(basic_game, test_user, basic_cards):
    """A disabled lobby does not store or return a tell."""
    cache.clear()
    settings = basic_game.lobby.settings
    settings.share_hand_signals = False
    settings.save(update_fields=["share_hand_signals"])
    _seat(basic_game, test_user, [basic_cards["seven_hearts"]])
    assert accept_hand_signal(
        basic_game.id,
        test_user.id,
        {"sort": "dealt", "selected": [0]},
    ) is None
    assert hand_signal_snapshot(basic_game.id) == []


@pytest.mark.django_db
def test_accept_rejects_an_index_past_the_hand(basic_game, test_user, basic_cards):
    """Indexes are checked against the cards this seat still holds."""
    cache.clear()
    _seat(basic_game, test_user, [basic_cards["seven_hearts"]])
    assert accept_hand_signal(
        basic_game.id,
        test_user.id,
        {"sort": "dealt", "selected": [1]},
    ) is None


@pytest.mark.django_db
def test_accept_stops_after_the_rate_limit(basic_game, test_user, basic_cards):
    """A burst past the limit is dropped. The last accepted tell stays stored."""
    cache.clear()
    _seat(basic_game, test_user, [basic_cards["seven_hearts"], basic_cards["king_spades"]])
    last = None
    for _ in range(HAND_SIGNAL_LIMIT):
        last = accept_hand_signal(
            basic_game.id,
            test_user.id,
            {"sort": "dealt", "selected": [0]},
        )
        assert last is not None
    assert accept_hand_signal(
        basic_game.id,
        test_user.id,
        {"sort": "dealt", "selected": [1]},
    ) is None
    assert hand_signal_snapshot(basic_game.id) == [last]


@pytest.mark.django_db
def test_game_state_includes_the_lobby_switch(basic_game, test_user):
    """The table payload tells the browser whether to send or draw tells."""
    state = serialize_game(basic_game, test_user)
    assert state["share_hand_signals"] is True


@pytest.mark.django_db
def test_create_lobby_shares_hand_signals_unless_the_host_turns_them_off(test_user):
    """Omitting the field leaves tells on. False is stored and returned."""
    api = APIClient()
    api.force_login(test_user)
    url = reverse("api-lobby-list")
    quiet = api.post(
        url,
        {
            "name": "Quiet table",
            "is_private": False,
            "max_players": 2,
            "card_count": 36,
            "share_hand_signals": False,
        },
        format="json",
    )
    assert quiet.status_code == 201
    assert quiet.data["settings"]["share_hand_signals"] is False
    loud = api.post(
        url,
        {
            "name": "Open table",
            "is_private": False,
            "max_players": 2,
            "card_count": 36,
        },
        format="json",
    )
    assert loud.status_code == 201
    assert loud.data["settings"]["share_hand_signals"] is True


@pytest.mark.django_db(transaction=True)
def test_match_socket_broadcasts_indexes_only(basic_game, test_user, basic_cards):
    """The seated socket echoes a tell without any card identity."""
    cache.clear()
    _seat(basic_game, test_user, [basic_cards["seven_hearts"], basic_cards["king_spades"]])

    async def scenario():
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/games/{basic_game.id}/",
        )
        communicator.scope["user"] = test_user
        connected, _ = await communicator.connect()
        assert connected
        await communicator.send_json_to(
            {
                "action": "hand_signal",
                "sort": "dealt",
                "selected": [0],
                "card_ids": [str(basic_cards["king_spades"].id)],
            }
        )
        message = await communicator.receive_json_from()
        await communicator.disconnect()
        return message

    message = asyncio.run(scenario())
    assert message["event"] == "hand_signal"
    assert message["payload"] == {
        "user_id": str(test_user.id),
        "sort": "dealt",
        "selected": [0],
    }
