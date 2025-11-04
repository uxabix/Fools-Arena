"""Tests for the `generate_fake_games` management command.

This module verifies that the `generate_fake_games` command creates `Game`
instances and associates them with `Lobby` objects.
"""

import pytest
from django.core.management import call_command

from game.models import Game, Lobby


@pytest.mark.django_db
def test_generate_fake_games_creates_games(user_factory):
    """Ensure `generate_fake_games` creates new Game objects.

    Steps:
    1. Create an owner user and a Lobby.
    2. Record the number of Game instances before running the command.
    3. Run the management command.
    4. Assert that the Game count increased and at least one game has a
       non-null lobby assignment.
    """

    user = user_factory(username="owner")
    lobby = Lobby.objects.create(owner=user, name="FakeLobby")

    count_before = Game.objects.count()

    # Generate fake games
    call_command("generate_fake_games")

    count_after = Game.objects.count()
    assert count_after > count_before, "Expected generate_fake_games to increase Game count"

    # There should be at least one game with a lobby assigned
    assert Game.objects.filter(lobby__isnull=False).exists()

    # Basic sanity on the first game
    game = Game.objects.first()
    assert game is not None
    assert game.lobby is not None
