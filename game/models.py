"""Game models for the Durak card game application.

This module contains all the Django models that define the game logic,
lobby management, card representations, and player interactions for
the online multiplayer Durak card game.
"""

import uuid
from django.db import models

class CardSuit(models.Model):
    """Card suit model representing playing card suits (Hearts, Diamonds, etc.).
    
    Defines the four traditional card suits with their display names and colors.
    Used as a lookup table for card generation and game logic.
    
    """

    id = models.SmallAutoField(primary_key=True)
    name = models.CharField(max_length=20)
    color = models.CharField(max_length=5, choices=[('red', 'Red'), ('black', 'Black')])

    def __str__(self):
        """Return string representation of the card suit.
        
        Returns:
            str: The name of the suit.
        """
        return self.name

    def is_red(self):
        """Check if the suit is red (Hearts or Diamonds).
        
        Returns:
            bool: True if the suit is red, False otherwise.
        """
        return self.color == 'red'

    class Meta:
        verbose_name = 'Card Suit'
        verbose_name_plural = 'Card Suits'
        ordering = ['name']

class CardRank(models.Model):
    """Card rank model representing playing card values (Ace, King, etc.).
    
    Defines the ranks/values of playing cards with their display names
    and numeric values for comparison during gameplay.
    
    """

    id = models.SmallAutoField(primary_key=True)
    name = models.CharField(max_length=20)
    value = models.IntegerField()

    def __str__(self):
        """Return string representation of the card rank.
        
        Returns:
            str: The name of the rank.
        """
        return self.name

    def is_face_card(self):
        """Check if this is a face card (Jack, Queen, King).
        
        Returns:
            bool: True if value indicates a face card (typically 11-13).
        """
        return 11 <= self.value <= 13

    class Meta:
        verbose_name = 'Card Rank'
        verbose_name_plural = 'Card Ranks'
        ordering = ['value']

class Lobby(models.Model):
    """Game lobby model for organizing players before starting games.
    
    Represents a game room where players can gather, chat, and prepare
    to start a Durak game session. Handles lobby ownership, privacy
    settings, and player management.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    is_private = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=128, null=True, blank=True)
    status = models.CharField(max_length=10,
                              choices=[('waiting', 'Waiting'), ('playing', 'Playing'), ('closed', 'Closed')])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return string representation of the lobby.
        
        Returns:
            str: The name of the lobby.
        """
        return self.name

    def is_full(self):
        """Check if the lobby has reached its maximum player capacity.
        
        Returns:
            bool: True if lobby is at max capacity, False otherwise.
        """
        current_players = self.players.filter(status__in=['waiting', 'ready', 'playing']).count()
        return current_players >= self.settings.max_players

    def can_start_game(self):
        """Check if the lobby has enough ready players to start a game.
        
        Returns:
            bool: True if there are at least 2 ready players and lobby is waiting.
        """
        if self.status != 'waiting':
            return False
        ready_players = self.players.filter(status='ready').count()
        return ready_players >= 2

    def get_active_players(self):
        """Get all active players in the lobby.
        
        Returns:
            QuerySet: LobbyPlayer objects with active status.
        """
        return self.players.filter(status__in=['waiting', 'ready', 'playing'])

    class Meta:
        verbose_name = 'Lobby'
        verbose_name_plural = 'Lobbies'
        ordering = ['-created_at']

class LobbySettings(models.Model):
    """Configuration settings for a game lobby.
    
    Defines the rules and parameters that will be applied to games
    started within the associated lobby. Each lobby has exactly one
    settings configuration.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lobby = models.OneToOneField(Lobby, on_delete=models.CASCADE, related_name='settings')
    max_players = models.PositiveIntegerField()
    card_count = models.IntegerField(choices=[(24, '24'), (36, '36'), (52, '52')])
    is_transferable = models.BooleanField(default=False)
    neighbor_throw_only = models.BooleanField(default=False)
    allow_jokers = models.BooleanField(default=False)
    turn_time_limit = models.IntegerField(null=True, blank=True)
    special_rule_set = models.ForeignKey('SpecialRuleSet', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        """Return string representation of the lobby settings.
        
        Returns:
            str: Summary of key settings.
        """
        return f"{self.lobby.name} Settings ({self.card_count} cards, {self.max_players} players)"

    def has_time_limit(self):
        """Check if the lobby has a turn time limit enabled.
        
        Returns:
            bool: True if turn_time_limit is set or not equals 0, False otherwise.
        """
        if self.turn_time_limit is None:
            return False
        else:
            return self.turn_time_limit > 0

    def is_beginner_friendly(self):
        """Check if settings are suitable for beginner players.
        
        Returns:
            bool: True if settings use standard rules without complex features.
        """
        return (not self.is_transferable and
                not self.allow_jokers and
                self.special_rule_set is None)

    class Meta:
        verbose_name = 'Lobby Settings'
        verbose_name_plural = 'Lobby Settings'

class LobbyPlayer(models.Model):
    """Relationship model connecting users to lobbies with their status.
    
    Represents a player's membership in a specific lobby, tracking their
    current status and readiness to play. Handles the player lifecycle
    from joining to leaving the lobby.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lobby = models.ForeignKey(Lobby, on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    status = models.CharField(max_length=10,
                              choices=[('waiting', 'Waiting'), ('ready', 'Ready'), ('playing', 'Playing'),
                                       ('left', 'Left')])

    def __str__(self):
        """Return string representation of the lobby player.
        
        Returns:
            str: Username and status in the lobby.
        """
        return f"{self.user.username} ({self.status}) in {self.lobby.name}"

    def is_active(self):
        """Check if the player is actively participating in the lobby.
        
        Returns:
            bool: True if player status is not 'left', False otherwise.
        """
        return self.status != 'left'

    def can_start_game(self):
        """Check if the player is ready to start a game.
        
        Returns:
            bool: True if player status is 'ready', False otherwise.
        """
        return self.status == 'ready'

    def leave_lobby(self):
        """Mark the player as having left the lobby.
        
        Updates the player's status to 'left' and saves the record.
        """
        self.status = 'left'
        self.save(update_fields=['status'])

    class Meta:
        verbose_name = 'Lobby Player'
        verbose_name_plural = 'Lobby Players'
        unique_together = ['lobby', 'user']
        ordering = ['lobby', 'user__username']

class Game(models.Model):
    """Core game session model for Durak card game.
    
    Represents an active or completed game session within a lobby.
    Handles game state, trump card selection, and player management.
    Each game is linked to a specific lobby and tracks all game-related data.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lobby = models.ForeignKey(Lobby, on_delete=models.CASCADE)
    trump_card = models.ForeignKey('Card', on_delete=models.PROTECT, related_name='as_trump')
    # attacker_id, defender_id, phase: build | defend | between
    runtime_state = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=[('in_progress', 'In Progress'), ('finished', 'Finished')])
    loser = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        """Return string representation of the game.
        
        Returns:
            str: Game info with lobby name and status.
        """
        return f"Game in {self.lobby.name} ({self.status})"

    def is_active(self):
        """Check if the game is currently in progress.
        
        Returns:
            bool: True if status is 'in_progress', False otherwise.
        """
        return self.status == 'in_progress'

    def get_trump_suit(self):
        """Get the trump suit for this game.
        
        Returns:
            CardSuit: The suit of the trump card.
        """
        return self.trump_card.suit

    def get_player_count(self):
        """Get the number of players in this game.
        
        Returns:
            int: Count of GamePlayer objects associated with this game.
        """
        return self.players.count()

    def get_winner(self):
        """Get the winner of the game (all players except the loser).
        
        Returns:
            QuerySet: GamePlayer objects representing winners, or None if game is active.
        """
        if self.status != 'finished' or not self.loser:
            return None
        return self.players.exclude(user=self.loser)

    class Meta:
        verbose_name = 'Game'
        verbose_name_plural = 'Games'
        ordering = ['-started_at']

class GamePlayer(models.Model):
    """Relationship model connecting users to game sessions with game-specific data.
    
    Represents a player's participation in a specific game, tracking their
    position, remaining cards, and other game-state information.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    seat_position = models.IntegerField()
    cards_remaining = models.IntegerField()

    def __str__(self):
        """Return string representation of the game player.
        
        Returns:
            str: Player info with username and card count.
        """
        return f"{self.user.username} ({self.cards_remaining} cards) - Position {self.seat_position}"

    def has_cards(self):
        """Check if the player still has cards in their hand.
        
        Returns:
            bool: True if cards_remaining > 0, False otherwise.
        """
        return self.cards_remaining > 0

    def is_eliminated(self):
        """Check if the player has been eliminated (no cards left).
        
        Returns:
            bool: True if player has no cards remaining, False otherwise.
        """
        return self.cards_remaining == 0

    def get_hand_cards(self):
        """Get all cards currently in this player's hand.
        
        Returns:
            QuerySet: PlayerHand objects representing cards in hand.
        """
        return PlayerHand.objects.filter(game=self.game, player=self.user)

    class Meta:
        verbose_name = 'Game Player'
        verbose_name_plural = 'Game Players'
        unique_together = ['game', 'user']
        ordering = ['seat_position']

class Card(models.Model):
    """Playing card model combining suit, rank, and optional special properties.
    
    Represents an individual playing card with its suit, rank, and any
    special abilities. Cards can be standard playing cards or special
    cards with unique effects.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    suit = models.ForeignKey(CardSuit, on_delete=models.CASCADE)
    rank = models.ForeignKey(CardRank, on_delete=models.CASCADE)
    special_card = models.ForeignKey('SpecialCard', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        """Return string representation of the card.
        
        Returns:
            str: Card rank and suit (e.g., "Ace of Hearts").
        """
        base_name = f"{self.rank.name} of {self.suit.name}"
        if self.special_card:
            return f"{base_name} ({self.special_card.name})"
        return base_name

    def is_trump(self, trump_suit):
        """Check if this card belongs to the trump suit.
        
        Args:
            trump_suit (CardSuit): The current trump suit for the game.
            
        Returns:
            bool: True if card's suit matches trump suit, False otherwise.
        """
        return self.suit == trump_suit

    def is_special(self):
        """Check if this card has special effects.
        
        Returns:
            bool: True if special_card is set, False otherwise.
        """
        return self.special_card is not None

    def can_beat(self, other_card, trump_suit):
        """Check if this card can beat another card according to Durak rules.
        
        Args:
            other_card (Card): The card to compare against.
            trump_suit (CardSuit): The current trump suit.
            
        Returns:
            bool: True if this card can beat the other card, False otherwise.
        """
        # Trump cards beat non-trump cards
        if self.is_trump(trump_suit) and not other_card.is_trump(trump_suit):
            return True

        # Non-trump cannot beat trump
        if not self.is_trump(trump_suit) and other_card.is_trump(trump_suit):
            return False

        # Same suit comparison by rank value
        if self.suit == other_card.suit:
            return self.rank.value > other_card.rank.value

        # Different non-trump suits cannot beat each other
        return False

    class Meta:
        verbose_name = 'Card'
        verbose_name_plural = 'Cards'
        unique_together = ['suit', 'rank', 'special_card']

class SpecialCard(models.Model):
    """Special card effects model for custom game mechanics.

    Defines special abilities that can be applied to cards to create
    unique gameplay mechanics beyond standard Durak rules. Each special
    card type has a specific effect and description.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    effect_type = models.CharField(
        max_length=20,
        choices=[
            ('skip', 'Skip Turn'),
            ('reverse', 'Reverse Order'),
            ('draw', 'Draw Cards'),
            ('custom', 'Custom Effect')
        ]
    )
    effect_value = models.JSONField(default=dict, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        """Return string representation of the special card.

        Returns:
            str: The name of the special card effect.
        """
        return self.name

    def get_effect_description(self):
        """Get a formatted description of the effect with parameters.

        Returns:
            str: Description with effect values interpolated.
        """
        if self.effect_type == 'draw' and 'card_count' in self.effect_value:
            return f"{self.description} ({self.effect_value['card_count']} cards)"
        return self.description

    def is_targetable(self):
        """Check if this effect requires targeting a specific player.

        Returns:
            bool: True if effect targets other players, False if self-affecting.
        """
        return self.effect_type in ['draw', 'skip']

    def can_be_countered(self):
        """Check if this special effect can be countered by other cards.

        Returns:
            bool: True if effect can be countered, False otherwise.
        """
        return self.effect_value.get('counterable', True)

    class Meta:
        verbose_name = 'Special Card'
        verbose_name_plural = 'Special Cards'
        ordering = ['name']

class SpecialRuleSet(models.Model):
    """Special rule configuration for advanced game variants.

    Defines collections of special rules and cards that can be applied
    to lobbies to create custom game experiences. Each rule set can
    specify minimum player requirements and special card inclusions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField()
    min_players = models.IntegerField(default=2)

    def __str__(self):
        """Return string representation of the rule set.

        Returns:
            str: The name of the rule set.
        """
        return self.name

    def get_special_card_count(self):
        """Get the number of special cards in this rule set.

        Returns:
            int: Count of special cards associated with this rule set.
        """
        return self.specialrulesetcard_set.count()

    def is_compatible_with_player_count(self, player_count):
        """Check if this rule set can be used with the given number of players.

        Args:
            player_count (int): Number of players in the game.

        Returns:
            bool: True if player count meets minimum requirement.
        """
        return player_count >= self.min_players

    def get_enabled_special_cards(self):
        """Get all special cards that are enabled in this rule set.

        Returns:
            QuerySet: SpecialCard objects that are active in this rule set.
        """
        return SpecialCard.objects.filter(
            specialrulesetcard__rule_set=self,
            specialrulesetcard__is_enabled=True
        )

    def can_be_used_in_lobby(self, lobby_settings):
        """Check if this rule set is compatible with lobby settings.

        Args:
            lobby_settings (LobbySettings): The lobby settings to check against.

        Returns:
            bool: True if compatible with lobby configuration.
        """
        return (self.is_compatible_with_player_count(lobby_settings.max_players) and
                lobby_settings.allow_jokers)  # Special cards require jokers enabled

    class Meta:
        verbose_name = 'Special Rule Set'
        verbose_name_plural = 'Special Rule Sets'
        ordering = ['name']

class SpecialRuleSetCard(models.Model):
    """Association model linking special cards to rule sets with configuration.

    Defines which special cards are included in specific rule sets and
    how they should be configured within that context. Allows for
    fine-tuned control over special card availability and behavior.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule_set = models.ForeignKey(SpecialRuleSet, on_delete=models.CASCADE)
    card = models.ForeignKey(SpecialCard, on_delete=models.CASCADE)
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        """Return string representation of the rule set card association.

        Returns:
            str: Rule set and card names with status.
        """
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.card.name} in {self.rule_set.name} ({status})"

    def toggle_enabled(self):
        """Toggle the enabled status of this card in the rule set.

        Returns:
            bool: New enabled status after toggling.
        """
        self.is_enabled = not self.is_enabled
        self.save(update_fields=['is_enabled'])
        return self.is_enabled

    def can_be_used_in_game(self, game):
        """Check if this special card can be used in a specific game.

        Args:
            game (Game): The game session to check compatibility with.

        Returns:
            bool: True if the card is enabled and game allows special rules.
        """
        if not self.is_enabled:
            return False

        lobby_settings = game.lobby.settings
        return (lobby_settings.special_rule_set == self.rule_set and
                lobby_settings.allow_jokers)

    class Meta:
        verbose_name = 'Special Rule Set Card'
        verbose_name_plural = 'Special Rule Set Cards'
        unique_together = ['rule_set', 'card']
        ordering = ['rule_set__name', 'card__name']

class GameDeck(models.Model):
    """Model representing cards remaining in the deck during a game.
    
    Tracks the position and order of cards in the game deck. Cards are
    drawn from this deck when players need to replenish their hands.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    position = models.IntegerField()

    def __str__(self):
        """Return string representation of the deck card.
        
        Returns:
            str: Card info with position in deck.
        """
        return f"{self.card} at position {self.position} in {self.game}"

    @classmethod
    def get_top_card(cls, game):
        """Get the top card from the deck (lowest position number).
        
        Args:
            game (Game): The game to get the top card for.
            
        Returns:
            GameDeck: The deck entry with the lowest position, or None if deck is empty.
        """
        return cls.objects.filter(game=game).order_by('position').first()

    @classmethod
    def draw_card(cls, game):
        """Draw and remove the top card from the deck.
        
        Args:
            game (Game): The game to draw a card from.
            
        Returns:
            Card: The drawn card, or None if deck is empty.
        """
        deck_card = cls.get_top_card(game)
        if deck_card:
            card = deck_card.card
            deck_card.delete()
            return card
        return None

    def is_last_card(self):
        """Check if this is the last card in the deck.
        
        Returns:
            bool: True if no other cards have higher positions, False otherwise.
        """
        return not GameDeck.objects.filter(
            game=self.game,
            position__gt=self.position
        ).exists()

    class Meta:
        verbose_name = 'Game Deck Card'
        verbose_name_plural = 'Game Deck Cards'
        unique_together = ['game', 'position']
        ordering = ['position']

class PlayerHand(models.Model):
    """Model representing cards in a player's hand during a game.
    
    Tracks which cards each player holds, with optional ordering
    information for UI display purposes.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    player = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    order_in_hand = models.IntegerField(null=True, blank=True)

    def __str__(self):
        """Return string representation of the hand card.
        
        Returns:
            str: Player and card information.
        """
        return f"{self.player.username} holds {self.card} in {self.game}"

    @classmethod
    def get_player_hand(cls, game, player):
        """Get all cards in a specific player's hand for a game.
        
        Args:
            game (Game): The game session.
            player (User): The player whose hand to retrieve.
            
        Returns:
            QuerySet: PlayerHand objects ordered by order_in_hand.
        """
        return cls.objects.filter(
            game=game,
            player=player
        ).order_by('order_in_hand')

    @classmethod
    def get_hand_size(cls, game, player):
        """Get the number of cards in a player's hand.
        
        Args:
            game (Game): The game session.
            player (User): The player whose hand size to count.
            
        Returns:
            int: Number of cards in the player's hand.
        """
        return cls.objects.filter(game=game, player=player).count()

    def remove_from_hand(self):
        """Remove this card from the player's hand.
        
        Deletes the PlayerHand record and updates the GamePlayer's
        cards_remaining counter.
        """
        game_player = GamePlayer.objects.get(game=self.game, user=self.player)
        game_player.cards_remaining = max(0, game_player.cards_remaining - 1)
        game_player.save(update_fields=['cards_remaining'])
        self.delete()

    class Meta:
        verbose_name = 'Player Hand Card'
        verbose_name_plural = 'Player Hand Cards'
        unique_together = ['game', 'player', 'card']
        ordering = ['order_in_hand']

class TableCard(models.Model):
    """Model representing attack and defense card pairs on the table.
    
    During a Durak game round, attacking cards are placed on the table
    and can be defended by appropriate defending cards. This model
    tracks these attack-defense pairs.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    attack_card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='attack_card')
    defense_card = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='defense_card')

    def __str__(self):
        """Return string representation of the table card.
        
        Returns:
            str: Attack and defense card information.
        """
        if self.defense_card:
            return f"{self.attack_card} defended by {self.defense_card}"
        return f"{self.attack_card} (undefended)"

    def is_defended(self):
        """Check if the attack card has been defended.
        
        Returns:
            bool: True if defense_card is set, False otherwise.
        """
        return self.defense_card is not None

    def is_valid_defense(self, defense_card, trump_suit):
        """Check if a card can validly defend this attack.
        
        Args:
            defense_card (Card): The card being used for defense.
            trump_suit (CardSuit): The current trump suit.
            
        Returns:
            bool: True if the defense is valid according to Durak rules.
        """
        if self.is_defended():
            return False  # Already defended

        return defense_card.can_beat(self.attack_card, trump_suit)

    def defend_with(self, defense_card, trump_suit):
        """Attempt to defend this attack with a card.
        
        Args:
            defense_card (Card): The card being used for defense.
            trump_suit (CardSuit): The current trump suit.
            
        Returns:
            bool: True if defense was successful, False otherwise.
        """
        if self.is_valid_defense(defense_card, trump_suit):
            self.defense_card = defense_card
            self.save(update_fields=['defense_card'])
            return True
        return False

    class Meta:
        verbose_name = 'Table Card'
        verbose_name_plural = 'Table Cards'
        ordering = ['id']

class DiscardPile(models.Model):
    """Model representing cards that have been discarded from the game.
    
    After successful defense rounds or when cards are played out,
    they are moved to the discard pile and removed from active play.
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    position = models.IntegerField(null=True, blank=True)

    def __str__(self):
        """Return string representation of the discarded card.
        
        Returns:
            str: Card and position information.
        """
        pos_info = f" (position {self.position})" if self.position else ""
        return f"Discarded {self.card}{pos_info}"

    @classmethod
    def discard_cards(cls, game, cards):
        """Discard multiple cards at once.
        
        Args:
            game (Game): The game session.
            cards (list): List of Card objects to discard.
            
        Returns:
            list: List of created DiscardPile objects.
        """
        last_position = cls.objects.filter(game=game).count()
        discard_entries = []
        for i, card in enumerate(cards):
            discard_entries.append(
                cls.objects.create(
                    game=game,
                    card=card,
                    position=last_position + i + 1,
                )
            )
        return discard_entries

class Turn(models.Model):
    """Turn tracking model for managing player turn sequence in games.
    
    Represents individual turns within a game session, tracking which player's
    turn it is and maintaining the sequential order of gameplay. Each turn
    can contain multiple moves (attack, defend, pickup).
    
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='turns')
    player = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    turn_number = models.IntegerField()

    def __str__(self):
        """Return string representation of the turn.
        
        Returns:
            str: Turn number and player information.
        """
        return f"Turn {self.turn_number}: {self.player.username} in {self.game}"

    def get_moves(self):
        """Get all moves made during this turn.
        
        Returns:
            QuerySet: Move objects associated with this turn.
        """
        return self.moves.all().order_by('created_at')

    def is_complete(self):
        """Check if this turn has been completed (has moves).
        
        Returns:
            bool: True if turn has associated moves, False otherwise.
        """
        return self.moves.exists()

    @classmethod
    def get_current_turn(cls, game):
        """Get the most recent turn for a game.
        
        Args:
            game (Game): The game to get the current turn for.
            
        Returns:
            Turn: The turn with the highest turn_number, or None if no turns exist.
        """
        return cls.objects.filter(game=game).order_by('-turn_number').first()

    @classmethod
    def create_next_turn(cls, game, player):
        """Create the next turn in sequence for a game.
        
        Args:
            game (Game): The game to create a turn for.
            player (User): The player whose turn it will be.
            
        Returns:
            Turn: The newly created turn object.
        """
        next_number = cls.objects.filter(game=game).count() + 1
        return cls.objects.create(
            game=game,
            player=player,
            turn_number=next_number
        )

    class Meta:
        verbose_name = 'Turn'
        verbose_name_plural = 'Turns'
        unique_together = ['game', 'turn_number']
        ordering = ['turn_number']

class Move(models.Model):
    """Game move model representing individual player actions during gameplay.
    
    Tracks specific actions taken by players during their turns, such as
    attacking with cards, defending attacks, or picking up cards. Each move
    is associated with a turn and references the relevant table cards.
    
    """

    ACTION_CHOICES = [
        ('attack', 'Attack'),
        ('defend', 'Defend'),
        ('pickup', 'Pickup'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    turn = models.ForeignKey(Turn, on_delete=models.CASCADE, related_name='moves')
    table_card = models.ForeignKey(TableCard, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return string representation of the move.
        
        Returns:
            str: Action type and card information.
        """
        return f"{self.action_type.title()} by {self.turn.player.username}: {self.table_card}"

    def get_player(self):
        """Get the player who made this move.
        
        Returns:
            User: The user associated with the turn that contains this move.
        """
        return self.turn.player

    def is_attack(self):
        """Check if this move is an attack action.
        
        Returns:
            bool: True if action_type is 'attack', False otherwise.
        """
        return self.action_type == 'attack'

    def is_defense(self):
        """Check if this move is a defense action.
        
        Returns:
            bool: True if action_type is 'defend', False otherwise.
        """
        return self.action_type == 'defend'

    def is_pickup(self):
        """Check if this move is a pickup action.
        
        Returns:
            bool: True if action_type is 'pickup', False otherwise.
        """
        return self.action_type == 'pickup'

    @classmethod
    def get_game_moves(cls, game):
        """Get all moves for a specific game ordered by time.
        
        Args:
            game (Game): The game to get moves for.
            
        Returns:
            QuerySet: Move objects for the game ordered by creation time.
        """
        return cls.objects.filter(turn__game=game).order_by('created_at')

    @classmethod
    def get_player_moves(cls, game, player):
        """Get all moves made by a specific player in a game.
        
        Args:
            game (Game): The game to search in.
            player (User): The player whose moves to retrieve.
            
        Returns:
            QuerySet: Move objects made by the player in the game.
        """
        return cls.objects.filter(turn__game=game, turn__player=player).order_by('created_at')

    class Meta:
        verbose_name = 'Move'
        verbose_name_plural = 'Moves'
        ordering = ['created_at']
