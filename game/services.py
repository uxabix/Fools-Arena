"""Business logic for multiplayer Durak (podkidnoy).

This module owns lobby lifecycle, dealing from the shared card pool, table
phases (build / defend / between), and persistence updates on existing Django
models. It also triggers WebSocket broadcasts via :mod:`game.realtime`.

Typical flow:
    #. Players create or join a lobby, toggle ready, owner calls ``start_game``.
    #. Attacker opens from ``between`` into ``build``. While the wave is on the table,
       the defender may ``defend`` or ``take_table`` at any time; the attacker and
       other players may still ``play_attack`` (throw-ins) in parallel—no separate
       ``defend`` phase gate.
    #. After the table is fully beaten, attacker ``bito`` discards and rotates roles.
"""

from __future__ import annotations

import secrets
from typing import Iterable
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from game.models import (
    Card,
    DiscardPile,
    Game,
    GameDeck,
    GamePlayer,
    Lobby,
    LobbyPlayer,
    LobbySettings,
    Move,
    PlayerHand,
    TableCard,
    Turn,
)
from chat.services import get_lobby_chat, remove_user_from_lobby_chat
from game.card_catalog import ensure_playing_cards_for_deck_size
from game.realtime import broadcast_game, broadcast_lobby

User = get_user_model()

PHASE_BUILD = "build"
PHASE_DEFEND = "defend"
PHASE_BETWEEN = "between"


def rank_values_for_deck(card_count: int) -> list[int]:
    """Return ordered rank *values* (ints) included in a 24/36/52-card shoe.

    Args:
        card_count: One of ``24``, ``36``, or ``52``.

    Returns:
        List of rank values from low to high (e.g. six..ace for 36 cards).

    Raises:
        ValueError: If ``card_count`` is not supported.
    """
    if card_count == 52:
        return list(range(2, 15))
    if card_count == 36:
        return list(range(6, 15))
    if card_count == 24:
        return list(range(9, 15))
    raise ValueError("Unsupported card_count")


class GameError(Exception):
    """Domain error with a stable machine-readable ``code`` for API mapping.

    Attributes:
        message: Human-readable explanation.
        code: Short string such as ``forbidden`` or ``phase``.
    """

    def __init__(self, message: str, code: str = "invalid"):
        self.message = message
        self.code = code
        super().__init__(message)


def _rs(game: Game) -> dict:
    return dict(game.runtime_state or {})


def _save_rs(game: Game, **updates):
    rs = _rs(game)
    rs.update(updates)
    game.runtime_state = rs
    game.save(update_fields=["runtime_state"])


def _refresh_card_counts(game: Game):
    for gp in game.players.all():
        n = PlayerHand.objects.filter(game=game, player=gp.user).count()
        if gp.cards_remaining != n:
            gp.cards_remaining = n
            gp.save(update_fields=["cards_remaining"])


def _player_circle(game: Game) -> list[GamePlayer]:
    return list(game.players.order_by("seat_position"))


def _neighbor_user_ids(game: Game, defender_id: UUID) -> set[UUID]:
    players = _player_circle(game)
    idx = next(i for i, p in enumerate(players) if p.user_id == defender_id)
    n = len(players)
    return {
        players[(idx - 1) % n].user_id,
        players[(idx + 1) % n].user_id,
    }


_SHOE_CARD_COUNT = {24: 24, 36: 36, 52: 52}


def _deck_card_ids_for_shoe(settings: LobbySettings) -> list[UUID]:
    """Return exactly one card PK per (suit, rank) for the configured shoe.

    Duplicate ``Card`` rows for the same suit and rank are possible in the
    database because ``unique_together`` treats multiple ``NULL``
    ``special_card`` values as distinct. A physical deck must contain each
    suit/rank combination at most once; the row with the smallest id wins
    (stable ordering). Done in Python because ``MIN(uuid)`` is not valid SQL
    on PostgreSQL.
    """
    values = rank_values_for_deck(settings.card_count)
    qs = Card.objects.filter(special_card__isnull=True, rank__value__in=values).order_by(
        "suit_id", "rank_id", "id"
    )
    seen: set[tuple[int, int]] = set()
    out: list[UUID] = []
    for card in qs:
        key = (card.suit_id, card.rank_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(card.id)
    return out


def _pick_first_attacker(game: Game, trump_suit_id) -> UUID:
    """Choose the opening attacker by lowest trump, then lowest seat.

    Args:
        game: Active game with hands already dealt.
        trump_suit_id: Primary key of the trump :class:`~game.models.CardSuit`.

    Returns:
        UUID of the user who should attack first.
    """
    best: tuple[int, int, UUID] | None = None
    for gp in _player_circle(game):
        trumps = (
            PlayerHand.objects.filter(game=game, player=gp.user, card__suit_id=trump_suit_id)
            .select_related("card__rank")
        )
        for ph in trumps:
            val = ph.card.rank.value
            key = (val, gp.seat_position, gp.user_id)
            if best is None or key < best:
                best = key
    if best:
        return best[2]
    return _player_circle(game)[0].user_id


def _draw_for_player(game: Game, user: User, target_hand: int = 6):
    while True:
        gp = GamePlayer.objects.get(game=game, user=user)
        if gp.cards_remaining >= target_hand:
            break
        entry = GameDeck.get_top_card(game)
        if not entry:
            break
        card = entry.card
        entry.delete()
        max_order = PlayerHand.objects.filter(game=game, player=user).aggregate(
            m=Max("order_in_hand")
        )["m"]
        next_order = (max_order or 0) + 1
        PlayerHand.objects.create(
            game=game,
            player=user,
            card=card,
            order_in_hand=next_order,
        )
        gp.cards_remaining += 1
        gp.save(update_fields=["cards_remaining"])


def _draw_round_after_discard(game: Game, start_user_id: UUID):
    order = _player_circle(game)
    idx = next(i for i, p in enumerate(order) if p.user_id == start_user_id)
    n = len(order)
    for k in range(n):
        _draw_for_player(game, order[(idx + k) % n].user, 6)
    _refresh_card_counts(game)


def _maybe_finish_game(game: Game):
    if game.status != "in_progress":
        return
    deck_empty = not GameDeck.objects.filter(game=game).exists()
    if not deck_empty:
        return
    holders = [gp for gp in _player_circle(game) if gp.cards_remaining > 0]
    if len(holders) == 1:
        game.status = "finished"
        game.loser = holders[0].user
        game.finished_at = timezone.now()
        game.save(update_fields=["status", "loser", "finished_at"])
        lobby = game.lobby
        lobby.status = "waiting"
        lobby.save(update_fields=["status"])
        LobbyPlayer.objects.filter(lobby=lobby, status="playing").update(status="waiting")
        broadcast_game(game.id, "game_finished", {"loser_id": str(game.loser_id)})
        broadcast_lobby(lobby.id, "game_finished", {"game_id": str(game.id)})


def _rotate_roles_after_success(game: Game):
    rs = _rs(game)
    old_def = UUID(rs["defender_id"])
    players = _player_circle(game)
    idx_d = next(i for i, p in enumerate(players) if p.user_id == old_def)
    new_att = old_def
    new_def = players[(idx_d + 1) % len(players)].user_id
    _save_rs(game, attacker_id=str(new_att), defender_id=str(new_def), phase=PHASE_BETWEEN)


def _clear_table_to_discard(game: Game):
    cards: list[Card] = []
    for tc in TableCard.objects.filter(game=game).order_by("id"):
        cards.append(tc.attack_card)
        if tc.defense_card:
            cards.append(tc.defense_card)
    TableCard.objects.filter(game=game).delete()
    if cards:
        DiscardPile.discard_cards(game, cards)


def _clear_table_to_hand(game: Game, user: User):
    for tc in TableCard.objects.filter(game=game).order_by("id"):
        for c in (tc.attack_card, tc.defense_card):
            if not c:
                continue
            max_order = PlayerHand.objects.filter(game=game, player=user).aggregate(
                m=Max("order_in_hand")
            )["m"]
            next_order = (max_order or 0) + 1
            PlayerHand.objects.create(
                game=game,
                player=user,
                card=c,
                order_in_hand=next_order,
            )
    TableCard.objects.filter(game=game).delete()
    _refresh_card_counts(game)


def _table_attack_ranks(game: Game) -> set[int]:
    """Ranks that may be used for throw-ins: any rank shown on the table (attack or defense).

    Classic podkidnoy allows matching ranks from beaten pairs, not only the original attacks.

    Resolves ranks via :class:`~game.models.Card` rows (not multi-hop ``values_list`` on
    nullable defense FKs) so every card on the table contributes reliably.
    """
    pairs = TableCard.objects.filter(game=game).values_list(
        "attack_card_id", "defense_card_id"
    )
    card_ids: set[UUID] = set()
    for attack_id, defense_id in pairs:
        card_ids.add(attack_id)
        if defense_id:
            card_ids.add(defense_id)
    if not card_ids:
        return set()
    return {
        int(v)
        for v in Card.objects.filter(id__in=card_ids).values_list("rank__value", flat=True)
    }


def _defender_hand_size(game: Game, defender_id: UUID) -> int:
    return PlayerHand.objects.filter(game=game, player_id=defender_id).count()


def _count_undefended(game: Game) -> int:
    return TableCard.objects.filter(game=game, defense_card__isnull=True).count()


def _all_defended(game: Game) -> bool:
    qs = TableCard.objects.filter(game=game)
    return qs.exists() and not qs.filter(defense_card__isnull=True).exists()


def leave_other_active_lobbies(user: User, *, except_lobby: Lobby | None = None):
    """Leave every active lobby membership except ``except_lobby`` (if given).

    Ensures a user is only seated in one waiting/playing lobby at a time.

    Args:
        user: Player to detach from extra rooms.
        except_lobby: Lobby id to skip (e.g. the room being joined).
    """
    qs = LobbyPlayer.objects.filter(user=user).exclude(status="left")
    if except_lobby is not None:
        qs = qs.exclude(lobby_id=except_lobby.id)
    for lp in list(qs):
        leave_lobby(lp.lobby, user)


@transaction.atomic
def create_lobby(
    owner: User,
    name: str,
    *,
    is_private: bool = False,
    password: str | None = None,
    max_players: int = 4,
    card_count: int = 36,
    is_transferable: bool = False,
    neighbor_throw_only: bool = False,
    allow_jokers: bool = False,
    turn_time_limit: int | None = None,
) -> Lobby:
    """Create a lobby, default :class:`~game.models.LobbySettings`, and owner seat.

    Args:
        owner: Authenticated user who becomes lobby owner.
        name: Display name.
        is_private: Whether a password is required to join.
        password: Plain text; stored hashed when private.
        max_players: Upper bound enforced by :meth:`game.models.Lobby.is_full`.
        card_count: Deck size (24, 36, or 52).
        is_transferable: Rule flag (reserved for future transfer logic).
        neighbor_throw_only: Restrict throw-in to defender's neighbors.
        allow_jokers: Whether jokers may appear in the shoe (requires data).
        turn_time_limit: Optional per-turn cap in seconds.

    Returns:
        The newly created :class:`~game.models.Lobby` instance.
    """
    leave_other_active_lobbies(owner, except_lobby=None)
    lobby = Lobby.objects.create(
        owner=owner,
        name=name,
        is_private=is_private,
        password_hash=make_password(password) if (is_private and password) else None,
        status="waiting",
    )
    LobbySettings.objects.create(
        lobby=lobby,
        max_players=max_players,
        card_count=card_count,
        is_transferable=is_transferable,
        neighbor_throw_only=neighbor_throw_only,
        allow_jokers=allow_jokers,
        turn_time_limit=turn_time_limit,
    )
    LobbyPlayer.objects.create(lobby=lobby, user=owner, status="waiting")
    get_lobby_chat(lobby)
    broadcast_lobby(lobby.id, "lobby_created", {"lobby_id": str(lobby.id)})
    return lobby


@transaction.atomic
def join_lobby(lobby: Lobby, user: User, password: str | None = None) -> LobbyPlayer:
    """Add ``user`` to ``lobby`` or reactivate a previously left membership.

    Args:
        lobby: Target lobby.
        user: Joining user.
        password: Required plaintext password when ``lobby.is_private``.

    Returns:
        The active :class:`~game.models.LobbyPlayer` row.

    Raises:
        GameError: If the lobby is full, closed, password is wrong, or duplicate.
    """
    if lobby.status == "closed":
        raise GameError("Lobby is closed", "closed")
    leave_other_active_lobbies(user, except_lobby=lobby)
    if lobby.is_full():
        raise GameError("Lobby is full", "full")
    if lobby.is_private:
        if not lobby.password_hash or not check_password(password or "", lobby.password_hash):
            raise GameError("Invalid password", "auth")
    if LobbyPlayer.objects.filter(lobby=lobby, user=user).exclude(status="left").exists():
        raise GameError("Already in lobby", "duplicate")
    if LobbyPlayer.objects.filter(user=user, lobby=lobby, status="left").exists():
        lp = LobbyPlayer.objects.get(user=user, lobby=lobby)
        lp.status = "waiting"
        lp.save(update_fields=["status"])
    else:
        lp = LobbyPlayer.objects.create(lobby=lobby, user=user, status="waiting")
    get_lobby_chat(lobby)
    broadcast_lobby(lobby.id, "player_joined", {"user_id": str(user.id)})
    return lp


@transaction.atomic
def leave_lobby(lobby: Lobby, user: User) -> dict:
    """Mark every active membership of ``user`` in ``lobby`` as left.

    If nobody remains, the lobby is closed. If the owner leaves but others stay,
    ownership moves to another member (alphabetically by username).

    Args:
        lobby: Lobby to exit.
        user: Leaving user.

    Returns:
        Dict with ``lobby_closed`` (bool) and ``new_owner_id`` (optional str).

    Raises:
        GameError: If the user had no active membership.
    """
    qs = LobbyPlayer.objects.filter(lobby=lobby, user=user).exclude(status="left")
    if not qs.exists():
        raise GameError("Not in lobby", "not_found")
    was_owner = lobby.owner_id == user.id
    for lp in qs:
        lp.leave_lobby()
    remove_user_from_lobby_chat(lobby, user)

    lobby_closed = False
    new_owner_id: str | None = None
    remaining = LobbyPlayer.objects.filter(lobby=lobby).exclude(status="left")
    if not remaining.exists():
        if lobby.status != "closed":
            lobby.status = "closed"
            lobby.save(update_fields=["status"])
        lobby_closed = True
    elif was_owner:
        next_lp = remaining.order_by("user__username").first()
        lobby.owner = next_lp.user
        lobby.save(update_fields=["owner"])
        new_owner_id = str(next_lp.user_id)

    broadcast_lobby(lobby.id, "player_left", {"user_id": str(user.id)})
    return {"lobby_closed": lobby_closed, "new_owner_id": new_owner_id}


@transaction.atomic
def set_ready(lobby: Lobby, user: User, ready: bool):
    """Toggle waiting/ready status for a member.

    Args:
        lobby: Lobby context.
        user: Member toggling readiness.
        ready: ``True`` for ready, ``False`` for waiting.

    Raises:
        GameError: If ``user`` is not an active member.
    """
    lp = LobbyPlayer.objects.filter(lobby=lobby, user=user).exclude(status="left").first()
    if not lp:
        raise GameError("Not in lobby", "not_found")
    lp.status = "ready" if ready else "waiting"
    lp.save(update_fields=["status"])
    broadcast_lobby(lobby.id, "ready_changed", {"user_id": str(user.id), "ready": ready})


@transaction.atomic
def start_game(lobby: Lobby, user: User) -> Game:
    """Deal cards, set trump, and spawn an in-progress :class:`~game.models.Game`.

    Args:
        lobby: Must be in ``waiting`` with at least two ``ready`` members.
        user: Lobby owner (only owners may start).

    Returns:
        Fresh :class:`~game.models.Game` in ``between`` phase.

    Raises:
        GameError: On permission, deck data, duplicate active game, or rules.
    """
    if lobby.owner_id != user.id:
        raise GameError("Only owner can start", "forbidden")
    if Game.objects.filter(lobby=lobby, status="in_progress").exists():
        raise GameError("Game already in progress", "state")
    if not lobby.can_start_game():
        raise GameError("Cannot start game", "precondition")
    settings = lobby.settings
    ready_players = list(
        lobby.players.filter(status="ready").select_related("user").order_by("user__username")
    )
    if len(ready_players) < 2:
        raise GameError("Need at least 2 ready players", "precondition")

    lobby.status = "playing"
    lobby.save(update_fields=["status"])
    for lp in lobby.players.filter(status__in=["waiting", "ready"]):
        if lp in ready_players:
            lp.status = "playing"
            lp.save(update_fields=["status"])
        else:
            lp.leave_lobby()

    if settings.card_count not in _SHOE_CARD_COUNT:
        raise GameError("Unsupported card_count for this lobby", "config")
    ensure_playing_cards_for_deck_size(settings.card_count)
    card_ids = _deck_card_ids_for_shoe(settings)
    expected = _SHOE_CARD_COUNT.get(settings.card_count)
    if expected is not None and len(card_ids) != expected:
        raise GameError(
            f"Deck data mismatch after auto-seed: {len(card_ids)} unique suit/rank cards, "
            f"need {expected} for a {settings.card_count}-card shoe",
            "config",
        )
    if len(card_ids) < 12:
        raise GameError("Not enough cards in database for this deck size", "config")
    if len(card_ids) != len(set(card_ids)):
        raise GameError(
            "Deck build produced duplicate card ids; run: python manage.py init_game_data",
            "config",
        )
    secrets.SystemRandom().shuffle(card_ids)
    trump_id = card_ids[-1]
    rest = card_ids[:-1]

    game = Game.objects.create(
        lobby=lobby,
        trump_card_id=trump_id,
        status="in_progress",
        runtime_state={},
    )
    for pos, cid in enumerate(rest):
        GameDeck.objects.create(game=game, card_id=cid, position=pos)

    for seat, lp in enumerate(ready_players, start=1):
        GamePlayer.objects.create(
            game=game,
            user=lp.user,
            seat_position=seat,
            cards_remaining=0,
        )

    trump_card = Card.objects.get(id=trump_id)
    for gp in _player_circle(game):
        for _ in range(6):
            entry = GameDeck.get_top_card(game)
            if not entry:
                break
            c = entry.card
            entry.delete()
            PlayerHand.objects.create(
                game=game,
                player=gp.user,
                card=c,
                order_in_hand=None,
            )
    _refresh_card_counts(game)

    first_attacker = _pick_first_attacker(game, trump_card.suit_id)
    players = _player_circle(game)
    idx_a = next(i for i, p in enumerate(players) if p.user_id == first_attacker)
    defender = players[(idx_a + 1) % len(players)].user_id
    _save_rs(
        game,
        attacker_id=str(first_attacker),
        defender_id=str(defender),
        phase=PHASE_BETWEEN,
    )

    broadcast_lobby(lobby.id, "game_started", {"game_id": str(game.id)})
    broadcast_game(game.id, "game_started", {})
    return game


def serialize_lobby(lobby: Lobby) -> dict:
    """Build a JSON-serializable lobby snapshot for REST responses.

    Args:
        lobby: Lobby including related settings and players.

    Returns:
        Dict with ids as strings, nested ``settings``, ``players``, and optional
        ``active_game_id``.
    """
    settings = lobby.settings
    return {
        "id": str(lobby.id),
        "name": lobby.name,
        "owner_id": str(lobby.owner_id),
        "is_private": lobby.is_private,
        "status": lobby.status,
        "created_at": lobby.created_at.isoformat(),
        "settings": {
            "max_players": settings.max_players,
            "card_count": settings.card_count,
            "is_transferable": settings.is_transferable,
            "neighbor_throw_only": settings.neighbor_throw_only,
            "allow_jokers": settings.allow_jokers,
            "turn_time_limit": settings.turn_time_limit,
        },
        "players": [
            {
                "user_id": str(p.user_id),
                "username": p.user.username,
                "status": p.status,
            }
            for p in lobby.players.exclude(status="left").select_related("user")
        ],
        "active_game_id": _active_game_id(lobby),
        "can_start": lobby.can_start_game(),
        "ready_count": lobby.players.filter(status="ready").count(),
        "active_player_count": lobby.players.exclude(status="left").count(),
    }


def _active_game_id(lobby: Lobby) -> str | None:
    g = Game.objects.filter(lobby=lobby, status="in_progress").order_by("-started_at").first()
    return str(g.id) if g else None


def serialize_game(game: Game, viewer: User) -> dict:
    """Return game state visible to ``viewer`` (only their hand is revealed).

    Args:
        game: Game to serialize.
        viewer: Authenticated subject; opponents see counts only.

    Returns:
        Dict with ``table``, ``runtime``, ``trump_card``, ``deck_remaining``, etc.
    """
    _refresh_card_counts(game)
    trump = game.trump_card
    rs = _rs(game)
    table = []
    for tc in TableCard.objects.filter(game=game).select_related(
        "attack_card__suit", "attack_card__rank", "defense_card__suit", "defense_card__rank"
    ):
        table.append(
            {
                "id": str(tc.id),
                "attack": _card_json(tc.attack_card),
                "defense": _card_json(tc.defense_card) if tc.defense_card else None,
            }
        )
    players_out = []
    for gp in _player_circle(game):
        hand = None
        if gp.user_id == viewer.id:
            hand = [
                {**_card_json(ph.card), "hand_id": str(ph.id)}
                for ph in PlayerHand.objects.filter(game=game, player=gp.user)
                .select_related("card__suit", "card__rank")
                .order_by("order_in_hand", "id")
            ]
        players_out.append(
            {
                "user_id": str(gp.user_id),
                "username": gp.user.username,
                "seat_position": gp.seat_position,
                "cards_remaining": gp.cards_remaining,
                "hand": hand,
            }
        )
    deck_left = GameDeck.objects.filter(game=game).count()
    return {
        "id": str(game.id),
        "lobby_id": str(game.lobby_id),
        "status": game.status,
        "trump_card": _card_json(trump),
        "deck_remaining": deck_left,
        "runtime": {
            "attacker_id": rs.get("attacker_id"),
            "defender_id": rs.get("defender_id"),
            "phase": rs.get("phase"),
        },
        "players": players_out,
        "table": table,
        "loser_id": str(game.loser_id) if game.loser_id else None,
    }


def _card_json(card: Card | None) -> dict | None:
    if not card:
        return None
    return {
        "id": str(card.id),
        "suit": card.suit.name,
        "rank": card.rank.name,
        "value": card.rank.value,
    }


def _ensure_turn(game: Game, user: User) -> Turn:
    t = Turn.get_current_turn(game)
    if t and t.player_id == user.id:
        return t
    return Turn.create_next_turn(game, user)


@transaction.atomic
def play_attack(game: Game, user: User, card_ids: list[UUID]):
    """Place attacking or throw-in cards from the actor's hand onto the table.

    Args:
        game: Active game.
        user: Attacker (open or extend) or throw-in player during ``build``.
        card_ids: Cards currently held by ``user``.

    Raises:
        GameError: On wrong phase, illegal ranks, capacity, or ownership.
    """
    if game.status != "in_progress":
        raise GameError("Game not active", "finished")
    rs = _rs(game)
    phase = rs.get("phase")
    if phase not in (PHASE_BUILD, PHASE_BETWEEN, PHASE_DEFEND):
        raise GameError("Cannot attack now", "phase")

    settings = game.lobby.settings
    attacker_id = UUID(rs["attacker_id"])
    defender_id = UUID(rs["defender_id"])

    if phase == PHASE_BETWEEN:
        if user.id != attacker_id:
            raise GameError("Only attacker may open", "turn")
        if TableCard.objects.filter(game=game).exists():
            raise GameError("Table must be empty", "state")
        if not card_ids:
            raise GameError("Play at least one card", "cards")
        cards = _cards_in_hand(game, user, card_ids)
        ranks = {c.rank_id for c in cards}
        if len(ranks) != 1:
            raise GameError("Attack cards must share rank", "cards")
        _save_rs(game, phase=PHASE_BUILD)
    else:
        if user.id == defender_id:
            raise GameError("Defender cannot attack", "turn")
        if user.id != attacker_id:
            if phase not in (PHASE_BUILD, PHASE_DEFEND):
                raise GameError("Cannot throw in now", "phase")
            eligible = {attacker_id, defender_id}
            others = {p.user_id for p in _player_circle(game)} - eligible
            if user.id not in others:
                raise GameError("Only other players may throw in", "turn")
            if settings.neighbor_throw_only:
                if user.id not in _neighbor_user_ids(game, defender_id):
                    raise GameError("Only neighbors may throw in", "rules")
        if not card_ids:
            raise GameError("No cards", "cards")
        cards = _cards_in_hand(game, user, card_ids)
        allowed_ranks = _table_attack_ranks(game)
        for c in cards:
            if int(c.rank.value) not in allowed_ranks:
                raise GameError(
                    f"Card rank must match table (got {c.rank.name}={c.rank.value}; "
                    f"allowed values: {sorted(allowed_ranks)})",
                    "cards",
                )
        max_cards = _defender_hand_size(game, defender_id)
        on_table = TableCard.objects.filter(game=game).count()
        if on_table + len(cards) > max_cards:
            raise GameError("Too many cards on table", "rules")

    turn = _ensure_turn(game, user)
    for c in cards:
        ph = PlayerHand.objects.get(game=game, player=user, card=c)
        ph.remove_from_hand()
        tc = TableCard.objects.create(game=game, attack_card=c)
        Move.objects.create(turn=turn, table_card=tc, action_type="attack")

    _refresh_card_counts(game)
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)


def _cards_in_hand(game: Game, user: User, card_ids: Iterable[UUID]) -> list[Card]:
    ids = list(card_ids)
    hands = list(
        PlayerHand.objects.filter(game=game, player=user, card_id__in=ids).select_related(
            "card__rank"
        )
    )
    if len(hands) != len(ids):
        raise GameError("Invalid hand cards", "cards")
    return [h.card for h in hands]


@transaction.atomic
def seal_attack(game: Game, user: User):
    """Legacy no-op: defense can start during ``build`` without a separate seal step.

    Kept for API compatibility.
    """
    if game.status != "in_progress":
        raise GameError("Game not active", "finished")
    rs = _rs(game)
    if UUID(rs["attacker_id"]) != user.id:
        raise GameError("Only attacker can seal", "turn")
    if rs.get("phase") not in (PHASE_BUILD, PHASE_DEFEND):
        raise GameError("Not in attack wave", "phase")
    if not TableCard.objects.filter(game=game).exists():
        raise GameError("Nothing to seal", "state")
    broadcast_game(game.id, "game_update", {})


@transaction.atomic
def defend(game: Game, user: User, table_card_id: UUID, card_id: UUID):
    """Cover a single attack row with a legal defense card.

    Args:
        game: Active game during the table wave (``build`` or legacy ``defend``).
        user: Defender.
        table_card_id: Row to beat.
        card_id: Card from defender's hand.

    Raises:
        GameError: If the defense is illegal or row already covered.
    """
    if game.status != "in_progress":
        raise GameError("Game not active", "finished")
    rs = _rs(game)
    if UUID(rs["defender_id"]) != user.id:
        raise GameError("Only defender acts", "turn")
    if rs.get("phase") not in (PHASE_BUILD, PHASE_DEFEND):
        raise GameError("Not defense phase", "phase")
    tc = TableCard.objects.select_related("attack_card").get(game=game, id=table_card_id)
    if tc.defense_card_id:
        raise GameError("Already defended", "state")
    defense_card = PlayerHand.objects.get(game=game, player=user, card_id=card_id).card
    trump = game.trump_card.suit
    if not tc.is_valid_defense(defense_card, trump):
        raise GameError("Illegal defense card", "cards")
    ph = PlayerHand.objects.get(game=game, player=user, card=defense_card)
    ph.remove_from_hand()
    tc.defense_card = defense_card
    tc.save(update_fields=["defense_card"])
    turn = _ensure_turn(game, user)
    Move.objects.create(turn=turn, table_card=tc, action_type="defend")
    _refresh_card_counts(game)
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)


@transaction.atomic
def take_table(game: Game, user: User):
    """Defender picks up the whole table; hands refill from the deck.

    Args:
        game: Active game in ``defend``.
        user: Defender.

    Raises:
        GameError: If phase or role is wrong.
    """
    if game.status != "in_progress":
        raise GameError("Game not active", "finished")
    rs = _rs(game)
    if UUID(rs["defender_id"]) != user.id:
        raise GameError("Only defender may take", "turn")
    if rs.get("phase") not in (PHASE_BUILD, PHASE_DEFEND):
        raise GameError("Not defense phase", "phase")
    if not TableCard.objects.filter(game=game).exists():
        raise GameError("Table empty", "state")

    turn = _ensure_turn(game, user)
    for tc in TableCard.objects.filter(game=game):
        Move.objects.create(turn=turn, table_card=tc, action_type="pickup")

    _clear_table_to_hand(game, user)
    _save_rs(game, phase=PHASE_BETWEEN)
    attacker = UUID(rs["attacker_id"])
    _draw_round_after_discard(game, attacker)
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)


@transaction.atomic
def bito(game: Game, user: User):
    """Attacker confirms successful defense; discards table and rotates roles.

    Args:
        game: Active game where every row is defended.
        user: Primary attacker.

    Raises:
        GameError: If any row is still open or caller is not the attacker.
    """
    if game.status != "in_progress":
        raise GameError("Game not active", "finished")
    rs = _rs(game)
    if UUID(rs["attacker_id"]) != user.id:
        raise GameError("Only attacker can call bito", "turn")
    if rs.get("phase") not in (PHASE_BUILD, PHASE_DEFEND):
        raise GameError("Wrong phase", "phase")
    if not _all_defended(game):
        raise GameError("Not all cards defended", "state")

    _clear_table_to_discard(game)
    old_att = UUID(rs["attacker_id"])
    _rotate_roles_after_success(game)
    _draw_round_after_discard(game, old_att)
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)
