"""Tests for special card and rule set models.

This module tests models responsible for custom game rules:
- SpecialCard: Defines special effects like 'skip' or 'draw'.
- SpecialRuleSet: A collection of special card rules.
- SpecialRuleSetCard: Links special cards to a rule set.
"""

import pytest
from game.models import (
    SpecialCard, SpecialRuleSet, SpecialRuleSetCard, LobbySettings
)


@pytest.mark.django_db
class TestSpecialCardModel:
    """Test suite for the SpecialCard model."""

    def test_special_card_creation(self, special_card_draw):
        """Tests that SpecialCard instances are created correctly."""
        assert special_card_draw.name == "Draw Two"
        assert special_card_draw.effect_type == "draw"
        assert special_card_draw.effect_value == {"card_count": 2}

    def test_get_effect_description(self, special_card_draw, special_card_skip):
        """Tests that get_effect_description formats the description correctly."""
        draw_desc = special_card_draw.get_effect_description()
        assert "2 cards" in draw_desc

        skip_desc = special_card_skip.get_effect_description()
        assert skip_desc == "Next player loses their turn"

    def test_is_targetable(self, special_card_skip, special_card_reverse):
        """Tests is_targetable() for different effect types."""
        assert special_card_skip.is_targetable() is True
        assert special_card_reverse.is_targetable() is False

    def test_can_be_countered(self, special_card_skip):
        """Tests can_be_countered() respects the default and explicit values."""
        # Default is counterable
        assert special_card_skip.can_be_countered() is True

        # Explicitly set to not be counterable
        uncounterable = SpecialCard.objects.create(
            name="Unstoppable",
            effect_type="custom",
            effect_value={"counterable": False}
        )
        assert uncounterable.can_be_countered() is False


@pytest.mark.django_db
class TestSpecialRuleSetModel:
    """Test suite for the SpecialRuleSet model."""

    def test_rule_set_creation(self, basic_rule_set):
        """Tests that SpecialRuleSet instances are created correctly."""
        assert basic_rule_set.name == "Beginner Special"
        assert basic_rule_set.min_players == 2

    def test_get_special_card_count(self, basic_rule_set, special_card_skip):
        """Tests get_special_card_count() returns the correct number of cards."""
        assert basic_rule_set.get_special_card_count() == 0
        SpecialRuleSetCard.objects.create(
            rule_set=basic_rule_set, card=special_card_skip, is_enabled=True
        )
        assert basic_rule_set.get_special_card_count() == 1

    def test_get_enabled_special_cards(
            self, basic_rule_set, special_card_skip, special_card_draw
    ):
        """Tests get_enabled_special_cards() returns only enabled cards."""
        # Add one enabled and one disabled card to the rule set
        SpecialRuleSetCard.objects.create(
            rule_set=basic_rule_set, card=special_card_skip, is_enabled=True
        )
        SpecialRuleSetCard.objects.create(
            rule_set=basic_rule_set, card=special_card_draw, is_enabled=False
        )

        enabled_cards = basic_rule_set.get_enabled_special_cards()
        assert enabled_cards.count() == 1
        assert enabled_cards.first() == special_card_skip


@pytest.mark.django_db
class TestSpecialRuleSetCardModel:
    """Test suite for the SpecialRuleSetCard through-model."""

    def test_association_creation(self, basic_rule_set, special_card_skip):
        """Tests the creation of the association between a rule set and a card."""
        association = SpecialRuleSetCard.objects.create(
            rule_set=basic_rule_set, card=special_card_skip, is_enabled=True
        )
        assert association.rule_set == basic_rule_set
        assert association.card == special_card_skip
        assert association.is_enabled is True

    def test_toggle_enabled(self, basic_rule_set, special_card_skip):
        """Tests that toggle_enabled() correctly flips the is_enabled status."""
        association = SpecialRuleSetCard.objects.create(
            rule_set=basic_rule_set, card=special_card_skip, is_enabled=True
        )
        association.toggle_enabled()
        assert association.is_enabled is False
        association.toggle_enabled()
        assert association.is_enabled is True
