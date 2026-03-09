"""Tests for turn and move tracking models.

This module tests Turn and Move models which track game progression,
player actions, and move history.
"""

import pytest
from django.db import IntegrityError
from game.models import Turn, Move, TableCard


@pytest.mark.django_db
class TestTurnModel:
    """Test suite for Turn model.

    A Turn represents a single turn in the game, tracking which player's
    turn it is and the turn number in sequence.
    """

    def test_turn_creation(self, basic_game, test_user):
        """Tests that Turn instances are created correctly."""
        turn = Turn.objects.create(game=basic_game, player=test_user, turn_number=1)
        assert turn.game == basic_game
        assert turn.player == test_user
        assert turn.turn_number == 1

    def test_get_current_turn(self, basic_game, test_user, second_user):
        """Tests get_current_turn() returns the most recent turn for a game."""
        turn1 = Turn.objects.create(game=basic_game, player=test_user, turn_number=1)
        assert Turn.get_current_turn(basic_game) == turn1

        turn2 = Turn.objects.create(game=basic_game, player=second_user, turn_number=2)
        assert Turn.get_current_turn(basic_game) == turn2

    def test_get_current_turn_no_turns(self, basic_game):
        """Tests get_current_turn() returns None for a game without any turns."""
        assert Turn.get_current_turn(basic_game) is None

    def test_create_next_turn(self, basic_game, test_user, second_user):
        """
        Tests create_next_turn() creates a new turn with an incremented number.

        The new turn should have a turn_number equal to the previous turn's
        number plus one.
        """
        Turn.objects.create(game=basic_game, player=test_user, turn_number=1)
        next_turn = Turn.create_next_turn(basic_game, second_user)

        assert next_turn.turn_number == 2
        assert next_turn.player == second_user
        assert next_turn.game == basic_game

    def test_unique_together_constraint(self, basic_game, test_user, second_user):
        """
        Tests that the (game, turn_number) combination is unique.

        Each game can only have one turn with a specific turn_number.
        """
        Turn.objects.create(game=basic_game, player=test_user, turn_number=1)
        with pytest.raises(IntegrityError):
            Turn.objects.create(game=basic_game, player=second_user, turn_number=1)


@pytest.mark.django_db
class TestMoveModel:
    """Test suite for Move model.

    A Move represents a single action (e.g., attack, defend) during a turn.
    """

    @pytest.fixture
    def attack_move(self, basic_game, test_user, basic_cards):
        """Fixture for creating a sample attack move."""
        turn = Turn.objects.create(game=basic_game, player=test_user, turn_number=1)
        table_card = TableCard.objects.create(
            game=basic_game, attack_card=basic_cards['ace_hearts']
        )
        return Move.objects.create(
            turn=turn, table_card=table_card, action_type='attack'
        )

    def test_move_creation(self, attack_move, test_user):
        """Tests that Move instances are created correctly."""
        assert attack_move.turn.player == test_user
        assert attack_move.action_type == 'attack'
        assert attack_move.table_card is not None

    def test_get_player(self, attack_move, test_user):
        """Tests get_player() returns the player from the associated turn."""
        assert attack_move.get_player() == test_user

    @pytest.mark.parametrize(
        "action, method_name, expected",
        [
            ("attack", "is_attack", True),
            ("defend", "is_attack", False),
            ("defend", "is_defense", True),
            ("pickup", "is_pickup", True),
            ("attack", "is_pickup", False),
        ],
    )
    def test_action_check_methods(self, attack_move, action, method_name, expected):
        """
        Tests the boolean check methods (is_attack, is_defense, is_pickup).

        Args:
            attack_move: Fixture for a sample move.
            action: The action_type to set for the move.
            method_name: The name of the method to call (e.g., 'is_attack').
            expected: The expected boolean result.
        """
        attack_move.action_type = action
        method_to_call = getattr(attack_move, method_name)
        assert method_to_call() is expected
