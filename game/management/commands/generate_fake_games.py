"""
Generate synthetic Durak game data for UI & statistics testing.

This command builds realistic game rows (lobbies, games, game players, hands,
game deck, turns, table cards, moves, and discard piles). It prefers to create
test users by invoking the `generate_test_users` management command (which you
said lives in the `accounts` app). The command will call that management
command with a marker group (`Test_Users`) so created accounts are easy and
safe to delete later.

Usage:
    python manage.py generate_fake_games --games 3 --players 4 --moves 30 --card-count 36
"""
from __future__ import annotations

import itertools
import random
import re
import uuid
from typing import List, Optional

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from game.models import (
    CardSuit,
    CardRank,
    Card,
    Lobby,
    LobbySettings,
    LobbyPlayer,
    Game,
    GamePlayer,
    GameDeck,
    PlayerHand,
    TableCard,
    DiscardPile,
    Turn,
    Move,
)

User = get_user_model()

DEFAULT_RANKS_52 = [
    ("2", 2),
    ("3", 3),
    ("4", 4),
    ("5", 5),
    ("6", 6),
    ("7", 7),
    ("8", 8),
    ("9", 9),
    ("10", 10),
    ("Jack", 11),
    ("Queen", 12),
    ("King", 13),
    ("Ace", 14),
]

DEFAULT_RANKS_36 = [r for r in DEFAULT_RANKS_52 if r[1] >= 6]
DEFAULT_RANKS_24 = [r for r in DEFAULT_RANKS_52 if r[1] >= 9]


class Command(BaseCommand):
    """Management command to generate fake Durak games.

    The command produces decks, deals hands, creates games and simulates a
    sequence of turns with Move rows (attack/defend/pickup). For test user
    creation it prefers to call the `generate_test_users` command (from the
    `accounts` app) with marker group `Test_Users`. If that call fails the
    command falls back to inline user creation to avoid blocking generation.

    Options:
        --games: Number of games to generate (default 5)
        --players: Players per game (default 4)
        --moves: Approximate number of moves per game (default 20)
        --card-count: Deck size (24, 36 or 52, default 36)
        --seed: Optional random seed
        --reset: Delete generated lobbies/games and fake users (prefix 'fake_user_')
    """

    help = "Generate sample Durak games with move history for UI & statistics testing."

    def add_arguments(self, parser):
        """Add command-line arguments.

        Args:
            parser: Argument parser provided by Django.
        """
        parser.add_argument("--games", type=int, default=5, help="Number of games to generate (default: 5)")
        parser.add_argument("--players", type=int, default=4, help="Players per game (2-8 recommended, default: 4)")
        parser.add_argument("--moves", type=int, default=20, help="Approx number of moves per game (default: 20)")
        parser.add_argument(
            "--card-count",
            type=int,
            choices=[24, 36, 52],
            default=36,
            help="Deck size per lobby (24, 36, or 52). Default: 36",
        )
        parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible runs")
        parser.add_argument(
            "--reset",
            action="store_true",
            default=False,
            help="Delete generated lobbies/games (prefix 'Fake Lobby ') and fake users (prefix 'fake_user_')",
        )

    def handle(self, *args, **options):
        """Main entry point.

        Args:
            *args: Positional args (unused).
            **options: Parsed CLI options.
        """
        games = options["games"]
        players = options["players"]
        approx_moves = options["moves"]
        card_count = options["card_count"]
        seed = options["seed"]
        do_reset = options["reset"]

        if seed is not None:
            random.seed(seed)

        if do_reset:
            self._reset_generated_lobbies_and_users()
            return

        if not (2 <= players <= 8):
            self.stdout.write(self.style.WARNING("players outside normal range (2-8). Continuing anyway."))

        self.stdout.write(
            f"Generating {games} game(s), {players} players each, ~{approx_moves} moves per game, {card_count}-card decks..."
        )

        with transaction.atomic():
            self._ensure_suits_and_ranks(card_count)
            self._ensure_cards(card_count)

            # estimate users needed: owner + players per game, reuse users when possible
            users = self._ensure_users(max_needed=games * (players + 1))

            # cycle through the users so we can reuse them across games if fewer provided
            user_iter = itertools.cycle(users)
            created_games = []

            for g_idx in range(games):
                game = self._create_fake_game(
                    players=players,
                    approx_moves=approx_moves,
                    card_count=card_count,
                    user_iter=user_iter,
                    game_index=g_idx + 1,
                )
                created_games.append(str(game.id))
                self.stdout.write(self.style.SUCCESS(f"Created Game {game.id} in Lobby '{game.lobby.name}'"))

        self.stdout.write(self.style.SUCCESS(f"Done. Created {len(created_games)} games: {created_games}"))

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _reset_generated_lobbies_and_users(self):
        """Remove generated lobbies/games and fake users.

        Lobbies are identified by name prefix 'Fake Lobby '. Fake users are
        identified by username prefix 'fake_user_'. Staff and superuser users
        are excluded from user deletion if those fields exist.
        """
        with transaction.atomic():
            lobby_qs = Lobby.objects.filter(name__startswith="Fake Lobby ")
            deleted_count, details = lobby_qs.delete()
            self.stdout.write(
                self.style.WARNING(f"Reset requested: deleted {deleted_count} objects (details: {details})."))

            try:
                fake_user_qs = User.objects.filter(username__startswith="fake_user_").exclude(is_staff=True).exclude(
                    is_superuser=True)
            except Exception:
                fake_user_qs = User.objects.filter(username__startswith="fake_user_")

            fake_user_count = fake_user_qs.count()
            if fake_user_count:
                u_deleted_count, u_deleted_details = fake_user_qs.delete()
                self.stdout.write(
                    self.style.WARNING(f"Deleted {fake_user_count} fake user(s) (deleted objects: {u_deleted_count})."))
            else:
                self.stdout.write(self.style.NOTICE("No fake users found to delete."))

    def _ensure_suits_and_ranks(self, card_count: int):
        """Ensure CardSuit and CardRank rows exist.

        Args:
            card_count: Number of cards in deck (24/36/52) to decide which ranks to create.
        """
        suits = {"Hearts": "red", "Diamonds": "red", "Clubs": "black", "Spades": "black"}
        for name, color in suits.items():
            CardSuit.objects.get_or_create(name=name, defaults={"color": color})

        if card_count == 52:
            ranks = DEFAULT_RANKS_52
        elif card_count == 36:
            ranks = DEFAULT_RANKS_36
        else:
            ranks = DEFAULT_RANKS_24

        existing_values = set(CardRank.objects.values_list("value", flat=True))
        for name, val in ranks:
            if val not in existing_values:
                CardRank.objects.create(name=name, value=val)

    def _ensure_cards(self, card_count: int):
        """Ensure Card objects exist for the requested deck size.

        Args:
            card_count: Deck size (24/36/52).
        """
        suits = list(CardSuit.objects.all())
        if card_count == 52:
            ranks_qs = CardRank.objects.all()
        elif card_count == 36:
            ranks_qs = CardRank.objects.filter(value__gte=6)
        else:
            ranks_qs = CardRank.objects.filter(value__gte=9)

        ranks = list(ranks_qs)
        created = 0
        for suit in suits:
            for rank in ranks:
                _, created_flag = Card.objects.get_or_create(suit=suit, rank=rank)
                if created_flag:
                    created += 1
        if created:
            self.stdout.write(self.style.NOTICE(f"Created {created} Card objects."))

    def _ensure_users(self, max_needed: int) -> List[User]:
        """Ensure at least `max_needed` users exist.

        The method prefers to call the `generate_test_users` management command
        (from the accounts app). It requests creation with prefix `fake_user_` and
        marker group `Test_Users`. If the call fails, it will fall back to inline
        creation to ensure generation continues.

        Args:
            max_needed: Minimum number of users required.

        Returns:
            List of User instances (length >= max_needed).
        """
        existing = list(User.objects.all().order_by("id"))
        if len(existing) >= max_needed:
            return existing[:max_needed]

        needed = max_needed - len(existing)

        prefix = "fake_user_"
        existing_fake = list(User.objects.filter(username__startswith=prefix))
        max_index = 0
        for u in existing_fake:
            m = re.search(rf'^{re.escape(prefix)}(\d+)$', u.username)
            if m:
                try:
                    idx = int(m.group(1))
                    if idx > max_index:
                        max_index = idx
                except Exception:
                    pass
        start = max_index + 1

        try:
            # Ask the accounts app's generate_test_users command to create the missing users
            call_command(
                "generate_test_users",
                "--count",
                str(needed),
                "--prefix",
                prefix,
                "--start",
                str(start),
                "--marker-group",
                "Test_Users",
            )
            self.stdout.write(self.style.NOTICE(
                f"Requested {needed} test user(s) via generate_test_users (prefix={prefix}, start={start})."))
        except Exception as exc:
            # Fallback inline creation
            self.stdout.write(
                self.style.WARNING(f"Calling generate_test_users failed: {exc}. Falling back to inline creation."))
            created_users = []
            for i in range(needed):
                username = f"{prefix}{start + i}"
                try:
                    user = User.objects.create_user(username=username, password="testpass")
                except Exception:
                    # Try create without password method if custom user model differs
                    user = User.objects.create(username=username)
                created_users.append(user)
            self.stdout.write(self.style.NOTICE(f"Fallback created {len(created_users)} users."))
            all_users = existing + created_users
            return all_users[:max_needed]

        all_users = list(User.objects.all().order_by("id"))
        return all_users[:max_needed]

    def _draw_from_deck_list(self, deck_cards: List[Card]) -> Optional[Card]:
        """Pop a card from a list representing the deck.

        Args:
            deck_cards: Mutable list acting as the deck (front = top).

        Returns:
            Card or None if deck is empty.
        """
        if not deck_cards:
            return None
        return deck_cards.pop(0)

    def _create_fake_game(self, players: int, approx_moves: int, card_count: int, user_iter, game_index: int) -> Game:
        """Create a single fake lobby/game and simulate play.

        Args:
            players: Number of players in the created game.
            approx_moves: Approximate number of attack/defend/pickup moves to simulate.
            card_count: Deck size (24/36/52).
            user_iter: Iterator that yields User objects (owner + players).
            game_index: One-based index used for naming.

        Returns:
            The created Game instance.
        """
        owner_user = next(user_iter)
        lobby = Lobby.objects.create(owner=owner_user, name=f"Fake Lobby {uuid.uuid4().hex[:6]}", is_private=False,
                                     status="playing")

        LobbySettings.objects.create(
            lobby=lobby,
            max_players=players,
            card_count=card_count,
            is_transferable=False,
            neighbor_throw_only=False,
            allow_jokers=False,
        )

        # Build list of Card objects representing the deck
        if card_count == 52:
            ranks_qs = CardRank.objects.all()
        elif card_count == 36:
            ranks_qs = CardRank.objects.filter(value__gte=6)
        else:
            ranks_qs = CardRank.objects.filter(value__gte=9)

        ranks = list(ranks_qs)
        suits = list(CardSuit.objects.all())
        deck_cards: List[Card] = []
        for suit in suits:
            for rank in ranks:
                try:
                    deck_cards.append(Card.objects.get(suit=suit, rank=rank))
                except Card.DoesNotExist:
                    continue

        random.shuffle(deck_cards)
        trump_card_obj = deck_cards[-1] if deck_cards else None
        if trump_card_obj is None:
            raise RuntimeError("No Card objects available to create a game.")

        game = Game.objects.create(lobby=lobby, trump_card=trump_card_obj, status="in_progress")

        # Persist deck into GameDeck model
        for pos, card in enumerate(deck_cards, start=1):
            GameDeck.objects.create(game=game, card=card, position=pos)

        # Create LobbyPlayer and GamePlayer entries
        game_players: List[GamePlayer] = []
        for seat in range(1, players + 1):
            user = next(user_iter)
            LobbyPlayer.objects.create(lobby=lobby, user=user, status="playing")
            gp = GamePlayer.objects.create(game=game, user=user, seat_position=seat, cards_remaining=0)
            game_players.append(gp)

        # Helper to pop top GameDeck entry (DB-backed)
        def pop_top_db_card(game_obj: Game) -> Optional[Card]:
            top_qs = GameDeck.objects.filter(game=game_obj).order_by("position")[:1]
            if not top_qs:
                return None
            gd = top_qs[0]
            card = gd.card
            gd.delete()
            return card

        # Deal initial hands (6 cards typical)
        initial_hand_size = 6
        for gp in game_players:
            for idx in range(initial_hand_size):
                card = pop_top_db_card(game)
                if not card:
                    break
                PlayerHand.objects.create(game=game, player=gp.user, card=card, order_in_hand=idx + 1)
                gp.cards_remaining += 1
            gp.save(update_fields=["cards_remaining"])

        # Simulate a sequence of turns and moves
        current_attacker_index = 0
        turn_counter = 0
        discard_position = 1

        def find_defense_card_for_player(defender_user, attack_card):
            """Return a PlayerHand instance that can defend or None."""
            ph_qs = PlayerHand.objects.filter(game=game, player=defender_user)
            for ph in ph_qs:
                try:
                    if ph.card.can_beat(attack_card, game.get_trump_suit()):
                        return ph
                except Exception:
                    return None
            return None

        for _ in range(approx_moves):
            turn_counter += 1
            attacker_gp = game_players[current_attacker_index % len(game_players)]
            attacker_user = attacker_gp.user
            turn = Turn.objects.create(game=game, player=attacker_user, turn_number=turn_counter)

            attacker_hand = list(PlayerHand.objects.filter(game=game, player=attacker_user).order_by("order_in_hand"))
            if not attacker_hand:
                current_attacker_index += 1
                continue

            attack_ph = attacker_hand[0]
            attack_card = attack_ph.card
            attack_ph.delete()
            attacker_gp.cards_remaining = max(0, attacker_gp.cards_remaining - 1)
            attacker_gp.save(update_fields=["cards_remaining"])

            table_card = TableCard.objects.create(game=game, attack_card=attack_card)
            Move.objects.create(turn=turn, table_card=table_card, action_type="attack", created_at=timezone.now())

            defender_index = (current_attacker_index + 1) % len(game_players)
            defender_gp = game_players[defender_index]
            defender_user = defender_gp.user

            defense_ph = find_defense_card_for_player(defender_user, attack_card)
            if defense_ph:
                defense_card = defense_ph.card
                table_card.defense_card = defense_card
                table_card.save(update_fields=["defense_card"])
                defense_ph.delete()
                defender_gp.cards_remaining = max(0, defender_gp.cards_remaining - 1)
                defender_gp.save(update_fields=["cards_remaining"])

                Move.objects.create(turn=turn, table_card=table_card, action_type="defend", created_at=timezone.now())

                DiscardPile.objects.create(game=game, card=attack_card, position=discard_position)
                discard_position += 1
                DiscardPile.objects.create(game=game, card=defense_card, position=discard_position)
                discard_position += 1
            else:
                Move.objects.create(turn=turn, table_card=table_card, action_type="pickup", created_at=timezone.now())
                PlayerHand.objects.create(game=game, player=defender_user, card=attack_card,
                                          order_in_hand=defender_gp.cards_remaining + 1)
                defender_gp.cards_remaining += 1
                defender_gp.save(update_fields=["cards_remaining"])

            # Refill hands up to 6 cards
            for gp in game_players:
                while gp.cards_remaining < 6:
                    card = pop_top_db_card(game)
                    if not card:
                        break
                    PlayerHand.objects.create(game=game, player=gp.user, card=card,
                                              order_in_hand=gp.cards_remaining + 1)
                    gp.cards_remaining += 1
                    gp.save(update_fields=["cards_remaining"])

            current_attacker_index = (current_attacker_index + 1) % len(game_players)

        # Optionally finish the game and pick a loser
        if random.random() < 0.6:
            loser_gp = random.choice(game_players)
            game.loser = loser_gp.user
            game.status = "finished"
            game.finished_at = timezone.now()
            game.save(update_fields=["loser", "status", "finished_at"])

        return game
