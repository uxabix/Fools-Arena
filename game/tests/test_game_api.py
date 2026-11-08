"""HTTP tests for `/api/game/` lobby and gameplay endpoints."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from game.models import Game


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
        """GET game state returns runtime phase and masked hands for opponents."""
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
        detail = api.get(reverse("api-game-state", kwargs={"game_id": gid}))
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["status"] == "in_progress"
        assert detail.data["runtime"]["phase"] == "between"
        me = next(p for p in detail.data["players"] if p["user_id"] == str(test_user.id))
        other = next(p for p in detail.data["players"] if p["user_id"] != str(test_user.id))
        assert me["hand"] is not None
        assert other["hand"] is None
