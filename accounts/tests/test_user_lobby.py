"""Tests for lobby-related methods on the User model."""

import pytest
from game.models import LobbyPlayer


@pytest.mark.django_db
class TestUserLobbyMethods:
    """Test suite for user methods related to lobby interactions."""

    def test_get_active_lobby_no_lobby(self, test_user):
        """
        Tests get_active_lobby() returns None when user is not in a lobby.

        Args:
            test_user: A fixture for a test user.
        """
        assert test_user.get_active_lobby() is None

    @pytest.mark.parametrize("status", ["waiting", "ready", "playing"])
    def test_get_active_lobby_active_statuses(self, basic_lobby, test_user, status):
        """
        Tests get_active_lobby() returns the lobby for active player statuses.

        Args:
            basic_lobby: A fixture for a basic lobby instance.
            test_user: A fixture for a test user.
            status: The status to test.
        """
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status=status)
        assert test_user.get_active_lobby() == basic_lobby

    def test_get_active_lobby_left_status(self, basic_lobby, test_user):
        """
        Tests get_active_lobby() returns None when user has left the lobby.

        Args:
            basic_lobby: A fixture for a basic lobby instance.
            test_user: A fixture for a test user.
        """
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status='left')
        assert test_user.get_active_lobby() is None

    def test_can_join_lobby_success(self, lobby_factory, test_user, second_user):
        """
        Tests can_join_lobby() returns True for a valid join scenario.

        Args:
            lobby_factory: A fixture to create lobbies.
            test_user: A fixture for a test user.
            second_user: A fixture for a second test user.
        """
        lobby = lobby_factory(owner=second_user, name="Open Lobby")
        assert test_user.can_join_lobby(lobby) is True

    def test_can_join_lobby_already_in_lobby(self, basic_lobby, test_user, lobby_factory, second_user):
        """
        Tests can_join_lobby() returns False when user is already in a lobby.

        Args:
            basic_lobby: A fixture for a basic lobby instance.
            test_user: A fixture for a test user.
            lobby_factory: A fixture to create lobbies.
            second_user: A fixture for a second test user.
        """
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status='waiting')
        other_lobby = lobby_factory(owner=second_user)
        assert test_user.can_join_lobby(other_lobby) is False

    def test_can_join_lobby_full(self, lobby_factory, user_factory, test_user):
        """
        Tests can_join_lobby() returns False when the lobby is full.

        Args:
            lobby_factory: A fixture to create lobbies.
            user_factory: A fixture to create users.
            test_user: A fixture for a test user.
        """
        owner = user_factory(username='owner')
        full_lobby = lobby_factory(owner=owner, max_players=1)
        LobbyPlayer.objects.create(lobby=full_lobby, user=owner, status='waiting')
        assert test_user.can_join_lobby(full_lobby) is False

    def test_can_join_lobby_closed(self, lobby_factory, test_user, second_user):
        """
        Tests can_join_lobby() returns False for closed lobbies.

        Args:
            lobby_factory: A fixture to create lobbies.
            test_user: A fixture for a test user.
            second_user: A fixture for a second test user.
        """
        closed_lobby = lobby_factory(owner=second_user, status='closed')
        assert test_user.can_join_lobby(closed_lobby) is False

    def test_leave_current_lobby_success(self, basic_lobby, test_user):
        """
        Tests leave_current_lobby() successfully removes user from lobby.

        Args:
            basic_lobby: A fixture for a basic lobby instance.
            test_user: A fixture for a test user.
        """
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status='waiting')
        assert test_user.leave_current_lobby() is True
        assert test_user.get_active_lobby() is None

    def test_leave_current_lobby_not_in_lobby(self, test_user):
        """
        Tests leave_current_lobby() returns False when not in a lobby.

        Args:
            test_user: A fixture for a test user.
        """

        assert test_user.leave_current_lobby() is False
