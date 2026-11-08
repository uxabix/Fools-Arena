"""Canonical playing-card catalog: dedupe rows and ensure a full shoe exists.

Used by ``init_game_data`` and by :func:`game.services.start_game` when the DB
is missing cards. Merges duplicate ``CardSuit`` (same name), ``CardRank`` (same
value), and normal ``Card`` rows (same suit + rank, ``special_card`` NULL).
"""

from __future__ import annotations

from typing import List, Tuple

from django.db import transaction
from django.db.models import Count

from game.models import Card, CardRank, CardSuit, DiscardPile, Game, GameDeck, PlayerHand, TableCard


def ranks_for_deck_size(size: int) -> List[Tuple[str, int]]:
    """Return (name, value) rank rows for a 24 / 36 / 52-card shoe."""
    face = [("Jack", 11), ("Queen", 12), ("King", 13), ("Ace", 14)]
    if size == 52:
        numeric = [(str(i), i) for i in range(2, 11)]
        return numeric + face
    if size == 36:
        numeric = [(str(i), i) for i in range(6, 11)]
        return numeric + face
    if size == 24:
        numeric = [("9", 9), ("10", 10)]
        return numeric + face
    raise ValueError(f"Unsupported deck size: {size}")


CANONICAL_SUITS: List[Tuple[str, str]] = [
    ("Hearts", "red"),
    ("Diamonds", "red"),
    ("Clubs", "black"),
    ("Spades", "black"),
]


def _reassign_card_pk(old_id, new_id) -> None:
    """Point all FKs from ``old_id`` to ``new_id``, then delete the old ``Card``.

    Bulk ``UPDATE`` on :class:`~game.models.PlayerHand` or :class:`~game.models.GameDeck`
    can violate uniqueness if the same player or deck already references ``new_id``
    (two physical duplicate rows for one suit/rank were both dealt). In that case
    drop the redundant row instead of updating it.
    """
    if old_id == new_id:
        return
    Game.objects.filter(trump_card_id=old_id).update(trump_card_id=new_id)

    for gd in GameDeck.objects.filter(card_id=old_id).order_by("id"):
        if GameDeck.objects.filter(game_id=gd.game_id, card_id=new_id).exclude(pk=gd.pk).exists():
            gd.delete()
        else:
            GameDeck.objects.filter(pk=gd.pk).update(card_id=new_id)

    for ph in PlayerHand.objects.filter(card_id=old_id).order_by("id"):
        if PlayerHand.objects.filter(game_id=ph.game_id, player_id=ph.player_id, card_id=new_id).exclude(
            pk=ph.pk
        ).exists():
            ph.delete()
        else:
            PlayerHand.objects.filter(pk=ph.pk).update(card_id=new_id)

    for tc in TableCard.objects.filter(attack_card_id=old_id).order_by("id"):
        if TableCard.objects.filter(game_id=tc.game_id, attack_card_id=new_id).exclude(pk=tc.pk).exists():
            tc.delete()
        else:
            TableCard.objects.filter(pk=tc.pk).update(attack_card_id=new_id)

    for tc in TableCard.objects.filter(defense_card_id=old_id).order_by("id"):
        if TableCard.objects.filter(game_id=tc.game_id, defense_card_id=new_id).exclude(pk=tc.pk).exists():
            tc.delete()
        else:
            TableCard.objects.filter(pk=tc.pk).update(defense_card_id=new_id)

    for dp in DiscardPile.objects.filter(card_id=old_id).order_by("id"):
        if DiscardPile.objects.filter(game_id=dp.game_id, card_id=new_id).exclude(pk=dp.pk).exists():
            dp.delete()
        else:
            DiscardPile.objects.filter(pk=dp.pk).update(card_id=new_id)

    Card.objects.filter(pk=old_id).delete()


def dedupe_card_suits() -> int:
    """Merge duplicate suits with the same ``name``; keep lowest ``id``. Returns removed count."""
    removed = 0
    names = CardSuit.objects.values_list("name", flat=True).distinct()
    for name in names:
        qs = list(CardSuit.objects.filter(name=name).order_by("id"))
        if len(qs) <= 1:
            continue
        keeper = qs[0]
        for dup in qs[1:]:
            Card.objects.filter(suit_id=dup.pk).update(suit_id=keeper.pk)
            dup.delete()
            removed += 1
    return removed


def dedupe_card_ranks() -> int:
    """Merge duplicate ranks with the same ``value``; keep lowest ``id``. Returns removed count."""
    removed = 0
    values = CardRank.objects.values_list("value", flat=True).distinct()
    for value in values:
        qs = list(CardRank.objects.filter(value=value).order_by("id"))
        if len(qs) <= 1:
            continue
        keeper = qs[0]
        for dup in qs[1:]:
            Card.objects.filter(rank_id=dup.pk).update(rank_id=keeper.pk)
            dup.delete()
            removed += 1
    return removed


def dedupe_normal_playing_cards() -> int:
    """Merge duplicate normal cards (same suit + rank); keep smallest ``id``. Returns removed count."""
    removed = 0
    keys = (
        Card.objects.filter(special_card__isnull=True)
        .values("suit_id", "rank_id")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    for row in keys:
        qs = list(
            Card.objects.filter(
                suit_id=row["suit_id"],
                rank_id=row["rank_id"],
                special_card__isnull=True,
            ).order_by("id")
        )
        keeper_id = qs[0].pk
        for dup in qs[1:]:
            _reassign_card_pk(dup.pk, keeper_id)
            removed += 1
    return removed


def _ensure_suits_and_ranks(deck_size: int) -> tuple[list[CardSuit], list[CardRank]]:
    suits: list[CardSuit] = []
    for name, color in CANONICAL_SUITS:
        suit_obj, _ = CardSuit.objects.get_or_create(name=name, defaults={"color": color})
        if suit_obj.color != color:
            suit_obj.color = color
            suit_obj.save(update_fields=["color"])
        suits.append(suit_obj)

    rank_rows = ranks_for_deck_size(deck_size)
    ranks: list[CardRank] = []
    for name, value in rank_rows:
        rank_obj, _ = CardRank.objects.get_or_create(value=value, defaults={"name": name})
        if rank_obj.name != name:
            rank_obj.name = name
            rank_obj.save(update_fields=["name"])
        ranks.append(rank_obj)
    return suits, ranks


def _create_missing_cards(suits: list[CardSuit], ranks: list[CardRank]) -> tuple[int, int]:
    created = 0
    skipped = 0
    for suit in suits:
        for rank in ranks:
            exists = Card.objects.filter(suit=suit, rank=rank, special_card__isnull=True).exists()
            if exists:
                skipped += 1
                continue
            Card.objects.create(suit=suit, rank=rank)
            created += 1
    return created, skipped


@transaction.atomic
def ensure_playing_cards_for_deck_size(deck_size: int) -> dict:
    """Dedupe catalog rows, then create any missing standard cards for ``deck_size``.

    Args:
        deck_size: One of ``24``, ``36``, ``52``.

    Returns:
        Stats dict with keys ``suits_removed``, ``ranks_removed``, ``cards_merged``,
        ``cards_created``, ``cards_skipped``.
    """
    if deck_size not in (24, 36, 52):
        raise ValueError(f"Unsupported deck_size: {deck_size}")

    sr = dedupe_card_suits()
    rr = dedupe_card_ranks()
    suits, ranks = _ensure_suits_and_ranks(deck_size)
    cc, sk = _create_missing_cards(suits, ranks)
    cm = dedupe_normal_playing_cards()
    return {
        "suits_removed": sr,
        "ranks_removed": rr,
        "cards_merged": cm,
        "cards_created": cc,
        "cards_skipped": sk,
    }
