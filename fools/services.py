"""Business logic for multiplayer Durak (podkidnoy).

This module owns lobby lifecycle, dealing from the shared card pool, table
phases (build / defend / between), and persistence updates on existing Django
models. It also triggers WebSocket broadcasts via :mod:`fools.realtime`.

Typical flow:
    #. Players create or join a lobby, toggle ready, owner calls ``start_game``.
    #. Attacker opens from ``between`` into ``build``. While the wave is on the table,
       the defender may ``defend`` or ``take_table`` at any time; the attacker and
       other players may still ``play_attack`` (throw-ins) in parallel—no separate
       ``defend`` phase gate. ``take_table`` only declares the take: the cards move
       after every player who can still throw in confirms with ``pass_throw``.
    #. After the table is fully beaten, attacker ``bito`` discards and rotates roles.
"""

from __future__ import annotations

import secrets
import time
from typing import Iterable
from uuid import UUID

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from fools.models import (
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
from fools.card_catalog import ensure_playing_cards_for_deck_size
from fools.realtime import broadcast_game, broadcast_lobby, broadcast_lobby_list

User = get_user_model()

PHASE_BUILD = "build"
PHASE_DEFEND = "defend"
PHASE_BETWEEN = "between"
PHASE_TAKING = "taking"


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
    rs["version"] = int(rs.get("version") or 0) + 1
    game.runtime_state = rs
    game.save(update_fields=["runtime_state"])


def _announce_cards(game: Game, user: User, action: str, cards: list[Card]):
    """Publish a card that is already being placed on the table.

    Only those cards are included. The rest of anyone's hand stays hidden.
    There is no pause; taking, passing, and ending the wave use
    :func:`_announce_action`.

    Args:
        game: Match being shown.
        user: Seat that played the cards.
        action: ``attack`` or ``defend``.
        cards: Cards moving onto the table.
    """
    broadcast_game(
        game.id,
        "play_announce",
        {
            "action": action,
            "user_id": str(user.id),
            "username": user.username,
            "cards": [_card_json(card) for card in cards],
        },
    )


def _announce_action(game: Game, user: User, action: str, cards: list[Card] | None = None):
    """Tell the table who is about to take, pass, or end the wave, then pause.

    The cards stay put until the caller changes them. ``TABLE_ACTION_DELAY``
    is the pause in seconds; tests set it to zero.

    Args:
        game: Match being shown.
        user: Seat the label belongs to.
        action: ``take``, ``bito``, or ``transfer``.
        cards: Cards named on a transfer. Omitted for take and bito.
    """
    payload = {
        "action": action,
        "user_id": str(user.id),
        "username": user.username,
    }
    if cards:
        payload["cards"] = [_card_json(card) for card in cards]
    broadcast_game(game.id, "play_announce", payload)
    delay = float(getattr(django_settings, "TABLE_ACTION_DELAY", 0))
    if delay > 0:
        time.sleep(delay)


def _refresh_card_counts(game: Game):
    for gp in game.players.all():
        n = PlayerHand.objects.filter(fools=game, player=gp.user).count()
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
        trump_suit_id: Primary key of the trump :class:`~fools.models.CardSuit`.

    Returns:
        UUID of the user who should attack first.
    """
    best: tuple[int, int, UUID] | None = None
    for gp in _player_circle(game):
        trumps = (
            PlayerHand.objects.filter(fools=game, player=gp.user, card__suit_id=trump_suit_id)
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
        gp = GamePlayer.objects.get(fools=game, user=user)
        if gp.cards_remaining >= target_hand:
            break
        entry = GameDeck.get_top_card(game)
        if not entry:
            break
        card = entry.card
        entry.delete()
        max_order = PlayerHand.objects.filter(fools=game, player=user).aggregate(
            m=Max("order_in_hand")
        )["m"]
        next_order = (max_order or 0) + 1
        PlayerHand.objects.create(
            fools=game,
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
    deck_empty = not GameDeck.objects.filter(fools=game).exists()
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
        publish_lobby_list(lobby.id)


def release_finished_seats(game: Game):
    """Skip players who are out once the deck is empty.

    A player with no cards is not asked to open the next attack or to
    defend it. A wave that is already on the table is left as it is, and
    no cards are drawn here.

    Args:
        game: In-progress match, or a match that may have just ended.
    """
    if game.status != "in_progress":
        return
    if GameDeck.objects.filter(fools=game).exists():
        return
    _refresh_card_counts(game)
    _maybe_finish_game(game)
    game.refresh_from_db()
    if game.status != "in_progress":
        return
    rs = _rs(game)
    if rs.get("phase") != PHASE_BETWEEN or "attacker_id" not in rs:
        return
    circle = _player_circle(game)
    holding = {row.user_id for row in circle if row.cards_remaining > 0}
    if len(holding) < 2:
        _maybe_finish_game(game)
        return
    start = next(i for i, row in enumerate(circle) if row.user_id == UUID(rs["attacker_id"]))
    new_att = None
    for step in range(len(circle)):
        person = circle[(start + step) % len(circle)]
        if person.user_id in holding:
            new_att = person.user_id
            break
    seat = next(i for i, row in enumerate(circle) if row.user_id == new_att)
    new_def = None
    for step in range(1, len(circle)):
        person = circle[(seat + step) % len(circle)]
        if person.user_id in holding:
            new_def = person.user_id
            break
    if new_att is None or new_def is None:
        return
    if str(new_att) == str(rs.get("attacker_id")) and str(new_def) == str(rs.get("defender_id")):
        return
    _save_rs(
        game,
        attacker_id=str(new_att),
        defender_id=str(new_def),
        phase=PHASE_BETWEEN,
    )
    broadcast_game(game.id, "game_update", {})


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
    for tc in TableCard.objects.filter(fools=game).order_by("id"):
        cards.append(tc.attack_card)
        if tc.defense_card:
            cards.append(tc.defense_card)
    TableCard.objects.filter(fools=game).delete()
    if cards:
        DiscardPile.discard_cards(game, cards)


def _clear_table_to_hand(game: Game, user: User):
    for tc in TableCard.objects.filter(fools=game).order_by("id"):
        for c in (tc.attack_card, tc.defense_card):
            if not c:
                continue
            max_order = PlayerHand.objects.filter(fools=game, player=user).aggregate(
                m=Max("order_in_hand")
            )["m"]
            next_order = (max_order or 0) + 1
            PlayerHand.objects.create(
                fools=game,
                player=user,
                card=c,
                order_in_hand=next_order,
            )
    TableCard.objects.filter(fools=game).delete()
    _refresh_card_counts(game)


def _table_attack_ranks(game: Game) -> set[int]:
    """Ranks that may be used for throw-ins: any rank shown on the table (attack or defense).

    Classic podkidnoy allows matching ranks from beaten pairs, not only the original attacks.

    Resolves ranks via :class:`~fools.models.Card` rows (not multi-hop ``values_list`` on
    nullable defense FKs) so every card on the table contributes reliably.
    """
    pairs = TableCard.objects.filter(fools=game).values_list(
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
    return PlayerHand.objects.filter(fools=game, player_id=defender_id).count()


def attack_cap(game: Game) -> int:
    """Return how many attacking cards the table may hold.

    Before any card has gone to the discard pile the cap is 5.
    After that first successful defense it is 6.

    Args:
        game: Active game.

    Returns:
        5 or 6.
    """
    if DiscardPile.objects.filter(fools=game).exists():
        return 6
    return 5


def _reject_if_defender_cannot_cover(game: Game, defender_id: UUID, new_cards: int):
    """Reject a throw the defender cannot cover, or that passes the table cap.

    Several cards may be added at once. Uncovered attacks plus the new
    cards must fit in the defender's current hand. Beaten attacks do not
    spend that hand. The table also never holds more attacking cards
    than :func:`attack_cap`.

    Args:
        game: Active game.
        defender_id: Defender whose hand sets the limit.
        new_cards: How many attack cards are about to be added.

    Raises:
        GameError: When the hand or the cap would be exceeded.
    """
    hand = _defender_hand_size(game, defender_id)
    if _count_undefended(game) + new_cards > hand:
        raise GameError(
            "The defender does not have enough cards for that many.",
            "rules",
        )
    cap = attack_cap(game)
    on_table = TableCard.objects.filter(fools=game).count()
    if on_table + new_cards > cap:
        raise GameError(
            "No more than %d attacking cards on the table." % cap,
            "rules",
        )


def _count_undefended(game: Game) -> int:
    return TableCard.objects.filter(fools=game, defense_card__isnull=True).count()


def _all_defended(game: Game) -> bool:
    qs = TableCard.objects.filter(fools=game)
    return qs.exists() and not qs.filter(defense_card__isnull=True).exists()


def close_lobby_if_no_humans(lobby: Lobby) -> bool:
    """Close a lobby that no longer has a human member.

    Bots do not keep a table open. Any match still running there is
    finished, and bot seats are marked left so those accounts can sit
    somewhere else.

    Args:
        lobby: Lobby to inspect.

    Returns:
        True when the lobby was closed by this call.
    """
    humans = LobbyPlayer.objects.filter(lobby=lobby, user__is_bot=False).exclude(status="left")
    if humans.exists():
        return False
    from fools.bots.runner import cancel_bots

    for game in Game.objects.filter(lobby=lobby, status="in_progress"):
        cancel_bots(game.id)
        game.status = "finished"
        if game.finished_at is None:
            game.finished_at = timezone.now()
            game.save(update_fields=["status", "finished_at"])
        else:
            game.save(update_fields=["status"])
        broadcast_game(game.id, "game_finished", {"loser_id": str(game.loser_id) if game.loser_id else None})
    LobbyPlayer.objects.filter(lobby=lobby).exclude(status="left").update(status="left")
    if lobby.status != "closed":
        lobby.status = "closed"
        lobby.save(update_fields=["status"])
    broadcast_lobby(lobby.id, "lobby_closed", {"lobby_id": str(lobby.id)})
    publish_lobby_list(lobby.id)
    return True


def close_abandoned_bot_lobbies():
    """Close every open lobby whose remaining members are only bots.

    A human who already left does not count. Used before seating bots
    so a new table can reuse accounts stuck in an empty room.
    """
    open_lobbies = Lobby.objects.exclude(status="closed")
    for lobby in open_lobbies:
        close_lobby_if_no_humans(lobby)


def publish_lobby_list(lobby_id):
    """Queue a public-list update for after the current transaction commits.

    A waiting public lobby with someone still in it is upserted. Anything
    else (private, playing, closed, or empty) is removed. The snapshot is
    the same one the list API returns.

    Args:
        lobby_id: Lobby to re-evaluate.
    """
    lobby_key = str(lobby_id)

    def send():
        try:
            lobby = Lobby.objects.select_related("settings").get(pk=lobby_key)
        except Lobby.DoesNotExist:
            broadcast_lobby_list("lobby_removed", {"id": lobby_key})
            return
        still_there = lobby.players.filter(user__is_bot=False).exclude(status="left").exists()
        if lobby.is_private or lobby.status != "waiting" or not still_there:
            broadcast_lobby_list("lobby_removed", {"id": lobby_key})
            return
        broadcast_lobby_list("lobby_upsert", serialize_lobby(lobby))

    transaction.on_commit(send)


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
    fill_with_bots: bool = False,
    turn_time_limit: int | None = None,
) -> Lobby:
    """Create a lobby, default :class:`~fools.models.LobbySettings`, and owner seat.

    Args:
        owner: Authenticated user who becomes lobby owner.
        name: Display name.
        is_private: Whether a password is required to join.
        password: Plain text; stored hashed when private.
        max_players: Upper bound enforced by :meth:`fools.models.Lobby.is_full`.
        card_count: Deck size (24, 36, or 52).
        is_transferable: Defender may pass an unbeaten attack to the next seat.
        neighbor_throw_only: Restrict throw-in to defender's neighbors.
        allow_jokers: Whether jokers may appear in the shoe (requires data).
        fill_with_bots: Seat bots in empty chairs when the game starts.
        turn_time_limit: Optional per-turn cap in seconds.

    Returns:
        The newly created :class:`~fools.models.Lobby` instance.
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
        fill_with_bots=fill_with_bots,
        turn_time_limit=turn_time_limit,
    )
    LobbyPlayer.objects.create(lobby=lobby, user=owner, status="waiting")
    get_lobby_chat(lobby)
    broadcast_lobby(lobby.id, "lobby_created", {"lobby_id": str(lobby.id)})
    publish_lobby_list(lobby.id)
    return lobby


@transaction.atomic
def join_lobby(lobby: Lobby, user: User, password: str | None = None) -> LobbyPlayer:
    """Add ``user`` to ``lobby`` or reactivate a previously left membership.

    Args:
        lobby: Target lobby.
        user: Joining user.
        password: Required plaintext password when ``lobby.is_private``.

    Returns:
        The active :class:`~fools.models.LobbyPlayer` row.

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
            raise GameError("That password is incorrect.", "auth")
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
    publish_lobby_list(lobby.id)
    return lp


@transaction.atomic
def leave_lobby(lobby: Lobby, user: User) -> dict:
    """Mark every active membership of ``user`` in ``lobby`` as left.

    If a match is still running, the leaver forfeits it. Bots do not keep
    the lobby open: when no human remains, the lobby is closed. If the
    owner leaves and another human stays, ownership moves to that human.

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

    game = Game.objects.filter(
        lobby=lobby, status="in_progress", players__user=user
    ).first()
    if game is not None:
        abandon_game(game, user)

    lobby_closed = False
    new_owner_id: str | None = None
    if close_lobby_if_no_humans(lobby):
        lobby_closed = True
    elif was_owner:
        next_lp = (
            LobbyPlayer.objects.filter(lobby=lobby, user__is_bot=False)
            .exclude(status="left")
            .order_by("user__username")
            .first()
        )
        if next_lp is not None:
            lobby.owner = next_lp.user
            lobby.save(update_fields=["owner"])
            new_owner_id = str(next_lp.user_id)

    broadcast_lobby(lobby.id, "player_left", {"user_id": str(user.id)})
    publish_lobby_list(lobby.id)
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
    """Deal cards, set trump, and spawn an in-progress :class:`~fools.models.Game`.

    Args:
        lobby: Must be in ``waiting`` with at least two ``ready`` members.
        user: Lobby owner (only owners may start).

    Returns:
        Fresh :class:`~fools.models.Game` in ``between`` phase.

    Raises:
        GameError: On permission, deck data, duplicate active fools, or rules.
    """
    if lobby.owner_id != user.id:
        raise GameError("Only owner can start", "forbidden")
    if Game.objects.filter(lobby=lobby, status="in_progress").exists():
        raise GameError("Game already in progress", "state")
    if lobby.settings.fill_with_bots:
        from fools.bots.seating import fill_empty_seats

        fill_empty_seats(lobby)
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
        GameDeck.objects.create(fools=game, card_id=cid, position=pos)
    # The trump is the bottom card. It is dealt only when the deck reaches it.
    GameDeck.objects.create(fools=game, card_id=trump_id, position=len(rest))

    for seat, lp in enumerate(ready_players, start=1):
        GamePlayer.objects.create(
            fools=game,
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
                fools=game,
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
    publish_lobby_list(lobby.id)
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
    members = list(lobby.players.exclude(status="left").select_related("user"))
    human_count = sum(1 for row in members if not row.user.is_bot)
    bot_count = sum(1 for row in members if row.user.is_bot)
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
            "fill_with_bots": settings.fill_with_bots,
            "turn_time_limit": settings.turn_time_limit,
        },
        "players": [
            {
                "user_id": str(row.user_id),
                "username": row.user.username,
                "status": row.status,
                "is_bot": row.user.is_bot,
            }
            for row in members
        ],
        "active_game_id": _active_game_id(lobby),
        "can_start": lobby.can_start_game(),
        "ready_count": sum(1 for row in members if row.status == "ready"),
        "active_player_count": len(members),
        "human_count": human_count,
        "bot_count": bot_count,
    }


def _active_game_id(lobby: Lobby) -> str | None:
    g = Game.objects.filter(lobby=lobby, status="in_progress").order_by("-started_at").first()
    return str(g.id) if g else None


def serialize_game(game: Game, viewer: User) -> dict:
    """Return fools state visible to ``viewer`` (only their hand is revealed).

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
    for tc in TableCard.objects.filter(fools=game).select_related(
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
                for ph in PlayerHand.objects.filter(fools=game, player=gp.user)
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
    deck_left = GameDeck.objects.filter(fools=game).count()
    trump_in_deck = GameDeck.objects.filter(fools=game, card_id=game.trump_card_id).exists()
    discarded = DiscardPile.objects.filter(fools=game).select_related("card__suit", "card__rank")
    top_discard = discarded.order_by("-position", "-id").first()
    return {
        "id": str(game.id),
        "lobby_id": str(game.lobby_id),
        "status": game.status,
        "transferable": bool(game.lobby.settings.is_transferable),
        "neighbor_throw_only": bool(game.lobby.settings.neighbor_throw_only),
        "trump_card": _card_json(trump),
        "trump_in_deck": trump_in_deck,
        "deck_remaining": deck_left,
        "discard_count": discarded.count(),
        "discard_top": _card_json(top_discard.card) if top_discard else None,
        "runtime": {
            "attacker_id": rs.get("attacker_id"),
            "defender_id": rs.get("defender_id"),
            "phase": rs.get("phase"),
            "version": int(rs.get("version") or 0),
            "pending_ids": [str(uid) for uid in pending_passers(game)]
            if rs.get("phase") == PHASE_TAKING
            else [],
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
    if phase not in (PHASE_BUILD, PHASE_BETWEEN, PHASE_DEFEND, PHASE_TAKING):
        raise GameError("Cannot attack now", "phase")

    settings = game.lobby.settings
    attacker_id = UUID(rs["attacker_id"])
    defender_id = UUID(rs["defender_id"])

    if phase == PHASE_BETWEEN:
        if user.id != attacker_id:
            raise GameError("Only attacker may open", "turn")
        if TableCard.objects.filter(fools=game).exists():
            raise GameError("Table must be empty", "state")
        if not card_ids:
            raise GameError("Play at least one card", "cards")
        cards = _cards_in_hand(game, user, card_ids)
        ranks = {c.rank_id for c in cards}
        if len(ranks) != 1:
            raise GameError("Attack cards must share rank", "cards")
        _reject_if_defender_cannot_cover(game, defender_id, len(cards))
        _save_rs(game, phase=PHASE_BUILD)
    else:
        if user.id == defender_id:
            raise GameError("Defender cannot attack", "turn")
        if user.id != attacker_id:
            if phase not in (PHASE_BUILD, PHASE_DEFEND, PHASE_TAKING):
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
        _reject_if_defender_cannot_cover(game, defender_id, len(cards))

    turn = _ensure_turn(game, user)
    for c in cards:
        ph = PlayerHand.objects.get(fools=game, player=user, card=c)
        ph.remove_from_hand()
        tc = TableCard.objects.create(fools=game, attack_card=c)
        Move.objects.create(turn=turn, table_card=tc, action_type="attack")

    _refresh_card_counts(game)
    if phase == PHASE_TAKING:
        _save_rs(game, passed_ids=[])
    else:
        _save_rs(game)
    _announce_cards(game, user, "attack", cards)
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)


def _cards_in_hand(game: Game, user: User, card_ids: Iterable[UUID]) -> list[Card]:
    ids = list(card_ids)
    hands = list(
        PlayerHand.objects.filter(fools=game, player=user, card_id__in=ids).select_related(
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
    if not TableCard.objects.filter(fools=game).exists():
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
    if rs.get("phase") == PHASE_TAKING:
        raise GameError("You are already taking the cards", "phase")
    if rs.get("phase") not in (PHASE_BUILD, PHASE_DEFEND):
        raise GameError("Not defense phase", "phase")
    tc = TableCard.objects.select_related("attack_card").get(fools=game, id=table_card_id)
    if tc.defense_card_id:
        raise GameError("Already defended", "state")
    defense_card = PlayerHand.objects.get(fools=game, player=user, card_id=card_id).card
    trump = game.trump_card.suit
    if not tc.is_valid_defense(defense_card, trump):
        raise GameError("Illegal defense card", "cards")
    ph = PlayerHand.objects.get(fools=game, player=user, card=defense_card)
    ph.remove_from_hand()
    tc.defense_card = defense_card
    tc.save(update_fields=["defense_card"])
    turn = _ensure_turn(game, user)
    Move.objects.create(turn=turn, table_card=tc, action_type="defend")
    _refresh_card_counts(game)
    _save_rs(game)
    _announce_cards(game, user, "defend", [defense_card])
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)


@transaction.atomic
def transfer_attack(game: Game, user: User, card_ids: list[UUID]):
    """Pass an unbeaten attack to the next seat with cards of the same rank.

    Allowed only when the lobby is transferable, every attack on the table
    shares one rank, nothing has been beaten yet, and the next player holds
    enough cards for the pile after the pass. The original attacker stays.

    Args:
        game: Active game.
        user: Current defender.
        card_ids: Cards from the defender's hand, all of the attack rank.

    Raises:
        GameError: When transfer is illegal for the rules or the position.
    """
    if game.status != "in_progress":
        raise GameError("Game not active", "finished")
    settings = game.lobby.settings
    if not settings.is_transferable:
        raise GameError("Transfers are not allowed", "rules")
    rs = _rs(game)
    if UUID(rs["defender_id"]) != user.id:
        raise GameError("Only defender may transfer", "turn")
    if rs.get("phase") not in (PHASE_BUILD, PHASE_DEFEND):
        raise GameError("Not defense phase", "phase")
    rows = list(TableCard.objects.filter(fools=game).select_related("attack_card__rank"))
    if not rows:
        raise GameError("Table empty", "state")
    if any(row.defense_card_id for row in rows):
        raise GameError("Cannot transfer after a card is beaten", "rules")
    attack_ranks = {int(row.attack_card.rank.value) for row in rows}
    if len(attack_ranks) != 1:
        raise GameError("You can only pass an attack of one rank.", "rules")
    rank = next(iter(attack_ranks))
    cards = _cards_in_hand(game, user, card_ids)
    for card in cards:
        if int(card.rank.value) != rank:
            raise GameError("Transfer cards must match the attack rank.", "cards")
    players = _player_circle(game)
    index = next(i for i, row in enumerate(players) if row.user_id == user.id)
    nxt = players[(index + 1) % len(players)]
    if nxt.user_id == user.id:
        raise GameError("Nobody to transfer to", "rules")
    needed = len(rows) + len(cards)
    held = PlayerHand.objects.filter(fools=game, player_id=nxt.user_id).count()
    if held < needed:
        raise GameError("Next player cannot take the transfer", "rules")
    cap = attack_cap(game)
    if needed > cap:
        raise GameError("No more than %d attacking cards on the table." % cap, "rules")
    _announce_action(game, user, "transfer", cards)
    turn = _ensure_turn(game, user)
    for card in cards:
        ph = PlayerHand.objects.get(fools=game, player=user, card=card)
        ph.remove_from_hand()
        table_card = TableCard.objects.create(fools=game, attack_card=card)
        Move.objects.create(turn=turn, table_card=table_card, action_type="attack")
    _save_rs(game, defender_id=str(nxt.user_id), phase=PHASE_BUILD)
    _refresh_card_counts(game)
    broadcast_game(game.id, "game_update", {})


def throw_seat_ids(game: Game) -> set[UUID]:
    """Return seats that may add cards, besides the defender.

    The attacker is always included. With the neighbor rule, only the
    seats beside the defender are included as well.

    Args:
        game: Active game with attacker and defender set.

    Returns:
        User ids allowed to throw in.
    """
    rs = _rs(game)
    attacker_id = UUID(rs["attacker_id"])
    defender_id = UUID(rs["defender_id"])
    settings = game.lobby.settings
    allowed = {attacker_id}
    others = {row.user_id for row in _player_circle(game)} - {attacker_id, defender_id}
    if settings.neighbor_throw_only:
        allowed |= _neighbor_user_ids(game, defender_id) & others
    else:
        allowed |= others
    allowed.discard(defender_id)
    return allowed


def pending_passers(game: Game) -> list[UUID]:
    """Return throwers who still must confirm during a take.

    A seat with no cards is skipped. Anyone already recorded in
    ``passed_ids`` is skipped.

    Args:
        game: Match that may be in the taking phase.

    Returns:
        User ids, in seat order, who have not confirmed.
    """
    if _rs(game).get("phase") != PHASE_TAKING:
        return []
    passed = {str(item) for item in (_rs(game).get("passed_ids") or [])}
    pending = []
    for row in _player_circle(game):
        if row.user_id not in throw_seat_ids(game):
            continue
        if str(row.user_id) in passed:
            continue
        if not PlayerHand.objects.filter(fools=game, player_id=row.user_id).exists():
            continue
        pending.append(row.user_id)
    return pending


def _complete_take(game: Game, user: User):
    """Move the table into the defender's hand and refill from the deck.

    Args:
        game: Match whose take has been confirmed.
        user: Defender who declared the take.
    """
    rs = _rs(game)
    turn = _ensure_turn(game, user)
    for tc in TableCard.objects.filter(fools=game):
        Move.objects.create(turn=turn, table_card=tc, action_type="pickup")
    _clear_table_to_hand(game, user)
    _save_rs(game, phase=PHASE_BETWEEN, passed_ids=[])
    _draw_round_after_discard(game, UUID(rs["attacker_id"]))
    release_finished_seats(game)
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)


@transaction.atomic
def take_table(game: Game, user: User):
    """Defender declares that they will pick up the table.

    The cards stay on the table until every player who can still throw
    in adds a card or confirms they are done. A player with no cards is
    not asked.

    Args:
        game: Active game during the wave.
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
    if not TableCard.objects.filter(fools=game).exists():
        raise GameError("Table empty", "state")

    _announce_action(game, user, "take")
    _save_rs(game, phase=PHASE_TAKING, passed_ids=[])
    if pending_passers(game):
        broadcast_game(game.id, "game_update", {})
        return
    _complete_take(game, user)


@transaction.atomic
def pass_throw(game: Game, user: User):
    """Confirm that this seat will not throw any more cards into a take.

    When no eligible seat is still pending, the defender receives the table.

    Args:
        game: Match in the taking phase.
        user: Attacker or other thrower.

    Raises:
        GameError: When this seat cannot confirm.
    """
    if game.status != "in_progress":
        raise GameError("Game not active", "finished")
    rs = _rs(game)
    if rs.get("phase") != PHASE_TAKING:
        raise GameError("Nobody is taking the cards", "phase")
    if user.id not in throw_seat_ids(game):
        raise GameError("You cannot throw in", "turn")
    if not PlayerHand.objects.filter(fools=game, player=user).exists():
        raise GameError("You have no cards to hold back", "turn")
    passed = [str(item) for item in (rs.get("passed_ids") or [])]
    if str(user.id) not in passed:
        passed.append(str(user.id))
        _save_rs(game, passed_ids=passed)
    broadcast_game(
        game.id,
        "play_announce",
        {"action": "pass", "user_id": str(user.id), "username": user.username},
    )
    if pending_passers(game):
        broadcast_game(game.id, "game_update", {})
        return
    defender = game.players.get(user_id=rs["defender_id"]).user
    _complete_take(game, defender)


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

    _announce_action(game, user, "bito")
    _clear_table_to_discard(game)
    old_att = UUID(rs["attacker_id"])
    _rotate_roles_after_success(game)
    _draw_round_after_discard(game, old_att)
    release_finished_seats(game)
    broadcast_game(game.id, "game_update", {})
    _maybe_finish_game(game)


@transaction.atomic
def abandon_game(game: Game, user: User) -> Game:
    """Forfeit an in-progress match. The leaver becomes the fool.

    The leaver is removed from the lobby immediately, even when other
    people are still in it. Bots do not keep a lobby open: if no human
    remains, it is closed. A finished match is left as it is.

    Args:
        game: Match the player is seated in.
        user: Player who is leaving.

    Returns:
        The same game after the forfeit, when one was applied.

    Raises:
        GameError: When ``user`` is not seated.
    """
    if not game.players.filter(user=user).exists():
        raise GameError("Not a player in this game", "forbidden")
    if game.status != "in_progress":
        return game
    from fools.bots.runner import cancel_bots

    cancel_bots(game.id)
    game.status = "finished"
    game.loser = user
    game.finished_at = timezone.now()
    game.save(update_fields=["status", "loser", "finished_at"])
    lobby = game.lobby
    was_owner = lobby.owner_id == user.id
    LobbyPlayer.objects.filter(lobby=lobby, user=user).update(status="left")
    LobbyPlayer.objects.filter(lobby=lobby, status="playing").exclude(user=user).update(status="waiting")
    if not close_lobby_if_no_humans(lobby):
        lobby.status = "waiting"
        update_fields = ["status"]
        if was_owner:
            nxt = (
                LobbyPlayer.objects.filter(lobby=lobby, user__is_bot=False)
                .exclude(status="left")
                .order_by("user__username")
                .first()
            )
            if nxt is not None:
                lobby.owner = nxt.user
                update_fields.append("owner")
        lobby.save(update_fields=update_fields)
    broadcast_game(game.id, "game_finished", {"loser_id": str(user.id)})
    broadcast_lobby(lobby.id, "game_finished", {"game_id": str(game.id)})
    publish_lobby_list(lobby.id)
    return game
