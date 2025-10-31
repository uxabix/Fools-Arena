# game/tests/test_reset_games.py
import pytest
from django.core.management import call_command
from game.models import Game
from datetime import datetime, timedelta

@pytest.mark.django_db
def test_reset_games_removes_active_games(basic_game):
    # Ensure game exists
    assert Game.objects.count() == 1

    # Dry-run: should not delete
    call_command("reset_games")
    assert Game.objects.count() == 1

    # Actual deletion
    call_command("reset_games", "--confirm")
    assert Game.objects.count() == 0
