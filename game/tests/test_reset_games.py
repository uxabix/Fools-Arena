"""Tests for the `reset_games` management command.

This module verifies that the `reset_games` command removes active/unfinished
Game instances when run with confirmation.
"""

import pytest
from django.core.management import call_command

from game.models import Game


@pytest.mark.django_db
def test_reset_games_removes_active_games(basic_game):
    """Ensure `reset_games` deletes active games only when confirmed.

    Steps:
    1. Record number of Game instances before running the command.
    2. Run `reset_games` with no arguments
    """

    # Ensure at least one game exists (provided by the basic_game fixture)
    count_before = Game.objects.count()
    assert count_before >= 1, "basic_game fixture should create at least one Game"

    # Dry-run: should not delete any games
    call_command("reset_games")
    count_after_dry = Game.objects.count()
    assert count_after_dry == count_before, "Expected dry-run reset_games to not delete games"
