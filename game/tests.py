from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from game.models import (
    CardSuit, CardRank, Card, Lobby, LobbySettings, LobbyPlayer,
    Game, GamePlayer, GameDeck, PlayerHand, TableCard, DiscardPile,
    Turn, Move, SpecialCard, SpecialRuleSet, SpecialRuleSetCard
)

User = get_user_model()


class CardSuitModelTest(TestCase):
    """Test suite for CardSuit model."""

    def setUp(self):
        """Set up test data for CardSuit tests."""
        self.hearts = CardSuit.objects.create(name="Hearts", color="red")
        self.spades = CardSuit.objects.create(name="Spades", color="black")

    def test_card_suit_creation(self):
        """Test that CardSuit instances are created correctly."""
        self.assertEqual(self.hearts.name, "Hearts")
        self.assertEqual(self.hearts.color, "red")
        self.assertEqual(self.spades.color, "black")

    def test_card_suit_str_representation(self):
        """Test string representation of CardSuit."""
        self.assertEqual(str(self.hearts), "Hearts")
        self.assertEqual(str(self.spades), "Spades")

    def test_is_red_method(self):
        """Test is_red() method returns correct boolean."""
        self.assertTrue(self.hearts.is_red())
        self.assertFalse(self.spades.is_red())

    def test_card_suit_ordering(self):
        """Test that CardSuit instances are ordered by name."""
        diamonds = CardSuit.objects.create(name="Diamonds", color="red")
        clubs = CardSuit.objects.create(name="Clubs", color="black")

        suits = list(CardSuit.objects.all())
        self.assertEqual(suits[0].name, "Clubs")
        self.assertEqual(suits[1].name, "Diamonds")
        self.assertEqual(suits[2].name, "Hearts")
        self.assertEqual(suits[3].name, "Spades")

    def test_card_suit_color_choices(self):
        """Test that only valid color choices are accepted."""
        # Valid colors should work
        valid_suit = CardSuit.objects.create(name="Test", color="red")
        self.assertEqual(valid_suit.color, "red")


class CardRankModelTest(TestCase):
    """Test suite for CardRank model."""

    def setUp(self):
        """Set up test data for CardRank tests."""
        self.ace = CardRank.objects.create(name="Ace", value=14)
        self.king = CardRank.objects.create(name="King", value=13)
        self.jack = CardRank.objects.create(name="Jack", value=11)
        self.six = CardRank.objects.create(name="Six", value=6)

    def test_card_rank_creation(self):
        """Test that CardRank instances are created correctly."""
        self.assertEqual(self.ace.name, "Ace")
        self.assertEqual(self.ace.value, 14)

    def test_card_rank_str_representation(self):
        """Test string representation of CardRank."""
        self.assertEqual(str(self.ace), "Ace")
        self.assertEqual(str(self.king), "King")

    def test_is_face_card_method(self):
        """Test is_face_card() method for various ranks."""
        self.assertTrue(self.king.is_face_card())
        self.assertTrue(self.jack.is_face_card())
        self.assertFalse(self.ace.is_face_card())
        self.assertFalse(self.six.is_face_card())

        queen = CardRank.objects.create(name="Queen", value=12)
        self.assertTrue(queen.is_face_card())

    def test_card_rank_ordering(self):
        """Test that CardRank instances are ordered by value."""
        ranks = list(CardRank.objects.all())
        self.assertEqual(ranks[0].value, 6)
        self.assertEqual(ranks[1].value, 11)
        self.assertEqual(ranks[2].value, 13)
        self.assertEqual(ranks[3].value, 14)


class CardModelTest(TestCase):
    """Test suite for Card model."""

    def setUp(self):
        """Set up test data for Card tests."""
        self.hearts = CardSuit.objects.create(name="Hearts", color="red")
        self.spades = CardSuit.objects.create(name="Spades", color="black")
        self.diamonds = CardSuit.objects.create(name="Diamonds", color="red")

        self.ace = CardRank.objects.create(name="Ace", value=14)
        self.king = CardRank.objects.create(name="King", value=13)
        self.seven = CardRank.objects.create(name="Seven", value=7)
        self.six = CardRank.objects.create(name="Six", value=6)

        self.ace_of_hearts = Card.objects.create(suit=self.hearts, rank=self.ace)
        self.king_of_spades = Card.objects.create(suit=self.spades, rank=self.king)
        self.seven_of_hearts = Card.objects.create(suit=self.hearts, rank=self.seven)
        self.six_of_diamonds = Card.objects.create(suit=self.diamonds, rank=self.six)

    def test_card_creation(self):
        """Test that Card instances are created correctly."""
        self.assertEqual(self.ace_of_hearts.suit, self.hearts)
        self.assertEqual(self.ace_of_hearts.rank, self.ace)

    def test_card_str_representation(self):
        """Test string representation of Card."""
        self.assertEqual(str(self.ace_of_hearts), "Ace of Hearts")
        self.assertEqual(str(self.king_of_spades), "King of Spades")

    def test_card_str_with_special_card(self):
        """Test string representation includes special card name."""
        special = SpecialCard.objects.create(
            name="Skip Turn",
            effect_type="skip",
            description="Skip next player's turn"
        )
        special_card = Card.objects.create(
            suit=self.spades,
            rank=self.ace,
            special_card=special
        )
        self.assertEqual(str(special_card), "Ace of Spades (Skip Turn)")

    def test_is_trump_method(self):
        """Test is_trump() method with various trump suits."""
        self.assertTrue(self.ace_of_hearts.is_trump(self.hearts))
        self.assertFalse(self.ace_of_hearts.is_trump(self.spades))
        self.assertTrue(self.king_of_spades.is_trump(self.spades))

    def test_is_special_method(self):
        """Test is_special() method."""
        self.assertFalse(self.ace_of_hearts.is_special())

        special = SpecialCard.objects.create(
            name="Draw Two",
            effect_type="draw",
            description="Draw 2 cards"
        )
        special_card = Card.objects.create(
            suit=self.hearts,
            rank=self.seven,
            special_card=special
        )
        self.assertTrue(special_card.is_special())

    def test_can_beat_trump_vs_non_trump(self):
        """Test that trump cards beat non-trump cards."""
        # Hearts is trump
        trump_suit = self.hearts

        # Low trump beats high non-trump
        self.assertTrue(self.seven_of_hearts.can_beat(self.king_of_spades, trump_suit))

        # Non-trump cannot beat trump
        self.assertFalse(self.king_of_spades.can_beat(self.seven_of_hearts, trump_suit))

    def test_can_beat_same_suit(self):
        """Test card comparison for same suit."""
        trump_suit = self.spades

        # Higher rank beats lower rank in same suit
        self.assertTrue(self.ace_of_hearts.can_beat(self.seven_of_hearts, trump_suit))

        # Lower rank cannot beat higher rank
        self.assertFalse(self.seven_of_hearts.can_beat(self.ace_of_hearts, trump_suit))

    def test_can_beat_different_non_trump_suits(self):
        """Test that different non-trump suits cannot beat each other."""
        trump_suit = self.spades

        # Hearts and Diamonds are both non-trump
        self.assertFalse(self.ace_of_hearts.can_beat(self.six_of_diamonds, trump_suit))
        self.assertFalse(self.six_of_diamonds.can_beat(self.ace_of_hearts, trump_suit))

    def test_can_beat_trump_vs_trump(self):
        """Test trump card comparison."""
        trump_suit = self.hearts

        # Higher trump beats lower trump
        self.assertTrue(self.ace_of_hearts.can_beat(self.seven_of_hearts, trump_suit))
        self.assertFalse(self.seven_of_hearts.can_beat(self.ace_of_hearts, trump_suit))

    def test_card_unique_together_constraint(self):
        """Test that cards with same suit, rank, and special_card are unique."""
        # Create a special card first
        special = SpecialCard.objects.create(
            name="Test Special",
            effect_type="skip",
            description="Test"
        )

        # Create first card with special_card
        Card.objects.create(
            suit=self.hearts,
            rank=self.ace,
            special_card=special
        )

        # Creating duplicate with same suit, rank, and special_card should fail
        with self.assertRaises(IntegrityError):
            Card.objects.create(
                suit=self.hearts,
                rank=self.ace,
                special_card=special
            )


class LobbyModelTest(TestCase):
    """Test suite for Lobby model."""

    def setUp(self):
        """Set up test data for Lobby tests."""
        self.user1 = User.objects.create_user(username="player1", password="test123")
        self.user2 = User.objects.create_user(username="player2", password="test123")

        self.lobby = Lobby.objects.create(
            owner=self.user1,
            name="Test Lobby",
            is_private=False,
            status='waiting'
        )

        # Create lobby settings
        self.settings = LobbySettings.objects.create(
            lobby=self.lobby,
            max_players=4,
            card_count=36,
            is_transferable=False,
            neighbor_throw_only=False,
            allow_jokers=False
        )

    def test_lobby_creation(self):
        """Test that Lobby instances are created correctly."""
        self.assertEqual(self.lobby.name, "Test Lobby")
        self.assertEqual(self.lobby.owner, self.user1)
        self.assertFalse(self.lobby.is_private)
        self.assertEqual(self.lobby.status, 'waiting')

    def test_lobby_str_representation(self):
        """Test string representation of Lobby."""
        self.assertEqual(str(self.lobby), "Test Lobby")

    def test_lobby_uuid_generation(self):
        """Test that UUID is automatically generated."""
        self.assertIsNotNone(self.lobby.id)

    def test_is_full_method_empty_lobby(self):
        """Test is_full() returns False for empty lobby."""
        self.assertFalse(self.lobby.is_full())

    def test_is_full_method_with_players(self):
        """Test is_full() with various player counts."""
        # Add players up to max
        for i in range(4):
            user = User.objects.create_user(username=f"player{i + 10}", password="test")
            LobbyPlayer.objects.create(
                lobby=self.lobby,
                user=user,
                status='waiting'
            )

        self.assertTrue(self.lobby.is_full())

    def test_is_full_excludes_left_players(self):
        """Test that is_full() doesn't count players who left."""
        # Add 3 active players
        for i in range(3):
            user = User.objects.create_user(username=f"player{i + 10}", password="test")
            LobbyPlayer.objects.create(
                lobby=self.lobby,
                user=user,
                status='waiting'
            )

        # Add 1 player who left
        left_user = User.objects.create_user(username="left_player", password="test")
        LobbyPlayer.objects.create(
            lobby=self.lobby,
            user=left_user,
            status='left'
        )

        self.assertFalse(self.lobby.is_full())

    def test_can_start_game_method_not_enough_players(self):
        """Test can_start_game() returns False with insufficient ready players."""
        # Add only 1 ready player
        LobbyPlayer.objects.create(
            lobby=self.lobby,
            user=self.user1,
            status='ready'
        )

        self.assertFalse(self.lobby.can_start_game())

    def test_can_start_game_method_enough_ready_players(self):
        """Test can_start_game() returns True with enough ready players."""
        # Add 2 ready players
        LobbyPlayer.objects.create(lobby=self.lobby, user=self.user1, status='ready')
        LobbyPlayer.objects.create(lobby=self.lobby, user=self.user2, status='ready')

        self.assertTrue(self.lobby.can_start_game())

    def test_can_start_game_method_wrong_status(self):
        """Test can_start_game() returns False if lobby status is not 'waiting'."""
        LobbyPlayer.objects.create(lobby=self.lobby, user=self.user1, status='ready')
        LobbyPlayer.objects.create(lobby=self.lobby, user=self.user2, status='ready')

        self.lobby.status = 'playing'
        self.lobby.save()

        self.assertFalse(self.lobby.can_start_game())

    def test_get_active_players_method(self):
        """Test get_active_players() returns only active players."""
        LobbyPlayer.objects.create(lobby=self.lobby, user=self.user1, status='waiting')
        LobbyPlayer.objects.create(lobby=self.lobby, user=self.user2, status='ready')

        left_user = User.objects.create_user(username="left", password="test")
        LobbyPlayer.objects.create(lobby=self.lobby, user=left_user, status='left')

        active_players = self.lobby.get_active_players()
        self.assertEqual(active_players.count(), 2)

    def test_lobby_ordering(self):
        """Test that lobbies are ordered by creation date (newest first)."""
        lobby2 = Lobby.objects.create(
            owner=self.user2,
            name="Newer Lobby",
            status='waiting'
        )

        lobbies = list(Lobby.objects.all())
        self.assertEqual(lobbies[0], lobby2)
        self.assertEqual(lobbies[1], self.lobby)

    def test_private_lobby_with_password(self):
        """Test creating a private lobby with password hash."""
        private_lobby = Lobby.objects.create(
            owner=self.user1,
            name="Private Game",
            is_private=True,
            password_hash="hashed_password_here",
            status='waiting'
        )

        self.assertTrue(private_lobby.is_private)
        self.assertEqual(private_lobby.password_hash, "hashed_password_here")


class LobbySettingsModelTest(TestCase):
    """Test suite for LobbySettings model."""

    def setUp(self):
        """Set up test data for LobbySettings tests."""
        self.user = User.objects.create_user(username="player1", password="test123")
        self.lobby = Lobby.objects.create(
            owner=self.user,
            name="Test Lobby",
            status='waiting'
        )

        self.settings = LobbySettings.objects.create(
            lobby=self.lobby,
            max_players=4,
            card_count=36,
            is_transferable=True,
            neighbor_throw_only=False,
            allow_jokers=False,
            turn_time_limit=60
        )

    def test_lobby_settings_creation(self):
        """Test that LobbySettings instances are created correctly."""
        self.assertEqual(self.settings.max_players, 4)
        self.assertEqual(self.settings.card_count, 36)
        self.assertTrue(self.settings.is_transferable)

    def test_lobby_settings_str_representation(self):
        """Test string representation of LobbySettings."""
        expected = "Test Lobby Settings (36 cards, 4 players)"
        self.assertEqual(str(self.settings), expected)

    def test_has_time_limit_method(self):
        """Test has_time_limit() method."""
        self.assertTrue(self.settings.has_time_limit())

        # Test without time limit
        settings_no_limit = LobbySettings.objects.create(
            lobby=Lobby.objects.create(owner=self.user, name="No Limit", status='waiting'),
            max_players=2,
            card_count=24,
            turn_time_limit=None
        )
        self.assertFalse(settings_no_limit.has_time_limit())

    def test_is_beginner_friendly_method_true(self):
        """Test is_beginner_friendly() returns True for simple settings."""
        beginner_settings = LobbySettings.objects.create(
            lobby=Lobby.objects.create(owner=self.user, name="Beginner", status='waiting'),
            max_players=2,
            card_count=24,
            is_transferable=False,
            neighbor_throw_only=False,
            allow_jokers=False,
            special_rule_set=None
        )

        self.assertTrue(beginner_settings.is_beginner_friendly())

    def test_is_beginner_friendly_method_false_transferable(self):
        """Test is_beginner_friendly() returns False with transferable cards."""
        self.assertFalse(self.settings.is_beginner_friendly())

    def test_is_beginner_friendly_method_false_jokers(self):
        """Test is_beginner_friendly() returns False with jokers."""
        settings = LobbySettings.objects.create(
            lobby=Lobby.objects.create(owner=self.user, name="Jokers", status='waiting'),
            max_players=2,
            card_count=24,
            is_transferable=False,
            allow_jokers=True
        )

        self.assertFalse(settings.is_beginner_friendly())

    def test_is_beginner_friendly_method_false_special_rules(self):
        """Test is_beginner_friendly() returns False with special rule set."""
        special_rules = SpecialRuleSet.objects.create(
            name="Advanced Rules",
            description="Complex rules",
            min_players=2
        )

        settings = LobbySettings.objects.create(
            lobby=Lobby.objects.create(owner=self.user, name="Special", status='waiting'),
            max_players=2,
            card_count=24,
            is_transferable=False,
            allow_jokers=False,
            special_rule_set=special_rules
        )

        self.assertFalse(settings.is_beginner_friendly())

    def test_card_count_choices(self):
        """Test that only valid card counts are accepted."""
        for count in [24, 36, 52]:
            settings = LobbySettings.objects.create(
                lobby=Lobby.objects.create(owner=self.user, name=f"Lobby{count}", status='waiting'),
                max_players=2,
                card_count=count
            )
            self.assertEqual(settings.card_count, count)


class LobbyPlayerModelTest(TestCase):
    """Test suite for LobbyPlayer model."""

    def setUp(self):
        """Set up test data for LobbyPlayer tests."""
        self.user1 = User.objects.create_user(username="player1", password="test123")
        self.user2 = User.objects.create_user(username="player2", password="test123")

        self.lobby = Lobby.objects.create(
            owner=self.user1,
            name="Test Lobby",
            status='waiting'
        )

        self.lobby_player = LobbyPlayer.objects.create(
            lobby=self.lobby,
            user=self.user1,
            status='waiting'
        )

    def test_lobby_player_creation(self):
        """Test that LobbyPlayer instances are created correctly."""
        self.assertEqual(self.lobby_player.lobby, self.lobby)
        self.assertEqual(self.lobby_player.user, self.user1)
        self.assertEqual(self.lobby_player.status, 'waiting')

    def test_lobby_player_str_representation(self):
        """Test string representation of LobbyPlayer."""
        expected = "player1 (waiting) in Test Lobby"
        self.assertEqual(str(self.lobby_player), expected)

    def test_is_active_method(self):
        """Test is_active() method for various statuses."""
        self.assertTrue(self.lobby_player.is_active())

        self.lobby_player.status = 'ready'
        self.assertTrue(self.lobby_player.is_active())

        self.lobby_player.status = 'playing'
        self.assertTrue(self.lobby_player.is_active())

        self.lobby_player.status = 'left'
        self.assertFalse(self.lobby_player.is_active())

    def test_can_start_game_method(self):
        """Test can_start_game() method."""
        self.assertFalse(self.lobby_player.can_start_game())

        self.lobby_player.status = 'ready'
        self.assertTrue(self.lobby_player.can_start_game())

        self.lobby_player.status = 'playing'
        self.assertFalse(self.lobby_player.can_start_game())

    def test_leave_lobby_method(self):
        """Test leave_lobby() method updates status."""
        self.lobby_player.leave_lobby()

        self.lobby_player.refresh_from_db()
        self.assertEqual(self.lobby_player.status, 'left')

    def test_unique_together_constraint(self):
        """Test that a user cannot join the same lobby twice."""
        with self.assertRaises(IntegrityError):
            LobbyPlayer.objects.create(
                lobby=self.lobby,
                user=self.user1,
                status='waiting'
            )

    def test_lobby_player_ordering(self):
        """Test that lobby players are ordered by lobby and username."""
        user3 = User.objects.create_user(username="aaa_first", password="test")

        player2 = LobbyPlayer.objects.create(
            lobby=self.lobby,
            user=self.user2,
            status='waiting'
        )

        player3 = LobbyPlayer.objects.create(
            lobby=self.lobby,
            user=user3,
            status='waiting'
        )

        players = list(LobbyPlayer.objects.filter(lobby=self.lobby))
        self.assertEqual(players[0].user.username, "aaa_first")
        self.assertEqual(players[1].user.username, "player1")
        self.assertEqual(players[2].user.username, "player2")


class GameModelTest(TestCase):
    """Test suite for Game model."""

    def setUp(self):
        """Set up test data for Game tests."""
        self.user1 = User.objects.create_user(username="player1", password="test123")
        self.user2 = User.objects.create_user(username="player2", password="test123")

        self.lobby = Lobby.objects.create(
            owner=self.user1,
            name="Game Lobby",
            status='playing'
        )

        # Create cards for trump
        self.hearts = CardSuit.objects.create(name="Hearts", color="red")
        self.ace = CardRank.objects.create(name="Ace", value=14)
        self.trump_card = Card.objects.create(suit=self.hearts, rank=self.ace)

        self.game = Game.objects.create(
            lobby=self.lobby,
            trump_card=self.trump_card,
            status='in_progress'
        )

    def test_game_creation(self):
        """Test that Game instances are created correctly."""
        self.assertEqual(self.game.lobby, self.lobby)
        self.assertEqual(self.game.trump_card, self.trump_card)
        self.assertEqual(self.game.status, 'in_progress')
        self.assertIsNone(self.game.finished_at)
        self.assertIsNone(self.game.loser)

    def test_game_str_representation(self):
        """Test string representation of Game."""
        expected = "Game in Game Lobby (in_progress)"
        self.assertEqual(str(self.game), expected)

    def test_is_active_method(self):
        """Test is_active() method."""
        self.assertTrue(self.game.is_active())

        self.game.status = 'finished'
        self.assertFalse(self.game.is_active())

    def test_get_trump_suit_method(self):
        """Test get_trump_suit() returns correct suit."""
        trump_suit = self.game.get_trump_suit()
        self.assertEqual(trump_suit, self.hearts)

    def test_get_player_count_method(self):
        """Test get_player_count() returns correct count."""
        self.assertEqual(self.game.get_player_count(), 0)

        GamePlayer.objects.create(
            game=self.game,
            user=self.user1,
            seat_position=1,
            cards_remaining=6
        )

        GamePlayer.objects.create(
            game=self.game,
            user=self.user2,
            seat_position=2,
            cards_remaining=6
        )

        self.assertEqual(self.game.get_player_count(), 2)

    def test_get_winner_method_active_game(self):
        """Test get_winner() returns None for active games."""
        self.assertIsNone(self.game.get_winner())

    def test_get_winner_method_finished_game(self):
        """Test get_winner() returns winners after game finishes."""
        player1 = GamePlayer.objects.create(
            game=self.game,
            user=self.user1,
            seat_position=1,
            cards_remaining=0
        )

        player2 = GamePlayer.objects.create(
            game=self.game,
            user=self.user2,
            seat_position=2,
            cards_remaining=3
        )

        self.game.status = 'finished'
        self.game.loser = self.user2
        self.game.finished_at = timezone.now()
        self.game.save()

        winners = self.game.get_winner()
        self.assertIsNotNone(winners)
        self.assertEqual(winners.count(), 1)
        self.assertEqual(winners.first().user, self.user1)

    def test_game_ordering(self):
        """Test that games are ordered by start time (newest first)."""
        game2 = Game.objects.create(
            lobby=self.lobby,
            trump_card=self.trump_card,
            status='in_progress'
        )

        games = list(Game.objects.all())
        self.assertEqual(games[0], game2)
        self.assertEqual(games[1], self.game)


class GamePlayerModelTest(TestCase):
    """Test suite for GamePlayer model."""

    def setUp(self):
        """Set up test data for GamePlayer tests."""
        self.user = User.objects.create_user(username="player1", password="test123")

        lobby = Lobby.objects.create(owner=self.user, name="Test", status='playing')

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump_card = Card.objects.create(suit=hearts, rank=ace)

        self.game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='in_progress'
        )

        self.game_player = GamePlayer.objects.create(
            game=self.game,
            user=self.user,
            seat_position=1,
            cards_remaining=6
        )

    def test_game_player_creation(self):
        """Test that GamePlayer instances are created correctly."""
        self.assertEqual(self.game_player.game, self.game)
        self.assertEqual(self.game_player.user, self.user)
        self.assertEqual(self.game_player.seat_position, 1)
        self.assertEqual(self.game_player.cards_remaining, 6)

    def test_game_player_str_representation(self):
        """Test string representation of GamePlayer."""
        expected = "player1 (6 cards) - Position 1"
        self.assertEqual(str(self.game_player), expected)

    def test_has_cards_method(self):
        """Test has_cards() method."""
        self.assertTrue(self.game_player.has_cards())

        self.game_player.cards_remaining = 0
        self.assertFalse(self.game_player.has_cards())

    def test_is_eliminated_method(self):
        """Test is_eliminated() method."""
        self.assertFalse(self.game_player.is_eliminated())

        self.game_player.cards_remaining = 0
        self.assertTrue(self.game_player.is_eliminated())

    def test_get_hand_cards_method(self):
        """Test get_hand_cards() returns correct queryset."""
        # Create some cards
        hearts = CardSuit.objects.create(name="Hearts", color="red")
        seven = CardRank.objects.create(name="Seven", value=7)
        card = Card.objects.create(suit=hearts, rank=seven)

        PlayerHand.objects.create(
            game=self.game,
            player=self.user,
            card=card,
            order_in_hand=1
        )

        hand_cards = self.game_player.get_hand_cards()
        self.assertEqual(hand_cards.count(), 1)
        self.assertEqual(hand_cards.first().card, card)

    def test_unique_together_constraint(self):
        """Test that a user cannot be added to same game twice."""
        with self.assertRaises(IntegrityError):
            GamePlayer.objects.create(
                game=self.game,
                user=self.user,
                seat_position=2,
                cards_remaining=6
            )

    def test_game_player_ordering(self):
        """Test that game players are ordered by seat position."""
        user2 = User.objects.create_user(username="player2", password="test")
        user3 = User.objects.create_user(username="player3", password="test")

        player2 = GamePlayer.objects.create(
            game=self.game,
            user=user2,
            seat_position=3,
            cards_remaining=6
        )

        player3 = GamePlayer.objects.create(
            game=self.game,
            user=user3,
            seat_position=2,
            cards_remaining=6
        )

        players = list(GamePlayer.objects.filter(game=self.game))
        self.assertEqual(players[0].seat_position, 1)
        self.assertEqual(players[1].seat_position, 2)
        self.assertEqual(players[2].seat_position, 3)


class SpecialCardModelTest(TestCase):
    """Test suite for SpecialCard model."""

    def setUp(self):
        """Set up test data for SpecialCard tests."""
        self.skip_card = SpecialCard.objects.create(
            name="Skip Turn",
            effect_type="skip",
            effect_value={},
            description="Next player loses their turn"
        )

        self.draw_card = SpecialCard.objects.create(
            name="Draw Two",
            effect_type="draw",
            effect_value={"card_count": 2},
            description="Target draws cards"
        )

    def test_special_card_creation(self):
        """Test that SpecialCard instances are created correctly."""
        self.assertEqual(self.skip_card.name, "Skip Turn")
        self.assertEqual(self.skip_card.effect_type, "skip")
        self.assertEqual(self.skip_card.effect_value, {})

    def test_special_card_str_representation(self):
        """Test string representation of SpecialCard."""
        self.assertEqual(str(self.skip_card), "Skip Turn")

    def test_get_effect_description_with_card_count(self):
        """Test get_effect_description() includes card count for draw effects."""
        description = self.draw_card.get_effect_description()
        self.assertIn("2 cards", description)

    def test_get_effect_description_without_card_count(self):
        """Test get_effect_description() returns base description."""
        description = self.skip_card.get_effect_description()
        self.assertEqual(description, "Next player loses their turn")

    def test_is_targetable_method(self):
        """Test is_targetable() for different effect types."""
        self.assertTrue(self.skip_card.is_targetable())
        self.assertTrue(self.draw_card.is_targetable())

        reverse_card = SpecialCard.objects.create(
            name="Reverse",
            effect_type="reverse",
            description="Reverse turn order"
        )
        self.assertFalse(reverse_card.is_targetable())

    def test_can_be_countered_default(self):
        """Test can_be_countered() returns True by default."""
        self.assertTrue(self.skip_card.can_be_countered())

    def test_can_be_countered_explicit(self):
        """Test can_be_countered() respects effect_value setting."""
        uncounterable = SpecialCard.objects.create(
            name="Unstoppable",
            effect_type="custom",
            effect_value={"counterable": False},
            description="Cannot be countered"
        )

        self.assertFalse(uncounterable.can_be_countered())

    def test_special_card_ordering(self):
        """Test that special cards are ordered by name."""
        cards = list(SpecialCard.objects.all())
        self.assertEqual(cards[0].name, "Draw Two")
        self.assertEqual(cards[1].name, "Skip Turn")


class SpecialRuleSetModelTest(TestCase):
    """Test suite for SpecialRuleSet model."""

    def setUp(self):
        """Set up test data for SpecialRuleSet tests."""
        self.rule_set = SpecialRuleSet.objects.create(
            name="Beginner Special",
            description="Simple special cards for new players",
            min_players=2
        )

        self.special_card = SpecialCard.objects.create(
            name="Skip Turn",
            effect_type="skip",
            description="Skip next turn"
        )

    def test_special_rule_set_creation(self):
        """Test that SpecialRuleSet instances are created correctly."""
        self.assertEqual(self.rule_set.name, "Beginner Special")
        self.assertEqual(self.rule_set.min_players, 2)

    def test_special_rule_set_str_representation(self):
        """Test string representation of SpecialRuleSet."""
        self.assertEqual(str(self.rule_set), "Beginner Special")

    def test_get_special_card_count_method(self):
        """Test get_special_card_count() returns correct count."""
        self.assertEqual(self.rule_set.get_special_card_count(), 0)

        SpecialRuleSetCard.objects.create(
            rule_set=self.rule_set,
            card=self.special_card,
            is_enabled=True
        )

        self.assertEqual(self.rule_set.get_special_card_count(), 1)

    def test_is_compatible_with_player_count_method(self):
        """Test is_compatible_with_player_count() validation."""
        self.assertTrue(self.rule_set.is_compatible_with_player_count(2))
        self.assertTrue(self.rule_set.is_compatible_with_player_count(4))
        self.assertFalse(self.rule_set.is_compatible_with_player_count(1))

    def test_get_enabled_special_cards_method(self):
        """Test get_enabled_special_cards() returns only enabled cards."""
        enabled_card = SpecialCard.objects.create(
            name="Enabled",
            effect_type="skip",
            description="Enabled card"
        )

        disabled_card = SpecialCard.objects.create(
            name="Disabled",
            effect_type="skip",
            description="Disabled card"
        )

        SpecialRuleSetCard.objects.create(
            rule_set=self.rule_set,
            card=enabled_card,
            is_enabled=True
        )

        SpecialRuleSetCard.objects.create(
            rule_set=self.rule_set,
            card=disabled_card,
            is_enabled=False
        )

        enabled_cards = self.rule_set.get_enabled_special_cards()
        self.assertEqual(enabled_cards.count(), 1)
        self.assertEqual(enabled_cards.first(), enabled_card)

    def test_can_be_used_in_lobby_method_compatible(self):
        """Test can_be_used_in_lobby() with compatible settings."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='waiting')
        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            allow_jokers=True
        )

        self.assertTrue(self.rule_set.can_be_used_in_lobby(settings))

    def test_can_be_used_in_lobby_method_no_jokers(self):
        """Test can_be_used_in_lobby() fails without jokers enabled."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='waiting')
        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            allow_jokers=False
        )

        self.assertFalse(self.rule_set.can_be_used_in_lobby(settings))

    def test_can_be_used_in_lobby_method_insufficient_players(self):
        """Test can_be_used_in_lobby() fails with too few players."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='waiting')
        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=1,  # Less than min_players
            card_count=36,
            allow_jokers=True
        )

        self.assertFalse(self.rule_set.can_be_used_in_lobby(settings))


class SpecialRuleSetCardModelTest(TestCase):
    """Test suite for SpecialRuleSetCard model."""

    def setUp(self):
        """Set up test data for SpecialRuleSetCard tests."""
        self.rule_set = SpecialRuleSet.objects.create(
            name="Test Rules",
            description="Test rule set",
            min_players=2
        )

        self.special_card = SpecialCard.objects.create(
            name="Skip Turn",
            effect_type="skip",
            description="Skip turn"
        )

        self.rule_set_card = SpecialRuleSetCard.objects.create(
            rule_set=self.rule_set,
            card=self.special_card,
            is_enabled=True
        )

    def test_special_rule_set_card_creation(self):
        """Test that SpecialRuleSetCard instances are created correctly."""
        self.assertEqual(self.rule_set_card.rule_set, self.rule_set)
        self.assertEqual(self.rule_set_card.card, self.special_card)
        self.assertTrue(self.rule_set_card.is_enabled)

    def test_special_rule_set_card_str_representation(self):
        """Test string representation of SpecialRuleSetCard."""
        expected = "Skip Turn in Test Rules (enabled)"
        self.assertEqual(str(self.rule_set_card), expected)

        self.rule_set_card.is_enabled = False
        expected_disabled = "Skip Turn in Test Rules (disabled)"
        self.assertEqual(str(self.rule_set_card), expected_disabled)

    def test_toggle_enabled_method(self):
        """Test toggle_enabled() switches enabled status."""
        self.assertTrue(self.rule_set_card.is_enabled)

        result = self.rule_set_card.toggle_enabled()
        self.assertFalse(result)
        self.rule_set_card.refresh_from_db()
        self.assertFalse(self.rule_set_card.is_enabled)

        result = self.rule_set_card.toggle_enabled()
        self.assertTrue(result)
        self.rule_set_card.refresh_from_db()
        self.assertTrue(self.rule_set_card.is_enabled)

    def test_can_be_used_in_game_enabled(self):
        """Test can_be_used_in_game() with enabled card."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='playing')

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            allow_jokers=True,
            special_rule_set=self.rule_set
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump = Card.objects.create(suit=hearts, rank=ace)

        game = Game.objects.create(
            lobby=lobby,
            trump_card=trump,
            status='in_progress'
        )

        self.assertTrue(self.rule_set_card.can_be_used_in_game(game))

    def test_can_be_used_in_game_disabled(self):
        """Test can_be_used_in_game() with disabled card."""
        self.rule_set_card.is_enabled = False
        self.rule_set_card.save()

        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='playing')

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            allow_jokers=True,
            special_rule_set=self.rule_set
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump = Card.objects.create(suit=hearts, rank=ace)

        game = Game.objects.create(
            lobby=lobby,
            trump_card=trump,
            status='in_progress'
        )

        self.assertFalse(self.rule_set_card.can_be_used_in_game(game))

    def test_can_be_used_in_game_no_jokers(self):
        """Test can_be_used_in_game() fails without jokers."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='playing')

        settings = LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36,
            allow_jokers=False,
            special_rule_set=self.rule_set
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump = Card.objects.create(suit=hearts, rank=ace)

        game = Game.objects.create(
            lobby=lobby,
            trump_card=trump,
            status='in_progress'
        )

        self.assertFalse(self.rule_set_card.can_be_used_in_game(game))

    def test_unique_together_constraint(self):
        """Test that card can only be added to rule set once."""
        with self.assertRaises(IntegrityError):
            SpecialRuleSetCard.objects.create(
                rule_set=self.rule_set,
                card=self.special_card,
                is_enabled=False
            )


class GameDeckModelTest(TestCase):
    """Test suite for GameDeck model."""

    def setUp(self):
        """Set up test data for GameDeck tests."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='playing')

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        self.ace = CardRank.objects.create(name="Ace", value=14)
        self.seven = CardRank.objects.create(name="Seven", value=7)

        self.trump_card = Card.objects.create(suit=hearts, rank=self.ace)
        self.deck_card = Card.objects.create(suit=hearts, rank=self.seven)

        self.game = Game.objects.create(
            lobby=lobby,
            trump_card=self.trump_card,
            status='in_progress'
        )

        self.game_deck = GameDeck.objects.create(
            game=self.game,
            card=self.deck_card,
            position=1
        )

    def test_game_deck_creation(self):
        """Test that GameDeck instances are created correctly."""
        self.assertEqual(self.game_deck.game, self.game)
        self.assertEqual(self.game_deck.card, self.deck_card)
        self.assertEqual(self.game_deck.position, 1)

    def test_game_deck_str_representation(self):
        """Test string representation of GameDeck."""
        self.assertIn("Seven of Hearts", str(self.game_deck))
        self.assertIn("position 1", str(self.game_deck))

    def test_get_top_card_method(self):
        """Test get_top_card() returns lowest position card."""
        spades = CardSuit.objects.create(name="Spades", color="black")
        card2 = Card.objects.create(suit=spades, rank=self.ace)

        GameDeck.objects.create(
            game=self.game,
            card=card2,
            position=2
        )

        top_card = GameDeck.get_top_card(self.game)
        self.assertEqual(top_card.position, 1)
        self.assertEqual(top_card.card, self.deck_card)

    def test_get_top_card_empty_deck(self):
        """Test get_top_card() returns None for empty deck."""
        self.game_deck.delete()

        top_card = GameDeck.get_top_card(self.game)
        self.assertIsNone(top_card)

    def test_draw_card_method(self):
        """Test draw_card() removes and returns top card."""
        drawn_card = GameDeck.draw_card(self.game)

        self.assertEqual(drawn_card, self.deck_card)
        self.assertEqual(GameDeck.objects.filter(game=self.game).count(), 0)

    def test_draw_card_empty_deck(self):
        """Test draw_card() returns None for empty deck."""
        self.game_deck.delete()

        drawn_card = GameDeck.draw_card(self.game)
        self.assertIsNone(drawn_card)

    def test_is_last_card_method(self):
        """Test is_last_card() detection."""
        self.assertTrue(self.game_deck.is_last_card())

        spades = CardSuit.objects.create(name="Spades", color="black")
        card2 = Card.objects.create(suit=spades, rank=self.ace)

        GameDeck.objects.create(
            game=self.game,
            card=card2,
            position=2
        )

        self.assertFalse(self.game_deck.is_last_card())

    def test_game_deck_ordering(self):
        """Test that deck cards are ordered by position."""
        spades = CardSuit.objects.create(name="Spades", color="black")
        king = CardRank.objects.create(name="King", value=13)

        card2 = Card.objects.create(suit=spades, rank=king)
        card3 = Card.objects.create(suit=spades, rank=self.seven)

        GameDeck.objects.create(game=self.game, card=card3, position=3)
        GameDeck.objects.create(game=self.game, card=card2, position=2)

        deck_cards = list(GameDeck.objects.filter(game=self.game))
        self.assertEqual(deck_cards[0].position, 1)
        self.assertEqual(deck_cards[1].position, 2)
        self.assertEqual(deck_cards[2].position, 3)

    def test_unique_together_constraint(self):
        """Test that game and position combination is unique."""
        spades = CardSuit.objects.create(name="Spades", color="black")
        card2 = Card.objects.create(suit=spades, rank=self.ace)

        with self.assertRaises(IntegrityError):
            GameDeck.objects.create(
                game=self.game,
                card=card2,
                position=1  # Same position as existing card
            )


class PlayerHandModelTest(TestCase):
    """Test suite for PlayerHand model."""

    def setUp(self):
        """Set up test data for PlayerHand tests."""
        self.user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=self.user, name="Test", status='playing')

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)

        trump_card = Card.objects.create(suit=hearts, rank=ace)
        self.hand_card = Card.objects.create(
            suit=hearts,
            rank=CardRank.objects.create(name="Seven", value=7)
        )

        self.game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='in_progress'
        )

        self.game_player = GamePlayer.objects.create(
            game=self.game,
            user=self.user,
            seat_position=1,
            cards_remaining=6
        )

        self.player_hand = PlayerHand.objects.create(
            game=self.game,
            player=self.user,
            card=self.hand_card,
            order_in_hand=1
        )

    def test_player_hand_creation(self):
        """Test that PlayerHand instances are created correctly."""
        self.assertEqual(self.player_hand.game, self.game)
        self.assertEqual(self.player_hand.player, self.user)
        self.assertEqual(self.player_hand.card, self.hand_card)
        self.assertEqual(self.player_hand.order_in_hand, 1)

    def test_player_hand_str_representation(self):
        """Test string representation of PlayerHand."""
        self.assertIn("player", str(self.player_hand))
        self.assertIn("Seven of Hearts", str(self.player_hand))

    def test_get_player_hand_method(self):
        """Test get_player_hand() returns all cards for player."""
        spades = CardSuit.objects.create(name="Spades", color="black")
        king = CardRank.objects.create(name="King", value=13)
        card2 = Card.objects.create(suit=spades, rank=king)

        PlayerHand.objects.create(
            game=self.game,
            player=self.user,
            card=card2,
            order_in_hand=2
        )

        hand = PlayerHand.get_player_hand(self.game, self.user)
        self.assertEqual(hand.count(), 2)
        self.assertEqual(hand.first().order_in_hand, 1)
        self.assertEqual(hand.last().order_in_hand, 2)

    def test_get_hand_size_method(self):
        """Test get_hand_size() returns correct count."""
        self.assertEqual(PlayerHand.get_hand_size(self.game, self.user), 1)

        spades = CardSuit.objects.create(name="Spades", color="black")
        king = CardRank.objects.create(name="King", value=13)
        card2 = Card.objects.create(suit=spades, rank=king)

        PlayerHand.objects.create(
            game=self.game,
            player=self.user,
            card=card2,
            order_in_hand=2
        )

        self.assertEqual(PlayerHand.get_hand_size(self.game, self.user), 2)

    def test_remove_from_hand_method(self):
        """Test remove_from_hand() deletes card and updates counter."""
        self.player_hand.remove_from_hand()

        self.assertEqual(PlayerHand.objects.filter(game=self.game, player=self.user).count(), 0)

        self.game_player.refresh_from_db()
        self.assertEqual(self.game_player.cards_remaining, 5)

    def test_remove_from_hand_prevents_negative(self):
        """Test remove_from_hand() doesn't go below zero cards."""
        self.game_player.cards_remaining = 0
        self.game_player.save()

        self.player_hand.remove_from_hand()

        self.game_player.refresh_from_db()
        self.assertEqual(self.game_player.cards_remaining, 0)

    def test_unique_together_constraint(self):
        """Test that same card cannot be in player's hand twice."""
        with self.assertRaises(IntegrityError):
            PlayerHand.objects.create(
                game=self.game,
                player=self.user,
                card=self.hand_card,
                order_in_hand=2
            )

    def test_player_hand_ordering(self):
        """Test that hand cards are ordered by order_in_hand."""
        spades = CardSuit.objects.create(name="Spades", color="black")
        king = CardRank.objects.create(name="King", value=13)
        queen = CardRank.objects.create(name="Queen", value=12)

        card2 = Card.objects.create(suit=spades, rank=king)
        card3 = Card.objects.create(suit=spades, rank=queen)

        PlayerHand.objects.create(
            game=self.game,
            player=self.user,
            card=card3,
            order_in_hand=3
        )

        PlayerHand.objects.create(
            game=self.game,
            player=self.user,
            card=card2,
            order_in_hand=2
        )

        hand = list(PlayerHand.objects.filter(game=self.game, player=self.user))
        self.assertEqual(hand[0].order_in_hand, 1)
        self.assertEqual(hand[1].order_in_hand, 2)
        self.assertEqual(hand[2].order_in_hand, 3)


class TableCardModelTest(TestCase):
    """Test suite for TableCard model."""

    def setUp(self):
        """Set up test data for TableCard tests."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='playing')

        self.hearts = CardSuit.objects.create(name="Hearts", color="red")
        self.spades = CardSuit.objects.create(name="Spades", color="black")

        ace = CardRank.objects.create(name="Ace", value=14)
        seven = CardRank.objects.create(name="Seven", value=7)
        ten = CardRank.objects.create(name="Ten", value=10)

        self.trump_card = Card.objects.create(suit=self.hearts, rank=ace)
        self.attack_card = Card.objects.create(suit=self.hearts, rank=seven)
        self.defense_card = Card.objects.create(suit=self.hearts, rank=ten)

        self.game = Game.objects.create(
            lobby=lobby,
            trump_card=self.trump_card,
            status='in_progress'
        )

        self.table_card = TableCard.objects.create(
            game=self.game,
            attack_card=self.attack_card
        )

    def test_table_card_creation(self):
        """Test that TableCard instances are created correctly."""
        self.assertEqual(self.table_card.game, self.game)
        self.assertEqual(self.table_card.attack_card, self.attack_card)
        self.assertIsNone(self.table_card.defense_card)

    def test_table_card_str_undefended(self):
        """Test string representation of undefended table card."""
        self.assertIn("Seven of Hearts", str(self.table_card))
        self.assertIn("undefended", str(self.table_card))

    def test_table_card_str_defended(self):
        """Test string representation of defended table card."""
        self.table_card.defense_card = self.defense_card
        self.table_card.save()

        self.assertIn("Seven of Hearts", str(self.table_card))
        self.assertIn("defended by", str(self.table_card))
        self.assertIn("Ten of Hearts", str(self.table_card))

    def test_is_defended_method(self):
        """Test is_defended() method."""
        self.assertFalse(self.table_card.is_defended())

        self.table_card.defense_card = self.defense_card
        self.assertTrue(self.table_card.is_defended())

    def test_is_valid_defense_same_suit_higher_rank(self):
        """Test is_valid_defense() with valid same-suit defense."""
        trump_suit = self.spades

        is_valid = self.table_card.is_valid_defense(self.defense_card, trump_suit)
        self.assertTrue(is_valid)

    def test_is_valid_defense_same_suit_lower_rank(self):
        """Test is_valid_defense() fails with lower rank."""
        trump_suit = self.spades

        six = CardRank.objects.create(name="Six", value=6)
        weak_defense = Card.objects.create(suit=self.hearts, rank=six)

        is_valid = self.table_card.is_valid_defense(weak_defense, trump_suit)
        self.assertFalse(is_valid)

    def test_is_valid_defense_trump_vs_non_trump(self):
        """Test is_valid_defense() with trump card defending non-trump."""
        trump_suit = self.spades

        six = CardRank.objects.create(name="Six", value=6)
        trump_defense = Card.objects.create(suit=self.spades, rank=six)

        is_valid = self.table_card.is_valid_defense(trump_defense, trump_suit)
        self.assertTrue(is_valid)

    def test_is_valid_defense_already_defended(self):
        """Test is_valid_defense() returns False if already defended."""
        self.table_card.defense_card = self.defense_card
        self.table_card.save()

        ace = CardRank.objects.create(name="Ace", value=14)
        another_defense = Card.objects.create(suit=self.hearts, rank=ace)

        is_valid = self.table_card.is_valid_defense(another_defense, self.hearts)
        self.assertFalse(is_valid)

    def test_defend_with_valid_defense(self):
        """Test defend_with() successfully defends with valid card."""
        trump_suit = self.spades

        result = self.table_card.defend_with(self.defense_card, trump_suit)

        self.assertTrue(result)
        self.table_card.refresh_from_db()
        self.assertEqual(self.table_card.defense_card, self.defense_card)

    def test_defend_with_invalid_defense(self):
        """Test defend_with() fails with invalid card."""
        trump_suit = self.spades

        six = CardRank.objects.create(name="Six", value=6)
        weak_defense = Card.objects.create(suit=self.hearts, rank=six)

        result = self.table_card.defend_with(weak_defense, trump_suit)

        self.assertFalse(result)
        self.table_card.refresh_from_db()
        self.assertIsNone(self.table_card.defense_card)


class DiscardPileModelTest(TestCase):
    """Test suite for DiscardPile model."""

    def setUp(self):
        """Set up test data for DiscardPile tests."""
        user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=user, name="Test", status='playing')

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        seven = CardRank.objects.create(name="Seven", value=7)

        trump_card = Card.objects.create(suit=hearts, rank=ace)
        self.discarded_card = Card.objects.create(suit=hearts, rank=seven)

        self.game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='in_progress'
        )

        self.discard_pile = DiscardPile.objects.create(
            game=self.game,
            card=self.discarded_card,
            position=1
        )

    def test_discard_pile_creation(self):
        """Test that DiscardPile instances are created correctly."""
        self.assertEqual(self.discard_pile.game, self.game)
        self.assertEqual(self.discard_pile.card, self.discarded_card)
        self.assertEqual(self.discard_pile.position, 1)

    def test_discard_pile_str_with_position(self):
        """Test string representation with position."""
        self.assertIn("Discarded", str(self.discard_pile))
        self.assertIn("Seven of Hearts", str(self.discard_pile))
        self.assertIn("position 1", str(self.discard_pile))

    def test_discard_pile_str_without_position(self):
        """Test string representation without position."""
        discard = DiscardPile.objects.create(
            game=self.game,
            card=self.discarded_card,
            position=None
        )

        result = str(discard)
        self.assertIn("Discarded", result)
        self.assertIn("Seven of Hearts", result)


class TurnModelTest(TestCase):
    """Test suite for Turn model."""

    def setUp(self):
        """Set up test data for Turn tests."""
        self.user1 = User.objects.create_user(username="player1", password="test")
        self.user2 = User.objects.create_user(username="player2", password="test")

        lobby = Lobby.objects.create(owner=self.user1, name="Test", status='playing')

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump_card = Card.objects.create(suit=hearts, rank=ace)

        self.game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='in_progress'
        )

        self.turn = Turn.objects.create(
            game=self.game,
            player=self.user1,
            turn_number=1
        )

    def test_turn_creation(self):
        """Test that Turn instances are created correctly."""
        self.assertEqual(self.turn.game, self.game)
        self.assertEqual(self.turn.player, self.user1)
        self.assertEqual(self.turn.turn_number, 1)

    def test_turn_str_representation(self):
        """Test string representation of Turn."""
        expected = "Turn 1: player1"
        self.assertIn(expected, str(self.turn))

    def test_get_moves_method(self):
        """Test get_moves() returns all moves for turn."""
        # Initially no moves
        self.assertEqual(self.turn.get_moves().count(), 0)

        # Create a move
        seven = CardRank.objects.create(name="Seven", value=7)
        attack_card = Card.objects.create(
            suit=CardSuit.objects.create(name="Spades", color="black"),
            rank=seven
        )

        table_card = TableCard.objects.create(
            game=self.game,
            attack_card=attack_card
        )

        Move.objects.create(
            turn=self.turn,
            table_card=table_card,
            action_type='attack'
        )

        self.assertEqual(self.turn.get_moves().count(), 1)

    def test_is_complete_method(self):
        """Test is_complete() method."""
        self.assertFalse(self.turn.is_complete())

        # Add a move
        seven = CardRank.objects.create(name="Seven", value=7)
        attack_card = Card.objects.create(
            suit=CardSuit.objects.create(name="Spades", color="black"),
            rank=seven
        )

        table_card = TableCard.objects.create(
            game=self.game,
            attack_card=attack_card
        )

        Move.objects.create(
            turn=self.turn,
            table_card=table_card,
            action_type='attack'
        )

        self.assertTrue(self.turn.is_complete())

    def test_get_current_turn_method(self):
        """Test get_current_turn() returns most recent turn."""
        current = Turn.get_current_turn(self.game)
        self.assertEqual(current, self.turn)

        # Create a newer turn
        turn2 = Turn.objects.create(
            game=self.game,
            player=self.user2,
            turn_number=2
        )

        current = Turn.get_current_turn(self.game)
        self.assertEqual(current, turn2)

    def test_get_current_turn_no_turns(self):
        """Test get_current_turn() returns None for game without turns."""
        # Create new game without turns
        lobby = Lobby.objects.create(owner=self.user1, name="New", status='playing')
        hearts = CardSuit.objects.create(name="Diamonds", color="red")
        ace = CardRank.objects.create(name="King", value=13)
        trump = Card.objects.create(suit=hearts, rank=ace)

        new_game = Game.objects.create(
            lobby=lobby,
            trump_card=trump,
            status='in_progress'
        )

        current = Turn.get_current_turn(new_game)
        self.assertIsNone(current)

    def test_create_next_turn_method(self):
        """Test create_next_turn() creates sequential turns."""
        next_turn = Turn.create_next_turn(self.game, self.user2)

        self.assertEqual(next_turn.turn_number, 2)
        self.assertEqual(next_turn.player, self.user2)
        self.assertEqual(next_turn.game, self.game)

    def test_unique_together_constraint(self):
        """Test that game and turn_number combination is unique."""
        with self.assertRaises(IntegrityError):
            Turn.objects.create(
                game=self.game,
                player=self.user2,
                turn_number=1  # Same as existing turn
            )

    def test_turn_ordering(self):
        """Test that turns are ordered by turn_number."""
        turn2 = Turn.objects.create(
            game=self.game,
            player=self.user2,
            turn_number=2
        )

        turn3 = Turn.objects.create(
            game=self.game,
            player=self.user1,
            turn_number=3
        )

        turns = list(Turn.objects.filter(game=self.game))
        self.assertEqual(turns[0].turn_number, 1)
        self.assertEqual(turns[1].turn_number, 2)
        self.assertEqual(turns[2].turn_number, 3)


class MoveModelTest(TestCase):
    """Test suite for Move model."""

    def setUp(self):
        """Set up test data for Move tests."""
        self.user = User.objects.create_user(username="player", password="test")
        lobby = Lobby.objects.create(owner=self.user, name="Test", status='playing')

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        seven = CardRank.objects.create(name="Seven", value=7)

        trump_card = Card.objects.create(suit=hearts, rank=ace)
        attack_card = Card.objects.create(suit=hearts, rank=seven)

        self.game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='in_progress'
        )

        self.turn = Turn.objects.create(
            game=self.game,
            player=self.user,
            turn_number=1
        )

        self.table_card = TableCard.objects.create(
            game=self.game,
            attack_card=attack_card
        )

        self.move = Move.objects.create(
            turn=self.turn,
            table_card=self.table_card,
            action_type='attack'
        )

    def test_move_creation(self):
        """Test that Move instances are created correctly."""
        self.assertEqual(self.move.turn, self.turn)
        self.assertEqual(self.move.table_card, self.table_card)
        self.assertEqual(self.move.action_type, 'attack')

    def test_move_str_representation(self):
        """Test string representation of Move."""
        result = str(self.move)
        self.assertIn("Attack", result)
        self.assertIn("player", result)
        self.assertIn("Seven of Hearts", result)

    def test_get_player_method(self):
        """Test get_player() returns correct user."""
        player = self.move.get_player()
        self.assertEqual(player, self.user)

    def test_is_attack_method(self):
        """Test is_attack() method."""
        self.assertTrue(self.move.is_attack())

        self.move.action_type = 'defend'
        self.assertFalse(self.move.is_attack())

    def test_is_defense_method(self):
        """Test is_defense() method."""
        self.assertFalse(self.move.is_defense())

        self.move.action_type = 'defend'
        self.assertTrue(self.move.is_defense())

    def test_is_pickup_method(self):
        """Test is_pickup() method."""
        self.assertFalse(self.move.is_pickup())

        self.move.action_type = 'pickup'
        self.assertTrue(self.move.is_pickup())

    def test_get_game_moves_method(self):
        """Test get_game_moves() returns all moves for game."""
        # Create another move
        ten = CardRank.objects.create(name="Ten", value=10)
        defense_card = Card.objects.create(
            suit=CardSuit.objects.first(),
            rank=ten
        )

        self.table_card.defense_card = defense_card
        self.table_card.save()

        move2 = Move.objects.create(
            turn=self.turn,
            table_card=self.table_card,
            action_type='defend'
        )

        moves = Move.get_game_moves(self.game)
        self.assertEqual(moves.count(), 2)

    def test_get_player_moves_method(self):
        """Test get_player_moves() returns moves for specific player."""
        user2 = User.objects.create_user(username="player2", password="test")

        turn2 = Turn.objects.create(
            game=self.game,
            player=user2,
            turn_number=2
        )

        spades = CardSuit.objects.create(name="Spades", color="black")
        king = CardRank.objects.create(name="King", value=13)
        card2 = Card.objects.create(suit=spades, rank=king)

        table_card2 = TableCard.objects.create(
            game=self.game,
            attack_card=card2
        )

        Move.objects.create(
            turn=turn2,
            table_card=table_card2,
            action_type='attack'
        )

        # Get moves for user1
        user1_moves = Move.get_player_moves(self.game, self.user)
        self.assertEqual(user1_moves.count(), 1)
        self.assertEqual(user1_moves.first().get_player(), self.user)

        # Get moves for user2
        user2_moves = Move.get_player_moves(self.game, user2)
        self.assertEqual(user2_moves.count(), 1)
        self.assertEqual(user2_moves.first().get_player(), user2)

    def test_move_ordering(self):
        """Test that moves are ordered by creation time."""
        # Create another move slightly later
        ten = CardRank.objects.create(name="Ten", value=10)
        defense_card = Card.objects.create(
            suit=CardSuit.objects.first(),
            rank=ten
        )

        self.table_card.defense_card = defense_card
        self.table_card.save()

        move2 = Move.objects.create(
            turn=self.turn,
            table_card=self.table_card,
            action_type='defend'
        )

        moves = list(Move.objects.filter(turn=self.turn))
        self.assertEqual(moves[0], self.move)
        self.assertEqual(moves[1], move2)

    def test_action_type_choices(self):
        """Test all action type choices are valid."""
        for action_type, _ in Move.ACTION_CHOICES:
            move = Move.objects.create(
                turn=self.turn,
                table_card=self.table_card,
                action_type=action_type
            )
            self.assertEqual(move.action_type, action_type)
