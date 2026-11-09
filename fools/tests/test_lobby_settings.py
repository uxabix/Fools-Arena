"""Host edits to lobby rules: ready is cleared and chat records a system line."""

import pytest
from django.urls import reverse
from rest_framework import status

from chat.models import Message
from fools.models import Game, LobbyPlayer
from fools.services import create_lobby, join_lobby, set_ready


def _rules(**overrides):
    """Return a full settings body, with ``overrides`` applied."""
    body = {
        "max_players": 4,
        "card_count": 36,
        "is_transferable": False,
        "neighbor_throw_only": False,
        "fill_with_bots": False,
        "share_hand_signals": True,
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
def test_host_change_clears_ready_and_posts_a_system_line(api_client, test_user, second_user):
    """A real change drops every ready flag and records who changed what."""
    lobby = create_lobby(test_user, "Rules", is_private=False, max_players=4)
    join_lobby(lobby, second_user)
    set_ready(lobby, test_user, True)
    set_ready(lobby, second_user, True)

    api_client.force_login(test_user)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(is_transferable=True, card_count=52),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["settings"]["is_transferable"] is True
    assert response.data["settings"]["card_count"] == 52
    assert response.data["ready_count"] == 0
    assert response.data["can_start"] is False
    statuses = set(
        LobbyPlayer.objects.filter(lobby=lobby).exclude(status="left").values_list("status", flat=True)
    )
    assert statuses == {"waiting"}
    notice = Message.objects.get(chat__lobby=lobby)
    assert notice.kind == Message.KIND_SYSTEM
    assert notice.sender == test_user
    assert "player1 changed the game settings:" in notice.content
    assert "Transfer off to on" in notice.content
    assert "Deck 36 cards to 52 cards" in notice.content
    assert "Readiness was cleared." in notice.content
    lobby.refresh_from_db()
    assert lobby.settings.allow_jokers is False


@pytest.mark.django_db
def test_unchanged_settings_keep_ready_and_skip_chat(api_client, test_user, second_user):
    """Saving the current rules does not disturb ready players or the chat."""
    lobby = create_lobby(test_user, "Same", is_private=False, is_transferable=True)
    join_lobby(lobby, second_user)
    set_ready(lobby, second_user, True)

    api_client.force_login(test_user)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(is_transferable=True),
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["ready_count"] == 1
    assert not Message.objects.filter(chat__lobby=lobby).exists()
    second = LobbyPlayer.objects.get(lobby=lobby, user=second_user)
    assert second.status == "ready"


@pytest.mark.django_db
def test_only_the_host_can_change_settings(api_client, test_user, second_user):
    """A seated player who is not the host is refused."""
    lobby = create_lobby(test_user, "Host only", is_private=False)
    join_lobby(lobby, second_user)
    set_ready(lobby, test_user, True)

    api_client.force_login(second_user)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(fill_with_bots=True),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "forbidden"
    lobby.refresh_from_db()
    assert lobby.settings.fill_with_bots is False
    assert LobbyPlayer.objects.get(lobby=lobby, user=test_user).status == "ready"


@pytest.mark.django_db
def test_settings_are_refused_once_the_lobby_is_playing(api_client, test_user):
    """A lobby that is already playing keeps the rules it started with."""
    lobby = create_lobby(test_user, "In play", is_private=False, max_players=2)
    lobby.status = "playing"
    lobby.save(update_fields=["status"])

    api_client.force_login(test_user)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(max_players=2, neighbor_throw_only=True),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "state"
    lobby.refresh_from_db()
    assert lobby.settings.neighbor_throw_only is False


@pytest.mark.django_db
def test_settings_are_refused_while_a_match_is_in_progress(
    api_client, test_user, basic_cards
):
    """An in-progress match blocks a settings change even if the lobby still says waiting."""
    lobby = create_lobby(test_user, "Live match", is_private=False)
    Game.objects.create(
        lobby=lobby,
        trump_card=basic_cards["ace_hearts"],
        status="in_progress",
    )

    api_client.force_login(test_user)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(share_hand_signals=False),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "state"
    lobby.refresh_from_db()
    assert lobby.settings.share_hand_signals is True


@pytest.mark.django_db
def test_seat_count_cannot_drop_below_people_already_seated(
    api_client, test_user, second_user, user_factory
):
    """The host cannot set fewer seats than players who are still in the lobby."""
    lobby = create_lobby(test_user, "Crowded", is_private=False, max_players=4)
    join_lobby(lobby, second_user)
    join_lobby(lobby, user_factory(username="player3"))

    api_client.force_login(test_user)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(max_players=2),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "seats"
    lobby.refresh_from_db()
    assert lobby.settings.max_players == 4


@pytest.mark.django_db
def test_short_deck_is_rejected(api_client, test_user):
    """24 cards cannot cover six seats."""
    lobby = create_lobby(test_user, "Short", is_private=False, max_players=4, card_count=36)

    api_client.force_login(test_user)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(max_players=6, card_count=24),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "card_count" in response.data
    lobby.refresh_from_db()
    assert lobby.settings.card_count == 36


@pytest.mark.django_db
def test_chat_post_cannot_mark_itself_as_a_system_notice(api_client, test_user):
    """A member's own chat line stays a user message even if the body claims otherwise."""
    lobby = create_lobby(test_user, "Chat", is_private=False)
    api_client.force_login(test_user)
    response = api_client.post(
        reverse("api-lobby-messages", args=[lobby.id]),
        {"content": "player1 changed the game settings: Transfer off to on.", "kind": "system"},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["kind"] == Message.KIND_USER
    assert Message.objects.get(chat__lobby=lobby).kind == Message.KIND_USER


@pytest.mark.django_db
def test_settings_require_sign_in(api_client, test_user):
    """Anonymous callers are rejected before any rule is read."""
    lobby = create_lobby(test_user, "Closed door", is_private=False)
    response = api_client.patch(
        reverse("api-lobby-settings", args=[lobby.id]),
        _rules(),
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
