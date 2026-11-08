"""Tests for :mod:`game.card_catalog` merge behavior."""

import pytest

from game.card_catalog import _reassign_card_pk
from game.models import Card, CardRank, CardSuit, Game, GamePlayer, PlayerHand
from game.services import create_lobby, join_lobby


@pytest.mark.django_db
def test_reassign_merges_duplicate_hand_rows_without_unique_violation(
    test_user, second_user, durak_deck_36
):
    """If a player holds two DB rows for the same suit/rank, merge drops the extra hand row."""
    hearts = CardSuit.objects.get(name="Hearts")
    ace = CardRank.objects.get(value=14)
    c1 = (
        Card.objects.filter(suit=hearts, rank=ace, special_card__isnull=True)
        .order_by("id")
        .first()
    )
    c2 = Card.objects.create(suit=hearts, rank=ace)
    lobby = create_lobby(test_user, "merge-hand", is_private=False)
    join_lobby(lobby, second_user)
    game = Game.objects.create(lobby=lobby, trump_card=c1, status="in_progress")
    GamePlayer.objects.create(game=game, user=test_user, seat_position=1, cards_remaining=2)
    PlayerHand.objects.create(game=game, player=test_user, card=c1, order_in_hand=1)
    PlayerHand.objects.create(game=game, player=test_user, card=c2, order_in_hand=2)
    _reassign_card_pk(c2.pk, c1.pk)
    assert PlayerHand.objects.filter(game=game, player=test_user, card=c1).count() == 1
    assert not Card.objects.filter(pk=c2.pk).exists()
