"""HTTP tests for `/api/fools/` lobby and gameplay endpoints."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from fools.models import Game


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
