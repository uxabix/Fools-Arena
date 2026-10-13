"""Bots: lowest-card strategy, seating, and a primitive transfer."""

from uuid import uuid4

import pytest

from fools.bots.actions import PlayCards, TakeCards, TransferAttack
from fools.bots.lowest import LowestCardStrategy
from fools.bots.runner import run_bots
from fools.bots.state import BotState, CardView, TableRow
from fools.models import GamePlayer
from fools.services import GameError, create_lobby, set_ready, start_game, transfer_attack


def _card(rank, trump=False):
    return CardView(id=uuid4(), suit_id=uuid4(), rank=rank, is_trump=trump)


def _state(role, hand, table, transferable=False, can_transfer=False):
    return BotState(
        actor_id=uuid4(),
        role=role,
        hand=tuple(hand),
        table=tuple(table),
        transferable=transferable,
        next_can_take_transfer=can_transfer,
        throw_limit=1,
    )


class TestLowestCardStrategy:
    """The default strategy spends the cheapest card the rule allows."""

    def test_opens_with_the_lowest_non_trump(self):
        """A six is played before a trump ace."""
        low = _card(6)
        trump = _card(14, trump=True)
        action = LowestCardStrategy().choose(_state("open", [trump, low], []))
        assert isinstance(action, PlayCards)
        assert action.card_ids == (low.id,)

    def test_transfers_when_the_rule_allows_it(self):
        """A same-rank non-trump is passed on instead of beating."""
        attack = _card(10)
        match = _card(10)
        beater = _card(11)
        row = TableRow(id=uuid4(), attack=attack, defended=False)
        action = LowestCardStrategy().choose(
            _state("defend", [beater, match], [row], transferable=True, can_transfer=True)
        )
        assert isinstance(action, TransferAttack)
        assert action.card_id == match.id

    def test_does_not_transfer_when_the_rule_is_off(self):
        """Without the rule, the same hand beats the attack."""
        attack = CardView(id=uuid4(), suit_id=uuid4(), rank=10, is_trump=False)
        match = CardView(id=uuid4(), suit_id=attack.suit_id, rank=10, is_trump=False)
        beater = CardView(id=uuid4(), suit_id=attack.suit_id, rank=11, is_trump=False)
        row = TableRow(id=uuid4(), attack=attack, defended=False)
        action = LowestCardStrategy().choose(
            _state("defend", [beater, match], [row], transferable=False, can_transfer=True)
        )
        assert action.card_id == beater.id

    def test_takes_when_nothing_beats_the_attack(self):
        """No legal cover and no transfer means the bot picks the table up."""
        attack = _card(14, trump=True)
        low = _card(6)
        row = TableRow(id=uuid4(), attack=attack, defended=False)
        action = LowestCardStrategy().choose(_state("defend", [low], [row]))
        assert isinstance(action, TakeCards)


@pytest.mark.django_db
class TestBotSeating:
    """Empty chairs become ready bots when the lobby asks for them."""

    def test_start_fills_seats_and_bots_may_open(self, test_user, durak_deck_36):
        """One ready owner plus the setting produces a full table."""
        lobby = create_lobby(
            test_user,
            "Bots",
            is_private=False,
            max_players=2,
            fill_with_bots=True,
        )
        set_ready(lobby, test_user, True)
        assert lobby.can_start_game() is True
        game = start_game(lobby, test_user)
        assert game.players.count() == 2
        assert GamePlayer.objects.filter(fools=game, user__is_bot=True).count() == 1
        run_bots(game)
        game.refresh_from_db()
        assert game.status == "in_progress"

    def test_transfer_is_rejected_when_the_lobby_disallows_it(
        self, test_user, second_user, durak_deck_36
    ):
        """The service refuses a pass when transfer was not turned on."""
        lobby = create_lobby(test_user, "No pass", is_private=False, is_transferable=False)
        from fools.services import join_lobby

        join_lobby(lobby, second_user)
        set_ready(lobby, test_user, True)
        set_ready(lobby, second_user, True)
        game = start_game(lobby, test_user)
        with pytest.raises(GameError) as exc:
            transfer_attack(game, second_user, game.trump_card_id)
        assert exc.value.code == "rules"
