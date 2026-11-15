"""HTTP tests for `/api/fools/` lobby and gameplay endpoints."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from fools.models import (
    Card,
    Game,
    GamePlayer,
    Lobby,
    LobbyPlayer,
    LobbySettings,
    PlayerHand,
    TableCard,
)


@pytest.mark.django_db
class TestGameLobbyAPI:
    """Integration tests using DRF APIClient and session auth."""

    @pytest.fixture
    def api(self):
        """Returns:
            APIClient: Unauthenticated REST client.
        """
        return APIClient()

    def test_list_requires_auth(self, api):
        """Unauthenticated GET on lobby list should return 403."""
        url = reverse("api-lobby-list")
        r = api.get(url)
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_create_rejects_a_deck_that_cannot_deal_every_seat(self, api, test_user):
        """24 cards deal 6 each, so 6 seats are refused before a lobby exists."""
        api.force_login(test_user)
        response = api.post(
            reverse("api-lobby-list"),
            {
                "name": "Too small",
                "is_private": False,
                "max_players": 6,
                "card_count": 24,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "card_count" in response.data

    def test_create_and_list_lobby(self, api, test_user, durak_deck_36):
        """Authenticated user can create a lobby and see it in the public list."""
        api.force_login(test_user)
        create_url = reverse("api-lobby-list")
        r = api.post(
            create_url,
            {
                "name": "API Room",
                "is_private": False,
                "max_players": 4,
                "card_count": 36,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_201_CREATED
        lobby_id = r.data["id"]
        r2 = api.get(create_url)
        assert r2.status_code == status.HTTP_200_OK
        assert any(row["id"] == lobby_id for row in r2.data)

    def test_join_ready_start_flow(self, api, test_user, second_user, durak_deck_36):
        """Two players: join, ready, owner starts — returns 201 with game payload."""
        api.force_login(test_user)
        r = api.post(
            reverse("api-lobby-list"),
            {"name": "Flow", "is_private": False, "card_count": 36, "max_players": 4},
            format="json",
        )
        assert r.status_code == status.HTTP_201_CREATED
        lid = r.data["id"]
        api.force_login(second_user)
        rj = api.post(reverse("api-lobby-join", kwargs={"lobby_id": lid}), {}, format="json")
        assert rj.status_code == status.HTTP_200_OK
        api.force_login(test_user)
        api.post(reverse("api-lobby-ready", kwargs={"lobby_id": lid}), {"ready": True}, format="json")
        api.force_login(second_user)
        api.post(reverse("api-lobby-ready", kwargs={"lobby_id": lid}), {"ready": True}, format="json")
        api.force_login(test_user)
        rs = api.post(reverse("api-lobby-start", kwargs={"lobby_id": lid}), {}, format="json")
        assert rs.status_code == status.HTTP_201_CREATED
        assert "id" in rs.data
        assert Game.objects.filter(id=rs.data["id"]).exists()

    def test_game_state_for_player(self, api, test_user, second_user, durak_deck_36):
        """GET fools state returns runtime phase and masked hands for opponents."""
        api.force_login(test_user)
        r = api.post(
            reverse("api-lobby-list"),
            {"name": "State", "is_private": False, "card_count": 36, "max_players": 4},
            format="json",
        )
        lid = r.data["id"]
        api.force_login(second_user)
        api.post(reverse("api-lobby-join", kwargs={"lobby_id": lid}), {}, format="json")
        api.force_login(test_user)
        api.post(reverse("api-lobby-ready", kwargs={"lobby_id": lid}), {"ready": True}, format="json")
        api.force_login(second_user)
        api.post(reverse("api-lobby-ready", kwargs={"lobby_id": lid}), {"ready": True}, format="json")
        api.force_login(test_user)
        rs = api.post(reverse("api-lobby-start", kwargs={"lobby_id": lid}), {}, format="json")
        gid = rs.data["id"]
        detail = api.get(reverse("api-fools-state", kwargs={"game_id": gid}))
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["status"] == "in_progress"
        assert detail.data["runtime"]["phase"] == "between"
        assert detail.data["runtime"]["passed_ids"] == []
        assert detail.data["runtime"]["pending_ids"] == []
        assert detail.data["transferable"] is False
        assert detail.data["neighbor_throw_only"] is False
        assert detail.data["fill_with_bots"] is False
        assert detail.data["public_events"] == []
        assert detail.data["can_rematch"] is False
        me = next(p for p in detail.data["players"] if p["user_id"] == str(test_user.id))
        other = next(p for p in detail.data["players"] if p["user_id"] != str(test_user.id))
        assert me["hand"] is not None
        assert other["hand"] is None
        from fools.models import Card, PlayerHand
        before = api.get(reverse("api-fools-state", kwargs={"game_id": gid})).data
        used = set(PlayerHand.objects.filter(fools_id=gid).values_list("card_id", flat=True))
        spare = Card.objects.filter(special_card__isnull=True).exclude(id__in=used).first()
        hidden = PlayerHand.objects.filter(fools_id=gid, player=second_user).first()
        hidden.card = spare
        hidden.save(update_fields=["card"])
        after = api.get(reverse("api-fools-state", kwargs={"game_id": gid})).data
        assert after == before
        assert spare.id not in {card["id"] for card in after["players"][0]["hand"] or []}

    def test_host_can_deal_again_after_the_game(self, api, test_user, second_user, durak_deck_36):
        """The host readies whoever is still seated and opens a new match."""
        api.force_login(test_user)
        created = api.post(
            reverse("api-lobby-list"),
            {"name": "Again", "is_private": False, "card_count": 36, "max_players": 4},
            format="json",
        )
        lid = created.data["id"]
        api.force_login(second_user)
        api.post(reverse("api-lobby-join", kwargs={"lobby_id": lid}), {}, format="json")
        api.force_login(test_user)
        api.post(reverse("api-lobby-ready", kwargs={"lobby_id": lid}), {"ready": True}, format="json")
        api.force_login(second_user)
        api.post(reverse("api-lobby-ready", kwargs={"lobby_id": lid}), {"ready": True}, format="json")
        api.force_login(test_user)
        started = api.post(reverse("api-lobby-start", kwargs={"lobby_id": lid}), {}, format="json")
        gid = started.data["id"]
        from fools.models import Game, Lobby, LobbyPlayer
        game = Game.objects.get(id=gid)
        game.status = "finished"
        game.save(update_fields=["status"])
        lobby = Lobby.objects.get(id=lid)
        lobby.status = "waiting"
        lobby.save(update_fields=["status"])
        LobbyPlayer.objects.filter(lobby=lobby).update(status="waiting")
        api.force_login(second_user)
        refused = api.post(reverse("api-fools-again", kwargs={"game_id": gid}), {}, format="json")
        assert refused.status_code == status.HTTP_400_BAD_REQUEST
        assert refused.data["code"] == "forbidden"
        api.force_login(test_user)
        again = api.post(reverse("api-fools-again", kwargs={"game_id": gid}), {}, format="json")
        assert again.status_code == status.HTTP_201_CREATED
        assert again.data["id"] != gid
        assert again.data["status"] == "in_progress"
        assert again.data["can_rematch"] is False
        seated = {row["user_id"] for row in again.data["players"]}
        assert str(test_user.id) in seated
        assert str(second_user.id) in seated
        followed = api.get(reverse("api-fools-state", kwargs={"game_id": gid}))
        assert followed.data["next_game_id"] == again.data["id"]

    def test_public_lobby_does_not_keep_a_password(self, api, test_user):
        """A public lobby ignores a password and keeps the rules that were asked for."""
        api.force_login(test_user)
        response = api.post(
            reverse("api-lobby-list"),
            {
                "name": "Public",
                "is_private": False,
                "password": "should-not-stick",
                "is_transferable": True,
                "card_count": 36,
                "max_players": 4,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["is_private"] is False
        assert response.data["settings"]["is_transferable"] is True
        from fools.models import Lobby
        lobby = Lobby.objects.get(id=response.data["id"])
        assert lobby.password_hash is None

    def test_private_lobby_requires_a_password_field_error(self, api, test_user):
        """A missing private password is reported on that field."""
        api.force_login(test_user)
        response = api.post(
            reverse("api-lobby-list"),
            {"name": "Secret", "is_private": True, "card_count": 36},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data
        assert "Enter a password" in response.data["password"][0]

    def test_private_lobby_link_asks_for_the_password(self, api, test_user, second_user):
        """Someone with the link, but not the password, is not shown the room."""
        api.force_login(test_user)
        created = api.post(
            reverse("api-lobby-list"),
            {
                "name": "Invite",
                "is_private": True,
                "password": "share-me",
                "card_count": 36,
            },
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED
        lobby_id = created.data["id"]
        api.force_login(second_user)
        denied = api.get(reverse("api-lobby-detail", kwargs={"lobby_id": lobby_id}))
        assert denied.status_code == status.HTTP_403_FORBIDDEN
        assert denied.data["code"] == "password_required"
        assert denied.data["name"] == "Invite"
        assert "players" not in denied.data
        wrong = api.post(
            reverse("api-lobby-join", kwargs={"lobby_id": lobby_id}),
            {"password": "nope"},
            format="json",
        )
        assert wrong.status_code == status.HTTP_400_BAD_REQUEST
        assert wrong.data["detail"] == "That password is incorrect."
        joined = api.post(
            reverse("api-lobby-join", kwargs={"lobby_id": lobby_id}),
            {"password": "share-me"},
            format="json",
        )
        assert joined.status_code == status.HTTP_200_OK
        assert any(row["user_id"] == str(second_user.id) for row in joined.data["players"])

    def test_lobby_list_page_hides_the_create_form(self, client, test_user):
        """The list page names the lobby field and keeps creation closed."""
        client.force_login(test_user)
        html = client.get(reverse("fools-lobby-list-page")).content.decode()
        assert 'type="text"' in html
        assert "Transferable" not in html
        assert 'id="create-form"' in html
        assert "hidden" in html
        assert "Create lobby" in html
        assert "Refresh" in html
        assert "Neighbors only" in html


def _card(suit, value):
    """Return one catalog card. Duplicate suit/rank rows pick the oldest id."""
    return (
        Card.objects.filter(suit__name=suit, rank__value=value, special_card__isnull=True)
        .order_by("id")
        .first()
    )


def _seat(game, user, seat, *cards):
    GamePlayer.objects.create(
        fools=game, user=user, seat_position=seat, cards_remaining=len(cards)
    )
    LobbyPlayer.objects.create(lobby=game.lobby, user=user, status="playing")
    for index, card in enumerate(cards, start=1):
        PlayerHand.objects.create(
            fools=game, player=user, card=card, order_in_hand=index
        )


def _table(owner, *others, phase="between", transferable=False):
    """Two or three seated humans, trump ace of spades, no deck and no bots."""
    lobby = Lobby.objects.create(owner=owner, name="API moves", status="playing")
    LobbySettings.objects.create(
        lobby=lobby,
        max_players=max(2, 1 + len(others)),
        card_count=36,
        is_transferable=transferable,
    )
    game = Game.objects.create(
        lobby=lobby,
        trump_card=_card("Spades", 14),
        status="in_progress",
        runtime_state={
            "phase": phase,
            "attacker_id": str(owner.id),
            "defender_id": str(others[0].id),
            "passed_ids": [],
        },
    )
    return game


@pytest.mark.django_db
class TestGameMoveAPI:
    """Table actions over HTTP, with cards placed by the test rather than dealt."""

    @pytest.fixture
    def api(self):
        return APIClient()

    def test_attacker_opens_with_a_card_from_hand(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user)
        six = _card("Hearts", 6)
        _seat(game, test_user, 1, six)
        _seat(game, second_user, 2, _card("Hearts", 7))
        api.force_login(test_user)
        response = api.post(
            reverse("api-fools-attack", kwargs={"game_id": game.id}),
            {"card_ids": [str(six.id)]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["runtime"]["phase"] == "build"
        assert TableCard.objects.filter(fools=game, attack_card=six).exists()
        assert not PlayerHand.objects.filter(fools=game, player=test_user, card=six).exists()

    def test_outsider_cannot_attack(self, api, test_user, second_user, user_factory, durak_deck_36):
        game = _table(test_user, second_user)
        six = _card("Hearts", 6)
        _seat(game, test_user, 1, six)
        _seat(game, second_user, 2, _card("Hearts", 7))
        api.force_login(user_factory(username="watcher"))
        response = api.post(
            reverse("api-fools-attack", kwargs={"game_id": game.id}),
            {"card_ids": [str(six.id)]},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not TableCard.objects.filter(fools=game).exists()

    def test_defender_cannot_open_the_attack(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user)
        seven = _card("Hearts", 7)
        _seat(game, test_user, 1, _card("Hearts", 6))
        _seat(game, second_user, 2, seven)
        api.force_login(second_user)
        response = api.post(
            reverse("api-fools-attack", kwargs={"game_id": game.id}),
            {"card_ids": [str(seven.id)]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert PlayerHand.objects.filter(fools=game, player=second_user, card=seven).exists()

    def test_attack_without_cards_is_rejected(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user)
        _seat(game, test_user, 1, _card("Hearts", 6))
        _seat(game, second_user, 2, _card("Hearts", 7))
        api.force_login(test_user)
        response = api.post(
            reverse("api-fools-attack", kwargs={"game_id": game.id}),
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not TableCard.objects.filter(fools=game).exists()

    def test_defender_beats_a_row(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        six = _card("Hearts", 6)
        seven = _card("Hearts", 7)
        _seat(game, test_user, 1, _card("Diamonds", 9))
        _seat(game, second_user, 2, seven)
        row = TableCard.objects.create(fools=game, attack_card=six)
        api.force_login(second_user)
        response = api.post(
            reverse("api-fools-defend", kwargs={"game_id": game.id}),
            {"table_card_id": str(row.id), "card_id": str(seven.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        row.refresh_from_db()
        assert row.defense_card_id == seven.id

    def test_attacker_cannot_defend(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        six = _card("Hearts", 6)
        nine = _card("Hearts", 9)
        _seat(game, test_user, 1, nine)
        _seat(game, second_user, 2, _card("Hearts", 7))
        row = TableCard.objects.create(fools=game, attack_card=six)
        api.force_login(test_user)
        response = api.post(
            reverse("api-fools-defend", kwargs={"game_id": game.id}),
            {"table_card_id": str(row.id), "card_id": str(nine.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        row.refresh_from_db()
        assert row.defense_card_id is None

    def test_attacker_can_seal_the_wave(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        _seat(game, test_user, 1, _card("Diamonds", 9))
        _seat(game, second_user, 2, _card("Hearts", 7))
        TableCard.objects.create(fools=game, attack_card=_card("Hearts", 6))
        api.force_login(test_user)
        response = api.post(reverse("api-fools-seal", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_200_OK
        game.refresh_from_db()
        assert game.runtime_state["phase"] == "build"

    def test_defender_cannot_seal(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        _seat(game, test_user, 1, _card("Diamonds", 9))
        _seat(game, second_user, 2, _card("Hearts", 7))
        TableCard.objects.create(fools=game, attack_card=_card("Hearts", 6))
        api.force_login(second_user)
        response = api.post(reverse("api-fools-seal", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_defender_declares_take_and_cards_stay_until_pass(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        six = _card("Hearts", 6)
        _seat(game, test_user, 1, _card("Diamonds", 9))
        _seat(game, second_user, 2, _card("Hearts", 7))
        TableCard.objects.create(fools=game, attack_card=six)
        api.force_login(second_user)
        response = api.post(reverse("api-fools-take", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["runtime"]["phase"] == "taking"
        assert TableCard.objects.filter(fools=game, attack_card=six).exists()

    def test_attacker_pass_gives_the_table_to_the_defender(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="taking")
        six = _card("Hearts", 6)
        _seat(game, test_user, 1, _card("Diamonds", 9))
        _seat(game, second_user, 2, _card("Hearts", 7))
        TableCard.objects.create(fools=game, attack_card=six)
        api.force_login(test_user)
        response = api.post(reverse("api-fools-pass", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_200_OK
        game.refresh_from_db()
        assert game.runtime_state["phase"] == "between"
        assert not TableCard.objects.filter(fools=game).exists()
        assert PlayerHand.objects.filter(fools=game, player=second_user, card=six).exists()

    def test_bito_clears_a_beaten_table_and_swaps_roles(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        _seat(game, test_user, 1, _card("Diamonds", 9))
        _seat(game, second_user, 2, _card("Clubs", 10))
        TableCard.objects.create(
            fools=game,
            attack_card=_card("Hearts", 6),
            defense_card=_card("Hearts", 7),
        )
        api.force_login(test_user)
        response = api.post(reverse("api-fools-bito", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_200_OK
        game.refresh_from_db()
        assert not TableCard.objects.filter(fools=game).exists()
        assert game.runtime_state["attacker_id"] == str(second_user.id)
        assert game.runtime_state["defender_id"] == str(test_user.id)
        assert game.status == "in_progress"

    def test_bito_is_refused_while_a_card_is_open(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        six = _card("Hearts", 6)
        _seat(game, test_user, 1, _card("Diamonds", 9))
        _seat(game, second_user, 2, _card("Hearts", 7))
        TableCard.objects.create(fools=game, attack_card=six)
        api.force_login(test_user)
        response = api.post(reverse("api-fools-bito", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert TableCard.objects.filter(fools=game, attack_card=six).exists()

    def test_defender_transfers_to_the_next_seat(self, api, test_user, second_user, user_factory, durak_deck_36):
        third = user_factory(username="third_seat")
        game = _table(test_user, second_user, third, phase="build", transferable=True)
        six_hearts = _card("Hearts", 6)
        six_diamonds = _card("Diamonds", 6)
        _seat(game, test_user, 1, _card("Clubs", 9))
        _seat(game, second_user, 2, six_diamonds)
        _seat(game, third, 3, _card("Clubs", 10), _card("Spades", 8))
        TableCard.objects.create(fools=game, attack_card=six_hearts)
        api.force_login(second_user)
        response = api.post(
            reverse("api-fools-transfer", kwargs={"game_id": game.id}),
            {"card_ids": [str(six_diamonds.id)]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        game.refresh_from_db()
        assert game.runtime_state["defender_id"] == str(third.id)
        assert game.runtime_state["attacker_id"] == str(test_user.id)
        assert TableCard.objects.filter(fools=game).count() == 2

    def test_surrender_finishes_the_match_and_keeps_the_seat(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        _seat(game, test_user, 1, _card("Hearts", 6))
        _seat(game, second_user, 2, _card("Hearts", 7))
        api.force_login(test_user)
        response = api.post(reverse("api-fools-surrender", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_200_OK
        game.refresh_from_db()
        assert game.status == "finished"
        assert game.loser_id == test_user.id
        seat = LobbyPlayer.objects.get(lobby=game.lobby, user=test_user)
        assert seat.status != "left"

    def test_leave_finishes_the_match_and_drops_the_seat(self, api, test_user, second_user, durak_deck_36):
        game = _table(test_user, second_user, phase="build")
        _seat(game, test_user, 1, _card("Hearts", 6))
        _seat(game, second_user, 2, _card("Hearts", 7))
        api.force_login(test_user)
        response = api.post(reverse("api-fools-leave", kwargs={"game_id": game.id}), {}, format="json")
        assert response.status_code == status.HTTP_200_OK
        game.refresh_from_db()
        assert game.status == "finished"
        assert game.loser_id == test_user.id
        seat = LobbyPlayer.objects.get(lobby=game.lobby, user=test_user)
        assert seat.status == "left"
