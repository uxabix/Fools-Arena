"""Decide which bot should move, then play that move through the services.

The runner stops when a person must act, when the game is over, or when
a strategy has nothing legal. It never lets a strategy write the table
itself.

Live play spaces those moves out. Defense is a short pause. A throw-in
waits a random, longer pause so a person can add a card first. A beaten
wave is not closed while someone else can still throw.
"""

import logging
import random
import threading
import time
from uuid import UUID

from django.conf import settings as django_settings
from django.db import close_old_connections, transaction

from fools.bots.actions import CallBito, DefendCard, PassThrow, PlayCards, TakeCards, TransferAttack
from fools.bots.registry import get_strategy
from fools.bots.state import BotState, CardView, TableRow
from fools.bots.strategy import BotStrategy
from fools.models import Game, PlayerHand, TableCard
from fools.services import (
    PHASE_BETWEEN,
    PHASE_BUILD,
    PHASE_DEFEND,
    PHASE_TAKING,
    GameError,
    _neighbor_user_ids,
    _player_circle,
    _rs,
    bito,
    defend,
    pass_throw,
    pending_passers,
    play_attack,
    release_finished_seats,
    take_table,
    transfer_attack,
)

logger = logging.getLogger(__name__)

MAX_BOT_STEPS = 48
DEFEND_DELAY = (0.7, 1.15)
THROW_DELAY = (2.2, 7.5)
BITO_WINDOW = (4.0, 8.0)
OPEN_DELAY = (0.45, 0.85)

_tokens: dict[str, int] = {}
_guard = threading.Lock()


def run_bots(game: Game, strategy: BotStrategy | None = None, *, single: bool = False):
    """Play bot moves until a human has to answer or the game ends.

    Args:
        game: Match that may have bot seats.
        strategy: Algorithm to ask. Defaults to the registered lowest-card
            strategy.
        single: When true, play at most one move and do not sleep. The live
            scheduler uses this so it can wait between cards.
    """
    brain = strategy or get_strategy()
    step_delay = float(getattr(django_settings, "BOT_STEP_DELAY", 0))
    first = True
    limit = 1 if single else MAX_BOT_STEPS
    for _ in range(limit):
        game.refresh_from_db()
        if game.status != "in_progress":
            return
        if _take_if_defender_empty(game):
            if single:
                return
            continue
        release_finished_seats(game)
        game.refresh_from_db()
        if game.status != "in_progress":
            return
        state = build_bot_state(game)
        if state is None:
            return
        action = brain.choose(state)
        if action is None:
            return
        if not single and not first and step_delay > 0:
            time.sleep(step_delay)
        first = False
        try:
            _apply(game, action)
        except GameError as exc:
            logger.warning("Bot move rejected: %s", exc.message)
            return


def schedule_bots(game_id):
    """Queue the next bot move on a background timer.

    A newer call cancels the previous timer. Tests leave
    ``BOT_STEP_DELAY`` at zero and call :func:`run_bots` directly.

    Args:
        game_id: Match that may need a bot.
    """
    if float(getattr(django_settings, "BOT_STEP_DELAY", 0)) <= 0:
        return
    key = str(game_id)
    with _guard:
        token = _tokens.get(key, 0) + 1
        _tokens[key] = token
    delay = _delay_for_next(key)
    timer = threading.Timer(delay, _tick, args=(key, token))
    timer.daemon = True
    timer.start()


def cancel_bots(game_id):
    """Drop a pending bot timer so a finished match does not move again.

    Args:
        game_id: Match that should stop.
    """
    key = str(game_id)
    with _guard:
        _tokens[key] = _tokens.get(key, 0) + 1


def build_bot_state(game: Game) -> BotState | None:
    """Describe the next bot action, or ``None`` when a person must play.

    Bots may throw in against a human, one card at a time. They do not
    end a beaten wave while a person can still add a card. Opening an
    attack and defending still happen when that seat is a bot.

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
    if phase == PHASE_TAKING:
        pending = pending_passers(game)
        bot_ids = [uid for uid in pending if by_id[uid].user.is_bot]
        if not bot_ids:
            return None
        thrower = _thrower(game, settings, attacker_id, defender_id, table)
        if thrower is not None and thrower in bot_ids:
            return _state(game, thrower, "throw", table, settings, room)
        return _state(game, bot_ids[0], "pass", table, settings, room)
    if phase == PHASE_BETWEEN and attacker.user.is_bot and _hand(game, attacker.user_id):
        return _state(game, attacker.user_id, "open", table, settings, 0)
    if undefended and defender.user.is_bot:
        return _state(game, defender.user_id, "defend", table, settings, room)
    if undefended:
        return None
    if table and room >= 1:
        thrower = _thrower(game, settings, attacker_id, defender_id, table)
        if thrower is not None:
            return _state(game, thrower, "throw", table, settings, room)
    if table and attacker.user.is_bot and not _human_can_throw(game):
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
    """How many more attacks can still be added.

    The defender must be able to cover the open attacks plus the new
    ones. The table also stops at five attacking cards before the first
    discard, and at six after that.
    """
    from fools.services import attack_cap

    in_hand = PlayerHand.objects.filter(fools=game, player_id=defender_id).count()
    uncovered = sum(1 for row in table if not row.defended)
    by_hand = max(0, in_hand - uncovered)
    by_cap = max(0, attack_cap(game) - len(table))
    return min(by_hand, by_cap)


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


def _human_can_throw(game) -> bool:
    """Return whether a person may still add a card to a beaten wave.

    Args:
        game: Match whose table is fully beaten.

    Returns:
        True when that person holds a matching rank and the table can take it.
    """
    rs = _rs(game)
    if "attacker_id" not in rs or "defender_id" not in rs:
        return False
    attacker_id = UUID(rs["attacker_id"])
    defender_id = UUID(rs["defender_id"])
    table = _table(game)
    if not table or any(not row.defended for row in table):
        return False
    if _room(game, defender_id, table) < 1:
        return False
    settings = game.lobby.settings
    ranks = _shown_ranks(game)
    allowed = {attacker_id}
    others = {row.user_id for row in _player_circle(game)} - {attacker_id, defender_id}
    if settings.neighbor_throw_only:
        allowed |= _neighbor_user_ids(game, defender_id) & others
    else:
        allowed |= others
    allowed.discard(defender_id)
    for user_id in allowed:
        player = game.players.select_related("user").get(user_id=user_id)
        if player.user.is_bot:
            continue
        if any(card.rank in ranks for card in _hand(game, user_id)):
            return True
    return False


def _shown_ranks(game) -> set[int]:
    ranks = set()
    rows = TableCard.objects.filter(fools=game).select_related(
        "attack_card__rank", "defense_card__rank"
    )
    for row in rows:
        ranks.add(int(row.attack_card.rank.value))
        if row.defense_card_id:
            ranks.add(int(row.defense_card.rank.value))
    return ranks


def _take_if_defender_empty(game) -> bool:
    """Pick the table up when the defender has nothing left to play.

    Args:
        game: Match that may have an empty defender and open attacks.

    Returns:
        True when the table was taken.
    """
    rs = _rs(game)
    if rs.get("phase") not in (PHASE_BUILD, PHASE_DEFEND):
        return False
    if "defender_id" not in rs:
        return False
    defender_id = UUID(rs["defender_id"])
    if not any(not row.defended for row in _table(game)):
        return False
    if PlayerHand.objects.filter(fools=game, player_id=defender_id).exists():
        return False
    user = game.players.get(user_id=defender_id).user
    try:
        take_table(game, user)
    except GameError as exc:
        logger.warning("Empty defender could not take: %s", exc.message)
        return False
    return True


def _awaiting_human_throw(game) -> bool:
    """Return whether a bot attacker should wait before ending the wave.

    Args:
        game: In-progress match.

    Returns:
        True when the wave is beaten, a person can still throw, and no bot
        throw is already the next move.
    """
    if game.status != "in_progress":
        return False
    rs = _rs(game)
    if "attacker_id" not in rs:
        return False
    attacker = game.players.select_related("user").filter(user_id=rs["attacker_id"]).first()
    if attacker is None or not attacker.user.is_bot:
        return False
    if build_bot_state(game) is not None:
        return False
    return _human_can_throw(game)


def _delay_for_next(game_id: str) -> float:
    try:
        game = Game.objects.get(id=game_id)
    except Game.DoesNotExist:
        return OPEN_DELAY[0]
    if _awaiting_human_throw(game):
        return random.uniform(*BITO_WINDOW)
    state = build_bot_state(game)
    if state is None:
        return OPEN_DELAY[0]
    if state.role == "defend":
        return random.uniform(*DEFEND_DELAY)
    if state.role in ("throw", "pass"):
        return random.uniform(*THROW_DELAY)
    if state.role == "bito":
        return random.uniform(*BITO_WINDOW) if _human_can_throw(game) else 1.15
    return random.uniform(*OPEN_DELAY)


def _work_pending(game) -> bool:
    if game.status != "in_progress":
        return False
    rs = _rs(game)
    if rs.get("phase") in (PHASE_BUILD, PHASE_DEFEND) and "defender_id" in rs:
        defender_id = UUID(rs["defender_id"])
        open_rows = any(not row.defended for row in _table(game))
        if open_rows and not PlayerHand.objects.filter(fools=game, player_id=defender_id).exists():
            return True
    if build_bot_state(game) is not None:
        return True
    return _awaiting_human_throw(game)


def _tick(game_id: str, token: int):
    close_old_connections()
    try:
        with _guard:
            if _tokens.get(game_id) != token:
                return
        try:
            game = Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            return
        if game.status != "in_progress":
            return
        if _awaiting_human_throw(game):
            _bito_after_window(game, token)
            game.refresh_from_db()
            if _work_pending(game):
                schedule_bots(game.id)
            return
        run_bots(game, single=True)
        game.refresh_from_db()
        if _work_pending(game):
            schedule_bots(game.id)
    finally:
        close_old_connections()


def _bito_after_window(game: Game, token: int) -> bool:
    with transaction.atomic():
        locked = Game.objects.select_for_update().get(id=game.id)
        with _guard:
            if _tokens.get(str(locked.id)) != token:
                return False
        if locked.status != "in_progress":
            return False
        table = _table(locked)
        if not table or any(not row.defended for row in table):
            return False
        rs = _rs(locked)
        attacker = locked.players.select_related("user").get(user_id=rs["attacker_id"])
        if not attacker.user.is_bot:
            return False
        pending = build_bot_state(locked)
        if pending is not None and pending.role != "bito":
            return False
        try:
            bito(locked, attacker.user)
        except GameError as exc:
            logger.warning("Delayed bito rejected: %s", exc.message)
            return False
        return True


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
        transfer_attack(game, user, [action.card_id])
        return
    if isinstance(action, TakeCards):
        user = game.players.get(user_id=action.user_id).user
        take_table(game, user)
        return
    if isinstance(action, CallBito):
        user = game.players.get(user_id=action.user_id).user
        bito(game, user)
        return
    if isinstance(action, PassThrow):
        user = game.players.get(user_id=action.user_id).user
        pass_throw(game, user)
