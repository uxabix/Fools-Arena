"""Decide which bot should move, then play that move through the services.

The runner stops when a person must act, when the game is over, or when
a strategy has nothing legal. It never lets a strategy write the table
itself.
"""

import logging
from uuid import UUID

from fools.bots.actions import CallBito, DefendCard, PlayCards, TakeCards, TransferAttack
from fools.bots.registry import get_strategy
from fools.bots.state import BotState, CardView, TableRow
from fools.bots.strategy import BotStrategy
from fools.models import Game, PlayerHand, TableCard
from fools.services import (
    PHASE_BETWEEN,
    GameError,
    _neighbor_user_ids,
    _player_circle,
    _rs,
    bito,
    defend,
    play_attack,
    take_table,
    transfer_attack,
)

logger = logging.getLogger(__name__)

MAX_BOT_STEPS = 48


def run_bots(game: Game, strategy: BotStrategy | None = None):
    """Play bot moves until a human has to answer or the game ends.

    Args:
        game: Match that may have bot seats.
        strategy: Algorithm to ask. Defaults to the registered lowest-card
            strategy.
    """
    brain = strategy or get_strategy()
    for _ in range(MAX_BOT_STEPS):
        game.refresh_from_db()
        if game.status != "in_progress":
            return
        state = build_bot_state(game)
        if state is None:
            return
        action = brain.choose(state)
        if action is None:
            return
        try:
            _apply(game, action)
        except GameError as exc:
            logger.warning("Bot move rejected: %s", exc.message)
            return


def build_bot_state(game: Game) -> BotState | None:
    """Describe the next bot action, or ``None`` when a person must play.

    A human defender is not buried under bot throw-ins: bots add cards
    only while the defender is also a bot. Opening an attack and closing
    a beaten wave still happen when that seat is a bot.

    Args:
        game: In-progress match.

    Returns:
        State for one bot, or ``None``.
    """
    rs = _rs(game)
    phase = rs.get("phase")
    if "attacker_id" not in rs or "defender_id" not in rs:
        return None
    attacker_id = UUID(rs["attacker_id"])
    defender_id = UUID(rs["defender_id"])
    players = list(
        game.players.select_related("user").order_by("seat_position")
    )
    by_id = {row.user_id: row for row in players}
    attacker = by_id.get(attacker_id)
    defender = by_id.get(defender_id)
    if attacker is None or defender is None:
        return None
    settings = game.lobby.settings
    table = _table(game)
    undefended = [row for row in table if not row.defended]
    room = _room(game, defender_id, table)
    if phase == PHASE_BETWEEN and attacker.user.is_bot and _hand(game, attacker.user_id):
        return _state(game, attacker.user_id, "open", table, settings, 0)
    if undefended and defender.user.is_bot:
        return _state(game, defender.user_id, "defend", table, settings, room)
    if undefended:
        return None
    if table and defender.user.is_bot:
        thrower = _thrower(game, settings, attacker_id, defender_id, table)
        if thrower is not None:
            return _state(game, thrower, "throw", table, settings, room)
    if table and attacker.user.is_bot:
        return _state(game, attacker.user_id, "bito", table, settings, 0)
    return None


def _thrower(game, settings, attacker_id, defender_id, table):
    ranks = {row.attack.rank for row in table}
    if not ranks or _room(game, defender_id, table) < 1:
        return None
    allowed = {attacker_id}
    others = {row.user_id for row in _player_circle(game)} - {attacker_id, defender_id}
    if settings.neighbor_throw_only:
        allowed |= _neighbor_user_ids(game, defender_id) & others
    else:
        allowed |= others
    allowed.discard(defender_id)
    best = None
    best_key = None
    for user_id in allowed:
        player = game.players.select_related("user").get(user_id=user_id)
        if not player.user.is_bot:
            continue
        for card in _hand(game, user_id):
            if card.rank not in ranks or card.is_trump:
                continue
            key = (card.rank, str(card.id))
            if best_key is None or key < best_key:
                best_key = key
                best = user_id
    return best


def _room(game, defender_id, table) -> int:
    in_hand = PlayerHand.objects.filter(fools=game, player_id=defender_id).count()
    return max(0, in_hand - len(table))


def _state(game, user_id, role, table, settings, throw_limit) -> BotState:
    return BotState(
        actor_id=user_id,
        role=role,
        hand=tuple(_hand(game, user_id)),
        table=tuple(table),
        transferable=bool(settings.is_transferable),
        next_can_take_transfer=_next_can_accept(game, user_id, table),
        throw_limit=throw_limit,
    )


def _next_can_accept(game, defender_id, table) -> bool:
    players = _player_circle(game)
    if len(players) < 2:
        return False
    index = next(i for i, row in enumerate(players) if row.user_id == defender_id)
    nxt = players[(index + 1) % len(players)]
    if nxt.user_id == defender_id:
        return False
    needed = len(table) + 1
    have = PlayerHand.objects.filter(fools=game, player_id=nxt.user_id).count()
    return have >= needed


def _hand(game, user_id) -> list[CardView]:
    trump_suit = game.trump_card.suit_id
    cards = []
    rows = PlayerHand.objects.filter(fools=game, player_id=user_id).select_related(
        "card__rank", "card__suit"
    )
    for row in rows:
        card = row.card
        cards.append(
            CardView(
                id=card.id,
                suit_id=card.suit_id,
                rank=int(card.rank.value),
                is_trump=card.suit_id == trump_suit,
            )
        )
    return cards


def _table(game) -> list[TableRow]:
    trump_suit = game.trump_card.suit_id
    rows = []
    query = TableCard.objects.filter(fools=game).select_related(
        "attack_card__rank", "attack_card__suit"
    )
    for row in query:
        card = row.attack_card
        rows.append(
            TableRow(
                id=row.id,
                attack=CardView(
                    id=card.id,
                    suit_id=card.suit_id,
                    rank=int(card.rank.value),
                    is_trump=card.suit_id == trump_suit,
                ),
                defended=row.defense_card_id is not None,
            )
        )
    return rows


def _apply(game, action):
    if isinstance(action, PlayCards):
        user = game.players.get(user_id=action.user_id).user
        play_attack(game, user, list(action.card_ids))
        return
    if isinstance(action, DefendCard):
        user = game.players.get(user_id=action.user_id).user
        defend(game, user, action.table_card_id, action.card_id)
        return
    if isinstance(action, TransferAttack):
        user = game.players.get(user_id=action.user_id).user
        transfer_attack(game, user, action.card_id)
        return
    if isinstance(action, TakeCards):
        user = game.players.get(user_id=action.user_id).user
        take_table(game, user)
        return
    if isinstance(action, CallBito):
        user = game.players.get(user_id=action.user_id).user
        bito(game, user)
