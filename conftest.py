"""
Fixtures for testing the Durak card game Django application.

This module provides reusable pytest fixtures for creating users, cards,
lobbies, games, and special cards/rule sets. The fixtures include both
factory-style functions (for flexible object creation) and pre-defined
instances for common test scenarios.

Usage:
    - Import the fixtures in your test modules.
    - Use factory fixtures to create objects with custom attributes.
    - Use pre-defined fixtures for simple, ready-to-use test objects.

Examples:
    def test_user_has_avatar(test_user):
        assert not test_user.has_avatar()

    def test_basic_game_has_trump(basic_game, basic_cards):
        assert basic_game.trump_card == basic_cards['ace_hearts']
"""

import os
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fools_Arena.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from game.models import (
    CardSuit, CardRank, Card, Lobby, LobbySettings,
    Game, GamePlayer, SpecialCard, SpecialRuleSet
)

User = get_user_model()


@pytest.fixture
def user_factory(db):
    """Factory fixture for creating users with custom attributes safely (no IntegrityError).

        Returns:
            callable: Function that creates and returns a User instance.
                Args:
                    username (str): Username for the user. Defaults to 'testuser'.
                    password (str): Password for the user. Defaults to 'test123'.
                    email (str, optional): Email for the user.
                    **kwargs: Additional fields to set on the user.

        Example:
            user = user_factory(username='player1', email='player1@test.com')
        """

    counter = {'i': 0}

    def create_user(username=None, password="test123", **kwargs):
        counter['i'] += 1
        if username is None:
            username = f"player{counter['i']}"
        kwargs.setdefault('email', f'{username}@example.com')

        # if user already exists, return it
        User = get_user_model()
        existing_user = User.objects.filter(username=username).first()
        if existing_user:
            return existing_user

        # else create a new user
        return User.objects.create_user(username=username, password=password, **kwargs)

    return create_user


@pytest.fixture
def test_user(user_factory):
    """Create a default test user.

    Returns:
        User: A user instance with username 'player1'.
    """
    return user_factory(username="player1", email="player1@example.com")


@pytest.fixture
def second_user(user_factory):
    """Create a second test user.

    Returns:
        User: A user instance with username 'player2'.
    """
    return user_factory(username="player2", email="player2@example.com")


@pytest.fixture
def card_suits():
    """Create basic card suits for testing."""
    return {
        'hearts': CardSuit.objects.create(name="Hearts", color="red"),
        'spades': CardSuit.objects.create(name="Spades", color="black"),
        'diamonds': CardSuit.objects.create(name="Diamonds", color="red"),
        'clubs': CardSuit.objects.create(name="Clubs", color="black"),
    }


@pytest.fixture
def card_ranks():
    """Create basic card ranks for testing."""
    return {
        'ace': CardRank.objects.create(name="Ace", value=14),
        'king': CardRank.objects.create(name="King", value=13),
        'queen': CardRank.objects.create(name="Queen", value=12),
        'jack': CardRank.objects.create(name="Jack", value=11),
        'ten': CardRank.objects.create(name="Ten", value=10),
        'seven': CardRank.objects.create(name="Seven", value=7),
        'six': CardRank.objects.create(name="Six", value=6),
    }


@pytest.fixture
def basic_cards(card_suits, card_ranks):
    """Create basic cards for testing."""
    return {
        'ace_hearts': Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        ),
        'seven_hearts': Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['seven']
        ),
        'king_spades': Card.objects.create(
            suit=card_suits['spades'],
            rank=card_ranks['king']
        ),
        'six_diamonds': Card.objects.create(
            suit=card_suits['diamonds'],
            rank=card_ranks['six']
        ),
    }


@pytest.fixture
def lobby_factory():
    """Factory fixture for creating lobbies with customizable settings.

    Returns:
        callable: Function that creates and returns a Lobby instance with settings.
            Args:
                owner (User): The user who owns the lobby.
                name (str): Name of the lobby. Defaults to 'Test Lobby'.
                status (str): Lobby status. Defaults to 'waiting'.
                **kwargs: Additional lobby and settings parameters:
                    - is_private (bool): Whether lobby is private.
                    - password_hash (str): Hashed password for private lobbies.
                    - max_players (int): Maximum number of players.
                    - card_count (int): Number of cards in deck (24, 36, or 52).
                    - is_transferable (bool): Allow card transfers.
                    - neighbor_throw_only (bool): Restrict throws to neighbors.
                    - allow_jokers (bool): Include jokers in deck.
                    - turn_time_limit (int): Time limit per turn in seconds.
                    - special_rule_set (SpecialRuleSet): Special rules to apply.

    Example:
        lobby = lobby_factory(
            owner=user,
            name='Pro Game',
            max_players=6,
            is_transferable=True
        )
    """

    def create_lobby(owner, name="Test Lobby", status='waiting', **kwargs):
        lobby = Lobby.objects.create(
            owner=owner,
            name=name,
            status=status,
            is_private=kwargs.get('is_private', False),
            password_hash=kwargs.get('password_hash', None)
        )

        # Automatically create lobby settings with provided or default values
        LobbySettings.objects.create(
            lobby=lobby,
            max_players=kwargs.get('max_players', 4),
            card_count=kwargs.get('card_count', 36),
            is_transferable=kwargs.get('is_transferable', False),
            neighbor_throw_only=kwargs.get('neighbor_throw_only', False),
            allow_jokers=kwargs.get('allow_jokers', False),
            turn_time_limit=kwargs.get('turn_time_limit', None),
            special_rule_set=kwargs.get('special_rule_set', None)
        )

        return lobby

    return create_lobby


@pytest.fixture
def basic_lobby(test_user, lobby_factory):
    """Create a basic lobby for testing.

    Args:
        test_user: Fixture providing a default test user.
        lobby_factory: Fixture providing lobby creation function.

    Returns:
        Lobby: A lobby instance with default settings.
    """
    return lobby_factory(owner=test_user)


@pytest.fixture
def game_factory(db):
    """Factory fixture for creating game instances.

    Returns:
        callable: Function that creates and returns a Game instance.
            Args:
                lobby (Lobby): The lobby associated with this game.
                trump_card (Card): The trump card for this game.
                status (str): Game status. Defaults to 'in_progress'.
                **kwargs: Additional game parameters:
                    - loser (User): The losing player (for finished games).
                    - finished_at (datetime): When the game finished.

    Example:
        game = game_factory(
            lobby=lobby,
            trump_card=ace_of_hearts,
            status='in_progress'
        )
    """

    def create_game(lobby, trump_card, status='in_progress', **kwargs):
        return Game.objects.create(
            lobby=lobby,
            trump_card=trump_card,
            status=status,
            loser=kwargs.get('loser', None),
            finished_at=kwargs.get('finished_at', None)
        )

    return create_game


@pytest.fixture
def basic_game(basic_lobby, basic_cards, game_factory):
    """Create a basic game ready for testing.

    Args:
        basic_lobby: Fixture providing a basic lobby.
        basic_cards: Fixture providing basic card instances.
        game_factory: Fixture providing game creation function.

    Returns:
        Game: A game instance in 'in_progress' status with ace of hearts as trump.

    Note:
        The associated lobby's status is changed to 'playing'.
    """
    basic_lobby.status = 'playing'
    basic_lobby.save()
    return game_factory(
        lobby=basic_lobby,
        trump_card=basic_cards['ace_hearts']
    )


@pytest.fixture
def game_player_factory(db):
    """Factory fixture for creating game player instances.

    Returns:
        callable: Function that creates and returns a GamePlayer instance.
            Args:
                game (Game): The game instance.
                user (User): The player's user instance.
                seat_position (int): Player's seat position (1-based).
                cards_remaining (int): Number of cards in player's hand.

    Example:
        player = game_player_factory(
            game=game,
            user=user,
            seat_position=1,
            cards_remaining=6
        )
    """

    def create_game_player(game, user, seat_position, cards_remaining=6):
        return GamePlayer.objects.create(
            game=game,
            user=user,
            seat_position=seat_position,
            cards_remaining=cards_remaining
        )

    return create_game_player


@pytest.fixture
def special_card_skip(db):
    """Create a special card with skip effect.

    Returns:
        SpecialCard: A special card that skips the next player's turn.
    """
    return SpecialCard.objects.create(
        name="Skip Turn",
        effect_type="skip",
        effect_value={},
        description="Next player loses their turn"
    )


@pytest.fixture
def special_card_draw(db):
    """Create a special card with draw effect.

    Returns:
        SpecialCard: A special card that makes target draw 2 cards.
    """
    return SpecialCard.objects.create(
        name="Draw Two",
        effect_type="draw",
        effect_value={"card_count": 2},
        description="Target draws cards"
    )


@pytest.fixture
def special_card_reverse(db):
    """Create a special card with reverse effect.

    Returns:
        SpecialCard: A special card that reverses turn order.
    """
    return SpecialCard.objects.create(
        name="Reverse",
        effect_type="reverse",
        effect_value={},
        description="Reverse turn order"
    )


@pytest.fixture
def basic_rule_set(db):
    """Create a basic special rule set for testing.

    Returns:
        SpecialRuleSet: A rule set with minimum 2 players requirement.
    """
    return SpecialRuleSet.objects.create(
        name="Beginner Special",
        description="Simple special cards for new players",
        min_players=2
    )

@pytest.fixture
def api_client():
    """DRF APIClient for API-tests."""
    return APIClient()
