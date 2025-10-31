import pytest
from django.core.management import call_command
from game.models import CardSuit, CardRank, Card

@pytest.mark.django_db
def test_init_game_data_creates_cards():
    call_command("init_game_data", "--deck-size", "36", "--reset")

    # Check suits
    assert CardSuit.objects.count() == 4

    # Numeric 6..10 + face cards = 5 + 4 = 9
    assert CardRank.objects.count() == 9

    # Total cards = 36
    assert Card.objects.count() == 36
