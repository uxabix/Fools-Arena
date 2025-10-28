"""Tests for game-related methods on the User model."""

import pytest
from game.models import GamePlayer


@pytest.mark.django_db
class TestUserGameMethods:
    """Test suite for user methods related to game interactions."""

    def test_get_current_game_no_game(self, test_user):
        """
        Tests get_current_game() returns None when user is not in a game.

        Args:
            test_user: A fixture for a test user.
        """
        assert test_user.get_current_game() is None

    def test_get_current_game_active_game(self, basic_game, test_user):
        """
        Tests get_current_game() returns game when user is playing.

        Args:
            basic_game: A fixture for a basic game instance.
            test_user: A fixture for a test user.
        """
        GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )
        assert test_user.get_current_game() == basic_game

    def test_get_current_game_finished_game(self, basic_game, test_user):
        """
        Tests get_current_game() returns None for finished games.

        Args:
            basic_game: A fixture for a basic game instance.
            test_user: A fixture for a test user.
        """
        basic_game.status = 'finished'
        basic_game.save()
        GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=0
        )
        assert test_user.get_current_game() is None
