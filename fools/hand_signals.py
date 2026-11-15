"""Ephemeral tells for a lifted card or a reordered hand.

The browser may report which positions in the sender's own fan are lifted,
and which sort mode that fan uses. Other seats receive those positions only.
Card ids, suits, and ranks are never stored or broadcast.

The latest tell for each seat is kept in the cache so a player who opens the
table mid-hand can see the current lifts. A cache outage still allows the
tell to be broadcast; it is simply not remembered.
"""

from __future__ import annotations

import logging

from django.core.cache import cache

from fools.models import Game, GamePlayer, LobbySettings, PlayerHand

logger = logging.getLogger(__name__)

HAND_SORTS = (
    "suit-left",
    "suit-right",
    "rank-ltr",
    "rank-rtl",
    "dealt",
    "dealt-rev",
)
HAND_SIGNAL_LIMIT = 20
HAND_SIGNAL_WINDOW = 1
_SIGNAL_TTL = 60 * 60 * 6


def signals_shared(game_id) -> bool:
    """Return whether this match may exchange hand tells.

    Args:
        game_id: Primary key of :class:`~fools.models.Game`.

    Returns:
        True when the lobby option is on and the match is still in progress.
    """
    game = _live_game(game_id)
    if game is None:
        return False
    return _settings_allow(game)


def normalize_hand_signal(payload, hand_size: int) -> dict | None:
    """Keep a sort mode and in-range indexes, or reject the whole payload.

    Args:
        payload: JSON object from the seated player. Extra keys are ignored.
        hand_size: How many cards that player actually holds.

    Returns:
        ``{"sort": str, "selected": list[int]}`` with indexes sorted, or
        ``None`` when the payload is not a legal tell.
    """
    if not isinstance(payload, dict) or hand_size < 0:
        return None
    sort = payload.get("sort")
    if sort not in HAND_SORTS:
        return None
    selected = payload.get("selected")
    if not isinstance(selected, list) or len(selected) > hand_size:
        return None
    indexes = []
    seen = set()
    for item in selected:
        if isinstance(item, bool) or not isinstance(item, int):
            return None
        if item < 0 or item >= hand_size or item in seen:
            return None
        seen.add(item)
        indexes.append(item)
    indexes.sort()
    return {"sort": sort, "selected": indexes}


def accept_hand_signal(game_id, user_id, payload) -> dict | None:
    """Validate one tell and remember it for the seat that sent it.

    The user id always comes from the socket, never from the payload.

    Args:
        game_id: Match the socket joined.
        user_id: Authenticated user primary key.
        payload: Client JSON. Card identities in it are ignored.

    Returns:
        Broadcast body ``user_id``, ``sort``, and ``selected``, or ``None``
        when the tell must be dropped.
    """
    game = _live_game(game_id)
    if game is None or not _settings_allow(game):
        return None
    if not GamePlayer.objects.filter(fools_id=game_id, user_id=user_id).exists():
        return None
    hand_size = PlayerHand.objects.filter(fools_id=game_id, player_id=user_id).count()
    parsed = normalize_hand_signal(payload, hand_size)
    if parsed is None:
        logger.info("Rejected hand signal game=%s user=%s", game_id, user_id)
        return None
    if not _under_rate_limit(game_id, user_id):
        logger.warning("Hand signal rate limit game=%s user=%s", game_id, user_id)
        return None
    _remember(game_id, user_id, parsed)
    return {
        "user_id": str(user_id),
        "sort": parsed["sort"],
        "selected": parsed["selected"],
    }


def hand_signal_snapshot(game_id) -> list[dict]:
    """Return the latest tell for every seat, when the lobby allows them.

    Args:
        game_id: Match primary key.

    Returns:
        A list of ``user_id``, ``sort``, and ``selected`` dicts. Empty when
        tells are off, or when nothing has been stored.
    """
    if not signals_shared(game_id):
        return []
    stored = _cache_get(_store_key(game_id))
    if not isinstance(stored, dict):
        return []
    rows = []
    for user_id, row in stored.items():
        if not isinstance(row, dict):
            continue
        sort = row.get("sort")
        selected = row.get("selected")
        if sort not in HAND_SORTS or not isinstance(selected, list):
            continue
        rows.append(
            {
                "user_id": str(user_id),
                "sort": sort,
                "selected": [int(index) for index in selected],
            }
        )
    return rows


def _live_game(game_id):
    """Return the in-progress match, or ``None``."""
    return (
        Game.objects.select_related("lobby__settings")
        .filter(id=game_id, status="in_progress")
        .first()
    )


def _settings_allow(game: Game) -> bool:
    """Return whether this match's lobby has hand tells turned on."""
    try:
        settings = game.lobby.settings
    except LobbySettings.DoesNotExist:
        return False
    return bool(settings.share_hand_signals)


def _store_key(game_id) -> str:
    return f"fools-hand-signals:{game_id}"


def _rate_key(game_id, user_id) -> str:
    return f"fools-hand-signal-rate:{game_id}:{user_id}"


def _under_rate_limit(game_id, user_id) -> bool:
    """Allow a short burst. If the cache is down, allow the tell."""
    key = _rate_key(game_id, user_id)
    try:
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=HAND_SIGNAL_WINDOW)
            return True
        return count <= HAND_SIGNAL_LIMIT
    except Exception:
        logger.warning(
            "Hand signal rate limit unavailable game=%s user=%s",
            game_id,
            user_id,
        )
        return True


def _remember(game_id, user_id, parsed: dict) -> None:
    """Store the latest tell. A cache failure does not block the broadcast."""
    key = _store_key(game_id)
    try:
        current = cache.get(key)
        if not isinstance(current, dict):
            current = {}
        current[str(user_id)] = parsed
        cache.set(key, current, timeout=_SIGNAL_TTL)
    except Exception:
        logger.warning("Hand signal cache write failed game=%s user=%s", game_id, user_id)


def _cache_get(key):
    try:
        return cache.get(key)
    except Exception:
        logger.warning("Hand signal cache read failed")
        return None
