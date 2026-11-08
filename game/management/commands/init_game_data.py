"""
Initialize default card suits, ranks and create Card entries.

This management command delegates to :mod:`game.card_catalog`, which merges
duplicate suits (same name), ranks (same value), and normal cards (same suit
and rank), then ensures every suit × rank pair exists for the chosen deck size.

Usage:
    python manage.py init_game_data
    python manage.py init_game_data --deck-size 36
    python manage.py init_game_data --reset

Using --reset deletes all Card, CardRank and CardSuit rows before rebuilding.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from game.card_catalog import ensure_playing_cards_for_deck_size
from game.models import Card, CardRank, CardSuit


class Command(BaseCommand):
    """Build or repair the standard playing-card catalog (24 / 36 / 52 cards)."""

    help = (
        "Initialize card suits, ranks, and cards; merge duplicates; "
        "default deck size is 52 (use 36 for classic Durak)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--deck-size",
            type=int,
            choices=[24, 36, 52],
            default=52,
            help="Deck to materialize: 24 (9-A), 36 (6-A), 52 (2-A). Default: 52.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all Card, CardRank and CardSuit rows before rebuilding.",
        )

    def handle(self, *args, **options):
        deck_size = options["deck_size"]
        do_reset = options["reset"]

        with transaction.atomic():
            if do_reset:
                self.stdout.write(
                    "Reset requested — deleting existing Cards, CardRank and CardSuit entries..."
                )
                Card.objects.all().delete()
                CardRank.objects.all().delete()
                CardSuit.objects.all().delete()
                self.stdout.write("Existing card data deleted.")

            stats = ensure_playing_cards_for_deck_size(deck_size)

        self.stdout.write(
            f"Dedupe: removed {stats['suits_removed']} duplicate suit(s), "
            f"{stats['ranks_removed']} duplicate rank(s), "
            f"merged {stats['cards_merged']} duplicate card row(s)."
        )
        self.stdout.write(
            f"Cards created: {stats['cards_created']}; already present: {stats['cards_skipped']}."
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Deck ready for deck_size={deck_size}. "
                f"Total suits: {CardSuit.objects.count()}; "
                f"ranks: {CardRank.objects.count()}; "
                f"cards: {Card.objects.count()}."
            )
        )
