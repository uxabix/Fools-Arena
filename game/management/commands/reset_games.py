# game/management/commands/reset_games.py
from __future__ import annotations

"""
Django management command to remove active/unfinished Game sessions and related data.

This command is intended to clean up "in-progress" / partially-complete game data
from the database (for example after testing, during QA, or when resetting state).

Behavior
--------
- By default the command does a dry-run and prints how many Game objects would be affected
  and shows their IDs and related Lobby names.
- To actually delete, pass --confirm.
- You can also limit deletion to specific game UUIDs via --game-ids (comma-separated).
- Deletion removes game-specific related objects:
    GameDeck, PlayerHand, TableCard, DiscardPile, Move, Turn, GamePlayer
  and finally the Game row itself. Deletion is performed inside a transaction.

Notes
-----
- The command identifies "unfinished / active" games as those where either:
    * status != 'finished'
    OR
    * finished_at IS NULL
  (This is intentionally broad to catch any games that haven't been properly finished.)
- Lobbies are not deleted by default. If you want the lobbies removed as well, run the
  separate `generate_fake_games --reset` (or tell me and I can add a --remove-lobbies flag).
"""

from typing import List, Optional
import textwrap

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from game.models import (
    Game, GameDeck, PlayerHand, TableCard, DiscardPile,
    Move, Turn, GamePlayer
)


class Command(BaseCommand):
    """Remove active or unfinished games and related data."""

    help = "Remove active/unfinished Game rows and their related game-specific data."

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Actually perform deletion. Without this flag the command will only show a dry-run report."
        )
        parser.add_argument(
            "--game-ids",
            type=str,
            default=None,
            help=(
                "Optional comma-separated list of Game UUIDs to restrict deletions to. "
                "If omitted, all active/unfinished games are targeted."
            )
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            default=False,
            help="Print verbose information about each game that will be (or was) deleted."
        )

    def handle(self, *args, **options):
        """
        Entry point for the management command.

        Steps:
        1. Construct a queryset of games considered 'active' or 'unfinished'.
        2. If --game-ids provided, restrict to those UUIDs.
        3. Report a dry-run summary unless --confirm is present.
        4. If --confirm, delete related objects and the Game rows within a transaction.
        """
        confirm: bool = options["confirm"]
        game_ids_raw: Optional[str] = options["game_ids"]
        verbose: bool = options["verbose"]

        # Identify unfinished/active games:
        # - status != 'finished' OR finished_at is NULL
        queryset = Game.objects.filter(Q(finished_at__isnull=True) | ~Q(status="finished"))

        if game_ids_raw:
            # parse comma-separated uuids and filter
            ids = [s.strip() for s in game_ids_raw.split(",") if s.strip()]
            if not ids:
                self.stdout.write(self.style.ERROR("No valid game IDs parsed from --game-ids. Aborting."))
                return
            queryset = queryset.filter(id__in=ids)

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.NOTICE("No active or unfinished games found. Nothing to do."))
            return

        # Dry-run info
        self.stdout.write(self.style.WARNING(
            textwrap.dedent(
                f"""
                Found {total} active/unfinished game(s) that match the criteria.
                To actually delete these games and their related data, re-run with --confirm.
                """
            ).strip()
        ))

        # show brief list (and verbose details when requested)
        games_list = list(queryset.values("id", "lobby__name", "status", "finished_at")[:200])
        # show up to 200 items to avoid spamming console for massive deletions
        for g in games_list:
            self.stdout.write(f"- Game {g['id']}  lobby='{g['lobby__name']}'  status='{g['status']}'  finished_at={g['finished_at']}")

        if total > len(games_list):
            self.stdout.write(self.style.NOTICE(f"... (only first {len(games_list)} shown)"))

        if not confirm:
            self.stdout.write(self.style.NOTICE("Dry run complete. No rows were deleted. Use --confirm to proceed."))
            return

        # Perform deletion inside a single transaction for safety
        deleted_games = []
        with transaction.atomic():
            # Iterate games to ensure we delete related rows in safe order and can report progress
            for game in queryset.select_related("lobby").all():
                if verbose:
                    self.stdout.write(f"Deleting related objects for game {game.id} (lobby='{getattr(game.lobby, 'name', None)}')...")

                # Delete moves (which reference turns) first
                moves_deleted = Move.objects.filter(turn__game=game).delete()
                if verbose:
                    self.stdout.write(f"  - Moves deleted: {moves_deleted[0]}")

                # Delete turns
                turns_deleted = Turn.objects.filter(game=game).delete()
                if verbose:
                    self.stdout.write(f"  - Turns deleted: {turns_deleted[0]}")

                # Delete table cards and discard piles
                tablecards_deleted = TableCard.objects.filter(game=game).delete()
                discards_deleted = DiscardPile.objects.filter(game=game).delete()
                if verbose:
                    self.stdout.write(f"  - TableCard deleted: {tablecards_deleted[0]}, DiscardPile deleted: {discards_deleted[0]}")

                # Delete player hands and deck entries
                ph_deleted = PlayerHand.objects.filter(game=game).delete()
                deck_deleted = GameDeck.objects.filter(game=game).delete()
                if verbose:
                    self.stdout.write(f"  - PlayerHand deleted: {ph_deleted[0]}, GameDeck deleted: {deck_deleted[0]}")

                # Delete game player rows
                gp_deleted = GamePlayer.objects.filter(game=game).delete()
                if verbose:
                    self.stdout.write(f"  - GamePlayer deleted: {gp_deleted[0]}")

                # Finally delete the game row itself
                game_id = str(game.id)
                game.delete()
                deleted_games.append(game_id)
                self.stdout.write(self.style.SUCCESS(f"Deleted Game {game_id} and related objects."))

        # finished
        self.stdout.write(self.style.SUCCESS(f"Deletion complete. Removed {len(deleted_games)} game(s): {deleted_games}"))
