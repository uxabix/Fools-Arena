"""Bots: lowest-card strategy, seating, and a primitive transfer."""

from uuid import uuid4

import pytest

from fools.bots.actions import PlayCards, TakeCards, TransferAttack
from fools.bots.lowest import LowestCardStrategy
from fools.bots.runner import build_bot_state, run_bots
from fools.bots.state import BotState, CardView, TableRow
from fools.models import Card, Game, GamePlayer, Lobby, LobbyPlayer, LobbySettings
from fools.services import (
    GameError,
    create_lobby,
    leave_lobby,
    set_ready,
    start_game,
    transfer_attack,
)


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


@pytest.mark.django_db
def test_bot_does_not_end_the_wave_while_a_person_can_throw(durak_deck_36, user_factory):
    """A beaten wave stays open when a person still holds a matching card."""
    from fools.models import Card, Game, GamePlayer, Lobby, LobbySettings, PlayerHand, TableCard
    from fools.services import PHASE_BUILD

    attacker = user_factory(username="wave_bot", is_bot=True)
    defender = user_factory(username="wave_def", is_bot=True)
    human = user_factory(username="wave_human")
    lobby = Lobby.objects.create(owner=human, name="wave-wait", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(attacker.id),
            "defender_id": str(defender.id),
        },
    )
    for seat, user in enumerate((attacker, defender, human), start=1):
        GamePlayer.objects.create(fools=game, user=user, seat_position=seat, cards_remaining=0)
    sixes = list(Card.objects.filter(rank__value=6, special_card__isnull=True)[:2])
    cover = Card.objects.filter(rank__value=10, special_card__isnull=True).first()
    filler = list(
        Card.objects.filter(special_card__isnull=True).exclude(
            id__in=[sixes[0].id, sixes[1].id, cover.id]
        )[:3]
    )
    TableCard.objects.create(fools=game, attack_card=sixes[0], defense_card=cover)
    PlayerHand.objects.create(fools=game, player=human, card=sixes[1], order_in_hand=1)
    for index, card in enumerate(filler):
        PlayerHand.objects.create(fools=game, player=defender, card=card, order_in_hand=index + 1)

    state = build_bot_state(game)
    assert state is None


@pytest.mark.django_db
def test_start_reuses_bots_stuck_without_a_human(test_user, durak_deck_36):
    """A table with only bots does not block the next game from filling seats."""
    from fools.bots.seating import ensure_bot_pool

    bots = ensure_bot_pool()
    ghost = Lobby.objects.create(owner=bots[0], name="ghost-bots", status="playing")
    LobbySettings.objects.create(lobby=ghost, max_players=4, card_count=36, fill_with_bots=True)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(lobby=ghost, trump_card=trump, status="in_progress")
    for seat, bot in enumerate(bots, start=1):
        LobbyPlayer.objects.create(lobby=ghost, user=bot, status="playing")
        GamePlayer.objects.create(fools=game, user=bot, seat_position=seat, cards_remaining=6)

    lobby = create_lobby(test_user, "with-bots", is_private=False, max_players=2, fill_with_bots=True)
    set_ready(lobby, test_user, True)
    started = start_game(lobby, test_user)
    assert started.players.filter(user__is_bot=True).exists()
    ghost.refresh_from_db()
    assert ghost.status == "closed"


@pytest.mark.django_db
def test_last_human_leaving_closes_the_lobby(test_user, durak_deck_36):
    """Bots do not keep a lobby or its match after the last human leaves."""
    lobby = create_lobby(
        test_user,
        "solo-bots",
        is_private=False,
        max_players=2,
        fill_with_bots=True,
    )
    set_ready(lobby, test_user, True)
    game = start_game(lobby, test_user)
    assert game.status == "in_progress"

    leave_lobby(lobby, test_user)
    lobby.refresh_from_db()
    game.refresh_from_db()
    assert lobby.status == "closed"
    assert game.status == "finished"
    assert game.loser_id == test_user.id
    assert not lobby.players.exclude(status="left").exists()
