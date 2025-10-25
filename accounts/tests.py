from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from game.models import Lobby, LobbyPlayer, LobbySettings, Game, GamePlayer, Card, CardSuit, CardRank

User = get_user_model()


class UserModelTest(TestCase):
    """Test suite for User model."""

    def setUp(self):
        """Set up test data for User tests."""
        self.user = User.objects.create_user(
            username="testplayer",
            email="test@example.com",
            password="testpass123"
        )

        self.user_with_avatar = User.objects.create_user(
            username="avataruser",
            email="avatar@example.com",
            password="testpass123",
            avatar_url="https://example.com/avatar.jpg"
        )

    def test_user_creation(self):
        """Test that User instances are created correctly."""
        self.assertEqual(self.user.username, "testplayer")
        self.assertEqual(self.user.email, "test@example.com")
        self.assertTrue(self.user.check_password("testpass123"))

    def test_user_uuid_generation(self):
        """Test that UUID is automatically generated for users."""
        self.assertIsNotNone(self.user.id)
        # UUID should be a valid UUID4
        self.assertEqual(len(str(self.user.id)), 36)

    def test_user_str_representation(self):
        """Test string representation of User."""
        self.assertEqual(str(self.user), "testplayer")

    def test_user_created_at_auto_generation(self):
        """Test that created_at timestamp is automatically set."""
        self.assertIsNotNone(self.user.created_at)

    def test_get_full_display_name_with_full_name(self):
        """Test get_full_display_name() returns full name when available."""
        self.user.first_name = "John"
        self.user.last_name = "Doe"
        self.user.save()

        self.assertEqual(self.user.get_full_display_name(), "John Doe")

    def test_get_full_display_name_without_full_name(self):
        """Test get_full_display_name() falls back to username."""
        self.assertEqual(self.user.get_full_display_name(), "testplayer")

    def test_get_full_display_name_with_partial_name(self):
        """Test get_full_display_name() with only first name."""
        self.user.first_name = "John"
        self.user.save()

        self.assertEqual(self.user.get_full_display_name(), "John")

    def test_has_avatar_true(self):
        """Test has_avatar() returns True when avatar is set."""
        self.assertTrue(self.user_with_avatar.has_avatar())

    def test_has_avatar_false(self):
        """Test has_avatar() returns False when avatar is not set."""
        self.assertFalse(self.user.has_avatar())

    def test_has_avatar_empty_string(self):
        """Test has_avatar() returns False for empty string."""
        self.user.avatar_url = ""
        self.user.save()

        self.assertFalse(self.user.has_avatar())

    def test_get_active_lobby_no_lobby(self):
        """Test get_active_lobby() returns None when user is not in a lobby."""
        self.assertIsNone(self.user.get_active_lobby())

    def test_get_active_lobby_waiting_status(self):
        """Test get_active_lobby() returns lobby when user is waiting."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Test Lobby",
            status='waiting'
        )

        LobbyPlayer.objects.create(
            lobby=lobby,
            user=self.user,
            status='waiting'
        )

        self.assertEqual(self.user.get_active_lobby(), lobby)

    def test_get_active_lobby_ready_status(self):
        """Test get_active_lobby() returns lobby when user is ready."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Test Lobby",
            status='waiting'
        )

        LobbyPlayer.objects.create(
            lobby=lobby,
            user=self.user,
            status='ready'
        )

        self.assertEqual(self.user.get_active_lobby(), lobby)

    def test_get_active_lobby_playing_status(self):
        """Test get_active_lobby() returns lobby when user is playing."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Test Lobby",
            status='playing'
        )

        LobbyPlayer.objects.create(
            lobby=lobby,
            user=self.user,
            status='playing'
        )

        self.assertEqual(self.user.get_active_lobby(), lobby)

    def test_get_active_lobby_left_status(self):
        """Test get_active_lobby() returns None when user has left."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Test Lobby",
            status='waiting'
        )

        LobbyPlayer.objects.create(
            lobby=lobby,
            user=self.user,
            status='left'
        )

        self.assertIsNone(self.user.get_active_lobby())

    def test_get_current_game_no_game(self):
        """Test get_current_game() returns None when user is not in a game."""
        self.assertIsNone(self.user.get_current_game())

    def test_get_current_game_active_game(self):
        """Test get_current_game() returns game when user is playing."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Game Lobby",
            status='playing'
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump_card = Card.objects.create(suit=hearts, rank=ace)

        game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='in_progress'
        )

        GamePlayer.objects.create(
            game=game,
            user=self.user,
            seat_position=1,
            cards_remaining=6
        )

        self.assertEqual(self.user.get_current_game(), game)

    def test_get_current_game_finished_game(self):
        """Test get_current_game() returns None for finished games."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Game Lobby",
            status='playing'
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump_card = Card.objects.create(suit=hearts, rank=ace)

        game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='finished'
        )

        GamePlayer.objects.create(
            game=game,
            user=self.user,
            seat_position=1,
            cards_remaining=0
        )

        self.assertIsNone(self.user.get_current_game())

    def test_can_join_lobby_success(self):
        """Test can_join_lobby() returns True for valid join."""
        lobby = Lobby.objects.create(
            owner=self.user_with_avatar,
            name="Open Lobby",
            status='waiting'
        )

        LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36
        )

        self.assertTrue(self.user.can_join_lobby(lobby))

    def test_can_join_lobby_already_in_lobby(self):
        """Test can_join_lobby() returns False when user is already in a lobby."""
        lobby1 = Lobby.objects.create(
            owner=self.user,
            name="Current Lobby",
            status='waiting'
        )

        LobbyPlayer.objects.create(
            lobby=lobby1,
            user=self.user,
            status='waiting'
        )

        lobby2 = Lobby.objects.create(
            owner=self.user_with_avatar,
            name="Other Lobby",
            status='waiting'
        )

        self.assertFalse(self.user.can_join_lobby(lobby2))

    def test_can_join_lobby_full(self):
        """Test can_join_lobby() returns False when lobby is full."""
        lobby = Lobby.objects.create(
            owner=self.user_with_avatar,
            name="Full Lobby",
            status='waiting'
        )

        LobbySettings.objects.create(
            lobby=lobby,
            max_players=2,
            card_count=36
        )

        # Fill the lobby
        user2 = User.objects.create_user(username="player2", password="test")
        user3 = User.objects.create_user(username="player3", password="test")

        LobbyPlayer.objects.create(lobby=lobby, user=user2, status='waiting')
        LobbyPlayer.objects.create(lobby=lobby, user=user3, status='waiting')

        self.assertFalse(self.user.can_join_lobby(lobby))

    def test_can_join_lobby_closed(self):
        """Test can_join_lobby() returns False for closed lobbies."""
        lobby = Lobby.objects.create(
            owner=self.user_with_avatar,
            name="Closed Lobby",
            status='closed'
        )

        # Create settings for the lobby
        LobbySettings.objects.create(
            lobby=lobby,
            max_players=4,
            card_count=36
        )

        self.assertFalse(self.user.can_join_lobby(lobby))

    def test_leave_current_lobby_success(self):
        """Test leave_current_lobby() successfully removes user from lobby."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Test Lobby",
            status='waiting'
        )

        LobbyPlayer.objects.create(
            lobby=lobby,
            user=self.user,
            status='waiting'
        )

        result = self.user.leave_current_lobby()

        self.assertTrue(result)
        self.assertIsNone(self.user.get_active_lobby())

    def test_leave_current_lobby_not_in_lobby(self):
        """Test leave_current_lobby() returns False when not in a lobby."""
        result = self.user.leave_current_lobby()

        self.assertFalse(result)

    def test_leave_current_lobby_already_left(self):
        """Test leave_current_lobby() returns False when already left."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Test Lobby",
            status='waiting'
        )

        LobbyPlayer.objects.create(
            lobby=lobby,
            user=self.user,
            status='left'
        )

        result = self.user.leave_current_lobby()

        self.assertFalse(result)

    def test_get_game_statistics_no_games(self):
        """Test get_game_statistics() with no games played."""
        stats = self.user.get_game_statistics()

        self.assertEqual(stats['total_games'], 0)
        self.assertEqual(stats['games_won'], 0)
        self.assertEqual(stats['games_lost'], 0)
        self.assertEqual(stats['win_rate'], 0.0)

    def test_get_game_statistics_with_wins_and_losses(self):
        """Test get_game_statistics() with mixed results."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Stats Lobby",
            status='playing'
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump_card = Card.objects.create(suit=hearts, rank=ace)

        # Create 3 finished games: 2 wins, 1 loss
        for i in range(3):
            game = Game.objects.create(
                lobby=lobby,
                trump_card=trump_card,
                status='finished',
                loser=self.user if i == 0 else self.user_with_avatar
            )

            GamePlayer.objects.create(
                game=game,
                user=self.user,
                seat_position=1,
                cards_remaining=0
            )

            GamePlayer.objects.create(
                game=game,
                user=self.user_with_avatar,
                seat_position=2,
                cards_remaining=0
            )

        stats = self.user.get_game_statistics()

        self.assertEqual(stats['total_games'], 3)
        self.assertEqual(stats['games_won'], 2)
        self.assertEqual(stats['games_lost'], 1)
        self.assertEqual(stats['win_rate'], 66.7)

    def test_get_game_statistics_all_wins(self):
        """Test get_game_statistics() with all wins."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Stats Lobby",
            status='playing'
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump_card = Card.objects.create(suit=hearts, rank=ace)

        # Create 2 games where user always wins
        for i in range(2):
            game = Game.objects.create(
                lobby=lobby,
                trump_card=trump_card,
                status='finished',
                loser=self.user_with_avatar
            )

            GamePlayer.objects.create(
                game=game,
                user=self.user,
                seat_position=1,
                cards_remaining=0
            )

            GamePlayer.objects.create(
                game=game,
                user=self.user_with_avatar,
                seat_position=2,
                cards_remaining=0
            )

        stats = self.user.get_game_statistics()

        self.assertEqual(stats['total_games'], 2)
        self.assertEqual(stats['games_won'], 2)
        self.assertEqual(stats['games_lost'], 0)
        self.assertEqual(stats['win_rate'], 100.0)

    def test_get_game_statistics_ignores_active_games(self):
        """Test get_game_statistics() only counts finished games."""
        lobby = Lobby.objects.create(
            owner=self.user,
            name="Stats Lobby",
            status='playing'
        )

        hearts = CardSuit.objects.create(name="Hearts", color="red")
        ace = CardRank.objects.create(name="Ace", value=14)
        trump_card = Card.objects.create(suit=hearts, rank=ace)

        # Create an active game
        active_game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='in_progress'
        )

        GamePlayer.objects.create(
            game=active_game,
            user=self.user,
            seat_position=1,
            cards_remaining=6
        )

        # Create a finished game
        finished_game = Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status='finished',
            loser=self.user_with_avatar
        )

        GamePlayer.objects.create(
            game=finished_game,
            user=self.user,
            seat_position=1,
            cards_remaining=0
        )

        GamePlayer.objects.create(
            game=finished_game,
            user=self.user_with_avatar,
            seat_position=2,
            cards_remaining=0
        )

        stats = self.user.get_game_statistics()

        # Should only count the finished game
        self.assertEqual(stats['total_games'], 1)
        self.assertEqual(stats['games_won'], 1)

    def test_user_ordering(self):
        """Test that users are ordered by username."""
        user_z = User.objects.create_user(username="zzz", password="test")
        user_a = User.objects.create_user(username="aaa", password="test")

        users = list(User.objects.all())

        # First user should be alphabetically first
        self.assertEqual(users[0].username, "aaa")
        # Last user should be alphabetically last
        self.assertEqual(users[-1].username, "zzz")

    def test_user_password_hashing(self):
        """Test that passwords are properly hashed."""
        # Password should not be stored in plain text
        self.assertNotEqual(self.user.password, "testpass123")

        # But check_password should work
        self.assertTrue(self.user.check_password("testpass123"))
        self.assertFalse(self.user.check_password("wrongpassword"))

    def test_user_authentication_fields(self):
        """Test that inherited authentication fields work correctly."""
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_create_superuser(self):
        """Test creating a superuser."""
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin123"
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)

    def test_user_email_optional(self):
        """Test that email is optional for users."""
        user_no_email = User.objects.create_user(
            username="noemail",
            password="test123"
        )

        self.assertEqual(user_no_email.email, "")

    def test_avatar_url_validation(self):
        """Test that avatar_url accepts valid URLs."""
        self.user.avatar_url = "https://cdn.example.com/avatars/user123.png"
        self.user.save()

        self.assertEqual(self.user.avatar_url, "https://cdn.example.com/avatars/user123.png")

    def test_user_related_objects_accessible(self):
        """Test that related objects are accessible through reverse relations."""
        # These should not raise AttributeError
        self.assertIsNotNone(self.user.sent_messages)
        self.assertIsNotNone(self.user.received_messages)
        self.assertIsNotNone(self.user.lobby_set)
        self.assertIsNotNone(self.user.lobbyplayer_set)
