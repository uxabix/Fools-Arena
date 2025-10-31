import pytest
from django.core.management import call_command
from game.models import Game, Lobby
from accounts.models import User

@pytest.mark.django_db
def test_generate_fake_games_creates_games(user_factory):
    user = user_factory(username="owner")
    lobby = Lobby.objects.create(owner=user, name="FakeLobby")

    # Generate one game
    call_command("generate_fake_games")

    # There should be at least one game
    assert Game.objects.exists()
    game = Game.objects.first()
    assert game.lobby == lobby or game.lobby is not None
