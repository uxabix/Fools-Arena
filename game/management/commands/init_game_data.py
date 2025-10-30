"""
Initialize default card suits, ranks and create Card entries.

This management command will create standard card suits and ranks and then
create Card objects for each suit × rank combination for a chosen deck size.

Usage:
    python manage.py init_game_data
    python manage.py init_game_data --deck-size 36
    python manage.py init_game_data --reset

The command is idempotent by default (it uses get_or_create and updates mismatched
names/colors). Using --reset will delete existing Card, CardRank and CardSuit
records before recreating them.

Module contents:
    Command -- Django management command class implementing the behavior.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from typing import List, Tuple

from game.models import CardSuit, CardRank, Card


class Command(BaseCommand):
    """
    Django management command to initialize card suits, ranks and cards.

    The command supports 24-, 36- and 52-card decks and an optional reset flag
    which deletes existing Card, CardRank and CardSuit records before creating
    new ones.

    Attributes:
        help (str): Short description displayed by `manage.py help`.
    """

    help = "Initialize default card suits, ranks and create Card entries. Default deck: 36 (Durak)."

    def add_arguments(self, parser):
        """
        Add command-line arguments for the management command.

        Args:
            parser (argparse.ArgumentParser): The argument parser instance.

        Recognized flags:
            --deck-size {24,36,52}: Which deck to create (default 52).
            --reset: If present, deletes existing Card/Rank/Suit rows before creating.
        """
        parser.add_argument(
            "--deck-size",
            type=int,
            choices=[24, 36, 52],
            default=52,
            help="Which deck to create cards for: 24 (9-A), 36 (6-A), 52 (2-A). Default: 52.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing Card, CardRank and CardSuit records and recreate from scratch.",
        )

    def handle(self, *args, **options):
        """
        Main entry point for the management command.

        This method creates suits and ranks (using get_or_create so it is safe to
        run repeatedly), then creates Card objects for each combination of suit
        and rank. If --reset is passed, existing Card, CardRank and CardSuit
        records will be deleted first.

        Args:
            *args: Positional arguments (unused).
            **options: Command options dictionary with keys:
                deck_size (int): Deck size to create (24, 36, 52).
                reset (bool): Whether to delete existing entries first.

        Raises:
            ValueError: If an unsupported deck size is provided (shouldn't happen
                because argparse restricts choices).
        """
        deck_size = options["deck_size"]
        do_reset = options["reset"]

        # Standard four suits with their display colors.
        suits = [
            ("Hearts", "red"),
            ("Diamonds", "red"),
            ("Clubs", "black"),
            ("Spades", "black"),
        ]

        def ranks_for_deck(size: int) -> List[Tuple[str, int]]:
            """
            Return a list of (name, value) tuples representing card ranks for the given deck size.

            The returned list orders ranks from lowest to highest numeric value.

            Args:
                size (int): Deck size. Supported values: 24, 36, 52.

            Returns:
                List[Tuple[str, int]]: List of (display_name, numeric_value) for ranks.

            Raises:
                ValueError: If an unsupported deck size is supplied.
            """
            face = [("Jack", 11), ("Queen", 12), ("King", 13), ("Ace", 14)]
            if size == 52:
                # 2..10 plus face cards
                numeric = [(str(i), i) for i in range(2, 11)]
                return numeric + face
            if size == 36:
                # 6..10 plus face cards (typical Durak deck)
                numeric = [(str(i), i) for i in range(6, 11)]
                return numeric + face
            if size == 24:
                # 9..10 plus face cards (short deck)
                numeric = [("9", 9), ("10", 10)]
                return numeric + face
            raise ValueError("Unsupported deck size")

        ranks = ranks_for_deck(deck_size)

        with transaction.atomic():
            if do_reset:
                self.stdout.write("Reset requested — deleting existing Cards, CardRank and CardSuit entries...")
                # Delete Cards first because of foreign key references to ranks & suits
                Card.objects.all().delete()
                CardRank.objects.all().delete()
                CardSuit.objects.all().delete()
                self.stdout.write("Existing card data deleted.")

            # Create or update suits
            created_suits = []
            for name, color in suits:
                suit_obj, created = CardSuit.objects.get_or_create(name=name, defaults={"color": color})
                # If suit exists but has a different color, update it to our canonical color.
                if not created and getattr(suit_obj, "color", None) != color:
                    suit_obj.color = color
                    suit_obj.save(update_fields=["color"])
                created_suits.append(suit_obj)
                self.stdout.write(f"{'Created' if created else 'Found'} suit: {suit_obj.name} ({suit_obj.color})")

            # Create or update ranks
            created_ranks = []
            for name, value in ranks:
                rank_obj, created = CardRank.objects.get_or_create(value=value, defaults={"name": name})
                # Normalize the printable name if it differs from our desired name.
                if not created and getattr(rank_obj, "name", None) != name:
                    rank_obj.name = name
                    rank_obj.save(update_fields=["name"])
                created_ranks.append(rank_obj)
                self.stdout.write(f"{'Created' if created else 'Found'} rank: {rank_obj.name} (value={rank_obj.value})")

            # Create cards for every suit × rank (skip cards that already exist)
            created_cards = 0
            skipped_cards = 0
            for suit in created_suits:
                for rank in created_ranks:
                    # If a Card with the suit & rank already exists (and is not a special card),
                    # skip creating a duplicate.
                    card_qs = Card.objects.filter(suit=suit, rank=rank, special_card__isnull=True)
                    if card_qs.exists():
                        skipped_cards += 1
                        continue
                    Card.objects.create(suit=suit, rank=rank)
                    created_cards += 1

            # Summary output
            self.stdout.write(self.style.SUCCESS(
                f"Deck initialization finished for deck_size={deck_size}."
            ))
            self.stdout.write(f"Cards created: {created_cards}. Cards already present: {skipped_cards}.")
            self.stdout.write(
                f"Total suits: {CardSuit.objects.count()}; ranks: {CardRank.objects.count()}; cards: {Card.objects.count()}")
