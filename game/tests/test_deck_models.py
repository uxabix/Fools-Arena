"""Tests for deck and card management models.

This module tests models responsible for managing the state of cards in the game:
- GameDeck: The main draw pile.
- PlayerHand: Cards held by a player.
- TableCard: Attacking and defending cards in play.
- DiscardPile: Cards that are out of play.
"""

import pytest
from game.models import (
    GameDeck, PlayerHand, TableCard, DiscardPile, GamePlayer
)


@pytest.mark.django_db
class TestGameDeckModel:
    """Test suite for the GameDeck model."""

    def test_game_deck_creation(self, basic_game, basic_cards):
        """Tests that GameDeck entries are created correctly."""
        deck_card = GameDeck.objects.create(
            game=basic_game, card=basic_cards['ace_hearts'], position=1
        )
        assert deck_card.game == basic_game
        assert deck_card.card == basic_cards['ace_hearts']
        assert deck_card.position == 1

    def test_get_top_card(self, basic_game, basic_cards):
        """Tests get_top_card() returns the card with the lowest position."""
        card1 = GameDeck.objects.create(game=basic_game, card=basic_cards['ace_hearts'], position=1)
        GameDeck.objects.create(game=basic_game, card=basic_cards['king_spades'], position=2)

        assert GameDeck.get_top_card(basic_game) == card1

    def test_draw_card(self, basic_game, basic_cards):
        """Tests draw_card() removes and returns the top card."""
        GameDeck.objects.create(game=basic_game, card=basic_cards['ace_hearts'], position=1)
        GameDeck.objects.create(game=basic_game, card=basic_cards['king_spades'], position=2)

        drawn_card = GameDeck.draw_card(basic_game)
        assert drawn_card == basic_cards['ace_hearts']
        assert GameDeck.objects.filter(game=basic_game).count() == 1
        assert GameDeck.get_top_card(basic_game).card == basic_cards['king_spades']

    def test_is_last_card(self, basic_game, basic_cards):
        """Tests is_last_card() correctly identifies the final card."""
        card1 = GameDeck.objects.create(game=basic_game, card=basic_cards['ace_hearts'], position=1)
        assert card1.is_last_card() is True
        card2 = GameDeck.objects.create(game=basic_game, card=basic_cards['king_spades'], position=2)
        assert card1.is_last_card() is False
        assert card2.is_last_card() is True


@pytest.mark.django_db
class TestPlayerHandModel:
    """Test suite for the PlayerHand model."""

    def test_player_hand_creation(self, basic_game, test_user, basic_cards):
        """Tests that PlayerHand entries are created correctly."""
        hand_card = PlayerHand.objects.create(
            game=basic_game, player=test_user, card=basic_cards['ace_hearts'], order_in_hand=1
        )
        assert hand_card.game == basic_game
        assert hand_card.player == test_user
        assert hand_card.card == basic_cards['ace_hearts']

    def test_get_player_hand(self, basic_game, test_user, basic_cards):
        """Tests get_player_hand() returns all cards for a player, ordered."""
        PlayerHand.objects.create(game=basic_game, player=test_user, card=basic_cards['ace_hearts'], order_in_hand=2)
        PlayerHand.objects.create(game=basic_game, player=test_user, card=basic_cards['king_spades'], order_in_hand=1)

        hand = list(PlayerHand.get_player_hand(basic_game, test_user))
        assert len(hand) == 2
        assert hand[0].card == basic_cards['king_spades']
        assert hand[1].card == basic_cards['ace_hearts']

    def test_remove_from_hand(self, basic_game, test_user, basic_cards):
        """Tests remove_from_hand() deletes the card and updates the player's card count."""
        game_player = GamePlayer.objects.create(
            game=basic_game, user=test_user, seat_position=1, cards_remaining=1
        )
        hand_card = PlayerHand.objects.create(
            game=basic_game, player=test_user, card=basic_cards['ace_hearts']
        )
        hand_card.remove_from_hand()

        game_player.refresh_from_db()
        assert not PlayerHand.objects.filter(pk=hand_card.pk).exists()
        assert game_player.cards_remaining == 0


@pytest.mark.django_db
class TestTableCardModel:
    """Test suite for the TableCard model."""

    def test_table_card_creation(self, basic_game, basic_cards):
        """Tests that TableCard instances are created correctly."""
        table_card = TableCard.objects.create(
            game=basic_game, attack_card=basic_cards['seven_hearts']
        )
        assert table_card.game == basic_game
        assert table_card.attack_card == basic_cards['seven_hearts']
        assert table_card.defense_card is None

    def test_is_defended(self, basic_game, basic_cards):
        """Tests is_defended() method."""
        table_card = TableCard.objects.create(
            game=basic_game, attack_card=basic_cards['seven_hearts']
        )
        assert table_card.is_defended() is False
        table_card.defense_card = basic_cards['ace_hearts']
        assert table_card.is_defended() is True

    def test_defend_with_valid_card(self, basic_game, card_suits, basic_cards):
        """Tests defend_with() successfully updates defense_card with a valid defense."""
        table_card = TableCard.objects.create(
            game=basic_game, attack_card=basic_cards['seven_hearts']
        )
        # Trump suit is Hearts, so any Heart can beat another Heart if it's higher rank
        trump_suit = card_suits['hearts']
        result = table_card.defend_with(basic_cards['ace_hearts'], trump_suit)

        assert result is True
        table_card.refresh_from_db()
        assert table_card.defense_card == basic_cards['ace_hearts']

    def test_defend_with_invalid_card(self, basic_game, card_suits, basic_cards):
        """Tests defend_with() fails to update with an invalid defense card."""
        table_card = TableCard.objects.create(
            game=basic_game, attack_card=basic_cards['ace_hearts']
        )
        # seven_hearts cannot beat ace_hearts
        trump_suit = card_suits['hearts']
        result = table_card.defend_with(basic_cards['seven_hearts'], trump_suit)

        assert result is False
        table_card.refresh_from_db()
        assert table_card.defense_card is None


@pytest.mark.django_db
class TestDiscardPileModel:
    """Test suite for the DiscardPile model."""

    def test_discard_pile_creation(self, basic_game, basic_cards):
        """Tests that DiscardPile entries are created correctly."""
        discarded = DiscardPile.objects.create(
            game=basic_game, card=basic_cards['ace_hearts'], position=1
        )
        assert discarded.game == basic_game
        assert discarded.card == basic_cards['ace_hearts']
        assert discarded.position == 1
