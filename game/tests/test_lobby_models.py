"""Tests for lobby-related models: Lobby, LobbySettings, and LobbyPlayer.

This module tests lobby creation, player management, game readiness checks,
and lobby settings configuration.
"""

import pytest
from django.db import IntegrityError
from game.models import Lobby, LobbySettings, LobbyPlayer, SpecialRuleSet


@pytest.mark.django_db
class TestLobbyModel:
    """Test suite for Lobby model."""

    def test_lobby_creation(self, test_user):
        """Test that Lobby instances are created correctly with basic attributes."""
        lobby = Lobby.objects.create(
            owner=test_user,
            name="Test Lobby",
            is_private=False,
            status='waiting'
        )

        assert lobby.name == "Test Lobby"
        assert lobby.owner == test_user
        assert lobby.is_private is False
        assert lobby.status == 'waiting'

    def test_lobby_str_representation(self, test_user):
        """Test string representation returns lobby name."""
        lobby = Lobby.objects.create(
            owner=test_user,
            name="Epic Game Room",
            status='waiting'
        )

        assert str(lobby) == "Epic Game Room"

    def test_lobby_uuid_generation(self, test_user):
        """Test that UUID is automatically generated as primary key.

        The lobby uses UUID4 for primary key which should be automatically
        generated and be 36 characters long when converted to string.
        """
        lobby = Lobby.objects.create(
            owner=test_user,
            name="Test Lobby",
            status='waiting'
        )

        assert lobby.id is not None
        assert len(str(lobby.id)) == 36

    def test_is_full_method_empty_lobby(self, basic_lobby):
        """Test is_full() returns False for empty lobby."""
        assert basic_lobby.is_full() is False

    def test_is_full_method_with_players(self, basic_lobby, user_factory):
        """Test is_full() returns True when lobby reaches max_players.

        The default lobby has max_players=4, so adding 4 active players
        should make is_full() return True.
        """
        # Add players up to max (default is 4)
        for i in range(4):
            user = user_factory(username=f"player{i + 10}")
            LobbyPlayer.objects.create(
                lobby=basic_lobby,
                user=user,
                status='waiting'
            )

        assert basic_lobby.is_full() is True

    def test_is_full_excludes_left_players(self, basic_lobby, user_factory):
        """Test that is_full() doesn't count players who have left.

        Players with status 'left' should not be counted toward the
        lobby's capacity, even if they haven't been removed from the database.
        """
        # Add 3 active players
        for i in range(3):
            user = user_factory(username=f"player{i + 10}")
            LobbyPlayer.objects.create(
                lobby=basic_lobby,
                user=user,
                status='waiting'
            )

        # Add 1 player who left
        left_user = user_factory(username="left_player")
        LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=left_user,
            status='left'
        )

        # Lobby should not be full (3 active + 1 left, max is 4)
        assert basic_lobby.is_full() is False

    def test_can_start_game_method_not_enough_players(self, basic_lobby, test_user):
        """Test can_start_game() returns False with insufficient ready players.

        A game requires at least 2 ready players to start.
        """
        # Add only 1 ready player
        LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,
            status='ready'
        )

        assert basic_lobby.can_start_game() is False

    def test_can_start_game_method_enough_ready_players(self, basic_lobby, test_user, second_user):
        """Test can_start_game() returns True with at least 2 ready players."""
        # Add 2 ready players
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status='ready')
        LobbyPlayer.objects.create(lobby=basic_lobby, user=second_user, status='ready')

        assert basic_lobby.can_start_game() is True

    def test_can_start_game_method_wrong_status(self, basic_lobby, test_user, second_user):
        """Test can_start_game() returns False if lobby status is not 'waiting'.

        Only lobbies in 'waiting' status can start a game. Lobbies that are
        'playing', 'closed', or have other statuses cannot start a new game.
        """
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status='ready')
        LobbyPlayer.objects.create(lobby=basic_lobby, user=second_user, status='ready')

        # Change lobby status to 'playing'
        basic_lobby.status = 'playing'
        basic_lobby.save()

        assert basic_lobby.can_start_game() is False

    def test_get_active_players_method(self, basic_lobby, test_user, second_user, user_factory):
        """Test get_active_players() returns only players who haven't left.

        Active players are those with status 'waiting', 'ready', or 'playing'.
        Players with status 'left' should not be included.
        """
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status='waiting')
        LobbyPlayer.objects.create(lobby=basic_lobby, user=second_user, status='ready')

        left_user = user_factory(username="left")
        LobbyPlayer.objects.create(lobby=basic_lobby, user=left_user, status='left')

        active_players = basic_lobby.get_active_players()

        assert active_players.count() == 2
        assert left_user not in [player.user for player in active_players]

    def test_lobby_ordering(self, test_user, second_user):
        """Test that lobbies are ordered by creation date (newest first).

        The model's Meta.ordering should ensure that newly created lobbies
        appear first in querysets.
        """
        lobby1 = Lobby.objects.create(
            owner=test_user,
            name="Old Lobby",
            status='waiting'
        )
        lobby2 = Lobby.objects.create(
            owner=second_user,
            name="Newer Lobby",
            status='waiting'
        )

        lobbies = list(Lobby.objects.all())

        assert lobbies[0] == lobby2  # Newest first
        assert lobbies[1] == lobby1

    def test_private_lobby_with_password(self, test_user):
        """Test creating a private lobby with password hash.

        Private lobbies should have is_private=True and can optionally
        include a password_hash for authentication.
        """
        private_lobby = Lobby.objects.create(
            owner=test_user,
            name="Private Game",
            is_private=True,
            password_hash="hashed_password_here",
            status='waiting'
        )

        assert private_lobby.is_private is True
        assert private_lobby.password_hash == "hashed_password_here"


@pytest.mark.django_db
class TestLobbySettingsModel:
    """Test suite for LobbySettings model."""

    def test_lobby_settings_creation(self, test_user):
        """Test that LobbySettings instances are created correctly.

        Settings should be created with proper defaults and relationships
        to the lobby.
        """
        lobby = Lobby.objects.create(
            owner=test_user,
            name="Test Lobby",
            status='waiting'
        )

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            is_transferable=True,
            neighbor_throw_only=False,
            allow_jokers=False,
            turn_time_limit=60
        )

        assert settings.max_players == 4
        assert settings.card_count == 36
        assert settings.is_transferable is True
        assert settings.turn_time_limit == 60

    def test_lobby_settings_str_representation(self, test_user):
        """Test string representation shows lobby name, card count, and players."""
        lobby = Lobby.objects.create(
            owner=test_user,
            name="Test Lobby",
            status='waiting'
        )

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36
        )

        expected = "Test Lobby Settings (36 cards, 4 players)"
        assert str(settings) == expected

    def test_has_time_limit_method(self, test_user):
        """Test has_time_limit() returns True when turn_time_limit is set."""
        lobby = Lobby.objects.create(
            owner=test_user,
            name="Test Lobby",
            status='waiting'
        )

        settings_with_limit = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            turn_time_limit=60
        )

        assert settings_with_limit.has_time_limit() is True

    def test_has_time_limit_method_no_limit(self, test_user):
        """Test has_time_limit() returns False when turn_time_limit is None."""
        lobby1 = Lobby.objects.create(owner=test_user, name="No Limit", status='waiting')
        lobby2 = Lobby.objects.create(owner=test_user, name="Zero Limit", status='waiting')

        settings_no_limit = LobbySettings.objects.create(
            lobby=lobby1,
            max_players=2,
            card_count=24,
            turn_time_limit=None
        )

        settings_zero_limit = LobbySettings.objects.create(
            lobby=lobby2,
            max_players=2,
            card_count=24,
            turn_time_limit=0
        )

        assert settings_no_limit.has_time_limit() is False
        assert settings_zero_limit.has_time_limit() is False

    def test_is_beginner_friendly_method_true(self, test_user):
        """Test is_beginner_friendly() returns True for simple settings.

        Beginner-friendly lobbies have:
        - No transferable cards
        - No jokers
        - No special rule sets
        - No neighbor throw restrictions
        """
        lobby = Lobby.objects.create(owner=test_user, name="Beginner", status='waiting')

        beginner_settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=2,
            card_count=24,
            is_transferable=False,
            neighbor_throw_only=False,
            allow_jokers=False,
            special_rule_set=None
        )

        assert beginner_settings.is_beginner_friendly() is True

    def test_is_beginner_friendly_method_false_transferable(self, test_user):
        """Test is_beginner_friendly() returns False with transferable cards enabled."""
        lobby = Lobby.objects.create(owner=test_user, name="Advanced", status='waiting')

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            is_transferable=True,
            neighbor_throw_only=False,
            allow_jokers=False
        )

        assert settings.is_beginner_friendly() is False

    def test_is_beginner_friendly_method_false_jokers(self, test_user):
        """Test is_beginner_friendly() returns False with jokers enabled."""
        lobby = Lobby.objects.create(owner=test_user, name="Jokers", status='waiting')

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=2,
            card_count=24,
            is_transferable=False,
            allow_jokers=True
        )

        assert settings.is_beginner_friendly() is False

    def test_is_beginner_friendly_method_false_special_rules(self, test_user):
        """Test is_beginner_friendly() returns False with special rule set."""
        lobby = Lobby.objects.create(owner=test_user, name="Special", status='waiting')

        special_rules = SpecialRuleSet.objects.create(
            name="Advanced Rules",
            description="Complex rules",
            min_players=2
        )

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=2,
            card_count=24,
            is_transferable=False,
            allow_jokers=False,
            special_rule_set=special_rules
        )

        assert settings.is_beginner_friendly() is False

    def test_card_count_choices(self, test_user):
        """Test that valid card counts (24, 36, 52) are accepted.

        These are the standard deck sizes supported by the game:
        - 24 cards: 9 through Ace in all suits
        - 36 cards: 6 through Ace in all suits (most common)
        - 52 cards: 2 through Ace in all suits (full deck)
        """
        for count in [24, 36, 52]:
            lobby = Lobby.objects.create(
                owner=test_user,
                name=f"Lobby{count}",
                status='waiting'
            )
            settings = LobbySettings.objects.create(
                lobby=lobby,
                max_players=2,
                card_count=count
            )
            assert settings.card_count == count


@pytest.mark.django_db
class TestLobbyPlayerModel:
    """Test suite for LobbyPlayer model."""

    def test_lobby_player_creation(self, basic_lobby, test_user):
        """Test that LobbyPlayer instances are created correctly."""
        lobby_player = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,
            status='waiting'
        )

        assert lobby_player.lobby == basic_lobby
        assert lobby_player.user == test_user
        assert lobby_player.status == 'waiting'

    def test_lobby_player_str_representation(self, basic_lobby, test_user):
        """Test string representation shows username, status, and lobby name."""
        lobby_player = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,
            status='waiting'
        )

        expected = "player1 (waiting) in Test Lobby"
        assert str(lobby_player) == expected

    def test_is_active_method(self, basic_lobby, test_user):
        """Test is_active() method for various player statuses.

        Active statuses: 'waiting', 'ready', 'playing'
        Inactive status: 'left'
        """
        lobby_player = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,
            status='waiting'
        )

        # Test 'waiting' status
        assert lobby_player.is_active() is True

        # Test 'ready' status
        lobby_player.status = 'ready'
        assert lobby_player.is_active() is True

        # Test 'playing' status
        lobby_player.status = 'playing'
        assert lobby_player.is_active() is True

        # Test 'left' status
        lobby_player.status = 'left'
        assert lobby_player.is_active() is False

    def test_can_start_game_method(self, basic_lobby, test_user):
        """Test can_start_game() method returns True only for 'ready' status.

        Only players with 'ready' status are considered ready to start a game.
        """
        lobby_player = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,
            status='waiting'
        )

        # 'waiting' status cannot start game
        assert lobby_player.can_start_game() is False

        # 'ready' status can start game
        lobby_player.status = 'ready'
        assert lobby_player.can_start_game() is True

        # 'playing' status cannot start game (already in game)
        lobby_player.status = 'playing'
        assert lobby_player.can_start_game() is False

    def test_leave_lobby_method(self, basic_lobby, test_user):
        """Test leave_lobby() method updates player status to 'left'.

        When a player leaves, their status should be updated to 'left'
        and persisted to the database.
        """
        lobby_player = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,
            status='waiting'
        )

        lobby_player.leave_lobby()

        lobby_player.refresh_from_db()
        assert lobby_player.status == 'left'

    def test_unique_together_constraint(self, basic_lobby, test_user):
        """Test that a user cannot join the same lobby twice.

        The database enforces uniqueness on (lobby, user) combination
        to prevent duplicate player entries.
        """
        LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,
            status='waiting'
        )

        # Attempting to create duplicate should fail
        with pytest.raises(IntegrityError):
            LobbyPlayer.objects.create(
                lobby=basic_lobby,
                user=test_user,
                status='waiting'
            )

    def test_lobby_player_ordering(self, basic_lobby, test_user, second_user, user_factory):
        """Test that lobby players are ordered by lobby and username.

        Within a lobby, players should be sorted alphabetically by username.
        """
        user3 = user_factory(username="aaa_first")

        # Create players in non-alphabetical order
        player1 = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=test_user,  # player1
            status='waiting'
        )
        player2 = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=second_user,  # player2
            status='waiting'
        )
        player3 = LobbyPlayer.objects.create(
            lobby=basic_lobby,
            user=user3,  # aaa_first
            status='waiting'
        )

        players = list(LobbyPlayer.objects.filter(lobby=basic_lobby))

        # Should be sorted alphabetically by username
        assert players[0].user.username == "aaa_first"
        assert players[1].user.username == "player1"
        assert players[2].user.username == "player2"
