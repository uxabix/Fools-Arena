"""Tests for game-related models: Game and GamePlayer.

This module tests game creation, player management, game state tracking,
and winner determination.
"""

import pytest
from django.db import IntegrityError
from django.utils import timezone
from game.models import Game, GamePlayer, PlayerHand, Card, CardSuit, CardRank


@pytest.mark.django_db
class TestGameModel:
    """Test suite for Game model."""

    def test_game_creation(self, basic_lobby, basic_cards):
        """Test that Game instances are created correctly with required fields."""
        basic_lobby.status = 'playing'
        basic_lobby.save()

        game = Game.objects.create(
            lobby=basic_lobby,
            trump_card=basic_cards['ace_hearts'],
            status='in_progress'
        )

        assert game.lobby == basic_lobby
        assert game.trump_card == basic_cards['ace_hearts']
        assert game.status == 'in_progress'
        assert game.finished_at is None
        assert game.loser is None

    def test_game_str_representation(self, basic_game):
        """Test string representation shows lobby name and game status."""
        expected = "Game in Test Lobby (in_progress)"
        assert str(basic_game) == expected

    def test_is_active_method(self, basic_game):
        """Test is_active() returns True for in_progress games and False for finished."""
        # Active game
        assert basic_game.is_active() is True

        # Finished game
        basic_game.status = 'finished'
        assert basic_game.is_active() is False

    def test_get_trump_suit_method(self, basic_game, card_suits):
        """Test get_trump_suit() returns the suit of the trump card."""
        trump_suit = basic_game.get_trump_suit()
        assert trump_suit == card_suits['hearts']

    def test_get_player_count_method(self, basic_game, test_user, second_user):
        """Test get_player_count() returns correct number of players in game."""
        # Initially no players
        assert basic_game.get_player_count() == 0

        # Add first player
        GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )
        assert basic_game.get_player_count() == 1

        # Add second player
        GamePlayer.objects.create(
            game=basic_game,
            user=second_user,
            seat_position=2,
            cards_remaining=6
        )
        assert basic_game.get_player_count() == 2

    def test_get_winner_method_active_game(self, basic_game):
        """Test get_winner() returns None for games that are still in progress."""
        assert basic_game.get_winner() is None

    def test_get_winner_method_finished_game(self, basic_game, test_user, second_user):
        """Test get_winner() returns all players except the loser.

        In the game, the loser is the player left with cards when the deck
        is empty. All other players are considered winners.
        """
        player1 = GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=0
        )

        player2 = GamePlayer.objects.create(
            game=basic_game,
            user=second_user,
            seat_position=2,
            cards_remaining=3
        )

        # Finish the game with player2 as loser
        basic_game.status = 'finished'
        basic_game.loser = second_user
        basic_game.finished_at = timezone.now()
        basic_game.save()

        winners = basic_game.get_winner()

        assert winners is not None
        assert winners.count() == 1
        assert winners.first().user == test_user

    def test_game_ordering(self, basic_lobby, basic_cards):
        """Test that games are ordered by start time (newest first).

        The model's Meta.ordering should ensure that newly created games
        appear first in querysets.
        """
        basic_lobby.status = 'playing'
        basic_lobby.save()

        game1 = Game.objects.create(
            lobby=basic_lobby,
            trump_card=basic_cards['ace_hearts'],
            status='in_progress'
        )

        game2 = Game.objects.create(
            lobby=basic_lobby,
            trump_card=basic_cards['king_spades'],
            status='in_progress'
        )

        games = list(Game.objects.all())

        assert games[0] == game2  # Newest first
        assert games[1] == game1


@pytest.mark.django_db
class TestGamePlayerModel:
    """Test suite for GamePlayer model."""

    def test_game_player_creation(self, basic_game, test_user):
        """Test that GamePlayer instances are created correctly."""
        game_player = GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )

        assert game_player.game == basic_game
        assert game_player.user == test_user
        assert game_player.seat_position == 1
        assert game_player.cards_remaining == 6

    def test_game_player_str_representation(self, basic_game, test_user):
        """Test string representation shows username, card count, and position."""
        game_player = GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )

        expected = "player1 (6 cards) - Position 1"
        assert str(game_player) == expected

    def test_has_cards_method(self, basic_game, test_user):
        """Test has_cards() returns True when player has cards remaining."""
        game_player = GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )

        assert game_player.has_cards() is True

        game_player.cards_remaining = 0
        assert game_player.has_cards() is False

    def test_is_eliminated_method(self, basic_game, test_user):
        """Test is_eliminated() returns True when player has no cards left."""
        game_player = GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )

        assert game_player.is_eliminated() is False

        game_player.cards_remaining = 0
        assert game_player.is_eliminated() is True

    def test_get_hand_cards_method(self, basic_game, test_user, card_suits, card_ranks):
        """Test get_hand_cards() returns all cards in player's hand."""
        game_player = GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )

        # Create a card in player's hand
        seven = CardRank.objects.get_or_create(name="Seven", value=7)[0]
        hearts = card_suits['hearts']
        card = Card.objects.create(suit=hearts, rank=seven)

        PlayerHand.objects.create(
            game=basic_game,
            player=test_user,
            card=card,
            order_in_hand=1
        )

        hand_cards = game_player.get_hand_cards()

        assert hand_cards.count() == 1
        assert hand_cards.first().card == card

    def test_unique_together_constraint(self, basic_game, test_user):
        """Test that a user cannot be added to the same game twice.

        The database enforces uniqueness on (game, user) combination.
        """
        GamePlayer.objects.create(
            game=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6
        )

        # Attempting to create duplicate should fail
        with pytest.raises(IntegrityError):
            GamePlayer.objects.create(
                game=basic_game,
                user=test_user,
                seat_position=2,
                cards_remaining=6
            )

    def test_game_player_ordering(self, basic_game, user_factory):
        """Test that game players are ordered by seat position.

        Players should be sorted by their seat_position in ascending order.
        """
        user1 = user_factory(username="player1")
        user2 = user_factory(username="player2")
        user3 = user_factory(username="player3")

        # Create players in non-sequential order
        player2 = GamePlayer.objects.create(
            game=basic_game,
            user=user2,
            seat_position=3,
            cards_remaining=6
        )

        player3 = GamePlayer.objects.create(
            game=basic_game,
            user=user3,
            seat_position=2,
            cards_remaining=6
        )

        player1 = GamePlayer.objects.create(
            game=basic_game,
            user=user1,
            seat_position=1,
            cards_remaining=6
        )

        players = list(GamePlayer.objects.filter(game=basic_game))

        # Should be sorted by seat position
        assert players[0].seat_position == 1
        assert players[1].seat_position == 2
        assert players[2].seat_position == 3
