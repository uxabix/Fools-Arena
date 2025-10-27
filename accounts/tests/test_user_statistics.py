"""Tests for statistics-related methods on the User model."""

import pytest
from game.models import GamePlayer


@pytest.mark.django_db
class TestUserStatisticsMethods:
    """Test suite for user methods related to game statistics."""

    def test_get_game_statistics_no_games(self, test_user):
        """
        Tests get_game_statistics() with no games played.

        Args:
            test_user: A fixture for a test user.
        """
        stats = test_user.get_game_statistics()
        assert stats['total_games'] == 0
        assert stats['games_won'] == 0
        assert stats['games_lost'] == 0
        assert stats['win_rate'] == 0.0

    def test_get_game_statistics_with_wins_and_losses(
            self, game_factory, basic_lobby, basic_cards, test_user, second_user
    ):
        """
        Tests get_game_statistics() with mixed results.

        Args:
            game_factory: A fixture to create games.
            basic_lobby: A fixture for a basic lobby instance.
            basic_cards: A fixture for basic card instances.
            test_user: A fixture for a test user.
            second_user: A fixture for a second test user.
        """
        # Create 3 finished games: 2 wins, 1 loss for test_user
        for i in range(3):
            game = game_factory(
                lobby=basic_lobby,
                trump_card=basic_cards['ace_hearts'],
                status='finished',
                loser=test_user if i == 0 else second_user
            )
            GamePlayer.objects.create(game=game, user=test_user, seat_position=1, cards_remaining=6)
            GamePlayer.objects.create(game=game, user=second_user, seat_position=2, cards_remaining=6)

        stats = test_user.get_game_statistics()
        assert stats['total_games'] == 3
        assert stats['games_won'] == 2
        assert stats['games_lost'] == 1
        assert stats['win_rate'] == 66.7

    def test_get_game_statistics_ignores_active_games(
            self, game_factory, basic_lobby, basic_cards, test_user, second_user
    ):
        """
        Tests get_game_statistics() only counts finished games.

        Args:
            game_factory: A fixture to create games.
            basic_lobby: A fixture for a basic lobby instance.
            basic_cards: A fixture for basic card instances.
            test_user: A fixture for a test user.
            second_user: A fixture for a second test user.
        """
        # Create an active game (should be ignored)
        active_game = game_factory(
            lobby=basic_lobby,
            trump_card=basic_cards['ace_hearts'],
            status='in_progress'
        )
        GamePlayer.objects.create(game=active_game, user=test_user, seat_position=1, cards_remaining=6)

        # Create a finished game (should be counted)
        finished_game = game_factory(
            lobby=basic_lobby,
            trump_card=basic_cards['king_spades'],
            status='finished',
            loser=second_user  # test_user wins
        )
        GamePlayer.objects.create(game=finished_game, user=test_user, seat_position=1, cards_remaining=6)
        GamePlayer.objects.create( game=finished_game, user=second_user, seat_position=2, cards_remaining=6)

        stats = test_user.get_game_statistics()

        # Should only count the finished game
        assert stats['total_games'] == 1
        assert stats['games_won'] == 1
        assert stats['games_lost'] == 0
        assert stats['win_rate'] == 100.0
