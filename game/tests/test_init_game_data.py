"""Tests for the `init_game_data` management command.

This module verifies that `init_game_data` initializes card suits, ranks,
and Card records for the requested deck size. The test runs the command
with a 36-card deck and checks that the expected numbers of suits, ranks,
and cards were created.
"""

import pytest
from django.core.management import call_command

from game.models import CardSuit, CardRank, Card


@pytest.mark.django_db
def test_init_game_data_creates_cards():
    """Run `init_game_data --deck-size 36 --reset` and verify DB state.

    The test executes the management command to initialize a 36-card deck
    and asserts:
    - 4 suits were created
    - 9 ranks (6..10 plus J,Q,K,A) were created
    - 36 Card instances were created
    """

    # Run the initialization command (reset ensures idempotence)
    call_command("init_game_data", "--deck-size", "36", "--reset")

    # Check suits
    assert CardSuit.objects.count() == 4

    # Numeric 6..10 + face cards = 5 + 4 = 9
    assert CardRank.objects.count() == 9

    # Total cards = 36
    assert Card.objects.count() == 36
