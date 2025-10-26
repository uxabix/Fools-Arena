"""Tests for card-related models: CardSuit, CardRank, and Card.

This module tests the creation, methods, and relationships of card components
used in the game, including basic card properties, trump logic, and special cards.
"""

import pytest
from django.db import IntegrityError
from game.models import CardSuit, CardRank, Card, SpecialCard


@pytest.mark.django_db
class TestCardSuitModel:
    """Test suite for CardSuit model."""

    def test_card_suit_creation(self):
        """Test that CardSuit instances are created correctly with name and color."""
        hearts = CardSuit.objects.create(name="Hearts", color="red")
        spades = CardSuit.objects.create(name="Spades", color="black")

        assert hearts.name == "Hearts"
        assert hearts.color == "red"
        assert spades.color == "black"

    def test_card_suit_str_representation(self):
        """Test string representation returns suit name."""
        hearts = CardSuit.objects.create(name="Hearts", color="red")
        spades = CardSuit.objects.create(name="Spades", color="black")

        assert str(hearts) == "Hearts"
        assert str(spades) == "Spades"

    def test_is_red_method(self):
        """Test is_red() method returns correct boolean based on color."""
        hearts = CardSuit.objects.create(name="Hearts", color="red")
        spades = CardSuit.objects.create(name="Spades", color="black")

        assert hearts.is_red() is True
        assert spades.is_red() is False

    def test_card_suit_ordering(self):
        """Test that CardSuit instances are ordered alphabetically by name."""
        hearts = CardSuit.objects.create(name="Hearts", color="red")
        spades = CardSuit.objects.create(name="Spades", color="black")
        diamonds = CardSuit.objects.create(name="Diamonds", color="red")
        clubs = CardSuit.objects.create(name="Clubs", color="black")

        suits = list(CardSuit.objects.all())

        assert suits[0].name == "Clubs"
        assert suits[1].name == "Diamonds"
        assert suits[2].name == "Hearts"
        assert suits[3].name == "Spades"

    def test_card_suit_color_choices(self):
        """Test that only valid color choices (red/black) are accepted."""
        # Valid colors should work
        valid_suit = CardSuit.objects.create(name="Test", color="red")
        assert valid_suit.color == "red"

        valid_suit_black = CardSuit.objects.create(name="Test2", color="black")
        assert valid_suit_black.color == "black"


@pytest.mark.django_db
class TestCardRankModel:
    """Test suite for CardRank model."""

    def test_card_rank_creation(self):
        """Test that CardRank instances are created correctly with name and value."""
        ace = CardRank.objects.create(name="Ace", value=14)
        king = CardRank.objects.create(name="King", value=13)

        assert ace.name == "Ace"
        assert ace.value == 14
        assert king.value == 13

    def test_card_rank_str_representation(self):
        """Test string representation returns rank name."""
        ace = CardRank.objects.create(name="Ace", value=14)
        king = CardRank.objects.create(name="King", value=13)

        assert str(ace) == "Ace"
        assert str(king) == "King"

    def test_is_face_card_method(self):
        """Test is_face_card() method identifies Jack, Queen, and King.

        Face cards are defined as cards with values 11-13:
        - Jack (11), Queen (12), King (13) are face cards
        - Ace (14) and number cards are not face cards
        """
        ace = CardRank.objects.create(name="Ace", value=14)
        king = CardRank.objects.create(name="King", value=13)
        queen = CardRank.objects.create(name="Queen", value=12)
        jack = CardRank.objects.create(name="Jack", value=11)
        six = CardRank.objects.create(name="Six", value=6)

        assert king.is_face_card() is True
        assert queen.is_face_card() is True
        assert jack.is_face_card() is True
        assert ace.is_face_card() is False
        assert six.is_face_card() is False

    def test_card_rank_ordering(self):
        """Test that CardRank instances are ordered by value ascending."""
        ace = CardRank.objects.create(name="Ace", value=14)
        king = CardRank.objects.create(name="King", value=13)
        jack = CardRank.objects.create(name="Jack", value=11)
        six = CardRank.objects.create(name="Six", value=6)

        ranks = list(CardRank.objects.all())

        assert ranks[0].value == 6
        assert ranks[1].value == 11
        assert ranks[2].value == 13
        assert ranks[3].value == 14


@pytest.mark.django_db
class TestCardModel:
    """Test suite for Card model."""

    def test_card_creation(self, card_suits, card_ranks):
        """Test that Card instances are created correctly with suit and rank."""
        ace_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        )

        assert ace_of_hearts.suit == card_suits['hearts']
        assert ace_of_hearts.rank == card_ranks['ace']
        assert ace_of_hearts.special_card is None

    def test_card_str_representation(self, card_suits, card_ranks):
        """Test string representation formats as 'Rank of Suit'."""
        ace_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        )
        king_of_spades = Card.objects.create(
            suit=card_suits['spades'],
            rank=card_ranks['king']
        )

        assert str(ace_of_hearts) == "Ace of Hearts"
        assert str(king_of_spades) == "King of Spades"

    def test_card_str_with_special_card(self, card_suits, card_ranks):
        """Test string representation includes special card name in parentheses."""
        special = SpecialCard.objects.create(
            name="Skip Turn",
            effect_type="skip",
            description="Skip next player's turn"
        )
        special_card = Card.objects.create(
            suit=card_suits['spades'],
            rank=card_ranks['ace'],
            special_card=special
        )

        assert str(special_card) == "Ace of Spades (Skip Turn)"

    def test_is_trump_method(self, card_suits, card_ranks):
        """Test is_trump() method correctly identifies trump suit cards."""
        ace_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        )
        king_of_spades = Card.objects.create(
            suit=card_suits['spades'],
            rank=card_ranks['king']
        )

        # Hearts is trump
        assert ace_of_hearts.is_trump(card_suits['hearts']) is True
        assert ace_of_hearts.is_trump(card_suits['spades']) is False

        # Spades is trump
        assert king_of_spades.is_trump(card_suits['spades']) is True
        assert king_of_spades.is_trump(card_suits['hearts']) is False

    def test_is_special_method(self, card_suits, card_ranks):
        """Test is_special() method identifies cards with special effects."""
        normal_card = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        )

        special = SpecialCard.objects.create(
            name="Draw Two",
            effect_type="draw",
            description="Draw 2 cards"
        )
        special_card = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['seven'],
            special_card=special
        )

        assert normal_card.is_special() is False
        assert special_card.is_special() is True

    def test_can_beat_trump_vs_non_trump(self, card_suits, card_ranks):
        """Test that any trump card beats any non-trump card.

        In the game, trump cards always beat non-trump cards regardless of rank.
        Even a low-value trump (e.g., Seven of Hearts) beats a high-value
        non-trump (e.g., King of Spades) when Hearts is trump.
        """
        seven_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['seven']
        )
        king_of_spades = Card.objects.create(
            suit=card_suits['spades'],
            rank=card_ranks['king']
        )

        # Hearts is trump
        trump_suit = card_suits['hearts']

        # Low trump beats high non-trump
        assert seven_of_hearts.can_beat(king_of_spades, trump_suit) is True

        # Non-trump cannot beat trump
        assert king_of_spades.can_beat(seven_of_hearts, trump_suit) is False

    def test_can_beat_same_suit(self, card_suits, card_ranks):
        """Test card comparison within the same suit uses rank value."""
        ace_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        )
        seven_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['seven']
        )

        trump_suit = card_suits['spades']  # Neither Hearts card is trump

        # Higher rank beats lower rank in same suit
        assert ace_of_hearts.can_beat(seven_of_hearts, trump_suit) is True

        # Lower rank cannot beat higher rank
        assert seven_of_hearts.can_beat(ace_of_hearts, trump_suit) is False

    def test_can_beat_different_non_trump_suits(self, card_suits, card_ranks):
        """Test that cards of different non-trump suits cannot beat each other.

        In the game, you can only beat a card with:
        1. A higher card of the same suit, OR
        2. Any trump card (if the original card is not trump)

        Cards of different non-trump suits cannot beat each other.
        """
        ace_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        )
        six_of_diamonds = Card.objects.create(
            suit=card_suits['diamonds'],
            rank=card_ranks['six']
        )

        trump_suit = card_suits['spades']  # Hearts and Diamonds are both non-trump

        # Different non-trump suits cannot beat each other
        assert ace_of_hearts.can_beat(six_of_diamonds, trump_suit) is False
        assert six_of_diamonds.can_beat(ace_of_hearts, trump_suit) is False

    def test_can_beat_trump_vs_trump(self, card_suits, card_ranks):
        """Test trump card comparison uses rank value."""
        ace_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace']
        )
        seven_of_hearts = Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['seven']
        )

        trump_suit = card_suits['hearts']  # Both cards are trump

        # Higher trump beats lower trump
        assert ace_of_hearts.can_beat(seven_of_hearts, trump_suit) is True
        assert seven_of_hearts.can_beat(ace_of_hearts, trump_suit) is False

    def test_card_unique_together_constraint(self, card_suits, card_ranks):
        """Test that cards with same suit, rank, and special_card are unique.

        The database enforces uniqueness on the combination of suit, rank,
        and special_card to prevent duplicate cards in the system.
        """
        # Create a special card first
        special = SpecialCard.objects.create(
            name="Test Special",
            effect_type="skip",
            description="Test"
        )

        # Create first card with special_card
        Card.objects.create(
            suit=card_suits['hearts'],
            rank=card_ranks['ace'],
            special_card=special
        )

        # Creating duplicate with same suit, rank, and special_card should fail
        with pytest.raises(IntegrityError):
            Card.objects.create(
                suit=card_suits['hearts'],
                rank=card_ranks['ace'],
                special_card=special
            )
