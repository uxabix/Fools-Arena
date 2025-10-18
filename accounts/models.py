"""Accounts models for the Durak card game application.

This module contains all the Django models used in the account system for
the online multiplayer Durak card game.
"""

import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended User model for the Durak card game application.
    
    This model extends Django's AbstractUser to include additional fields
    specific to the game functionality such as avatar and creation timestamp.
    Uses UUID as primary key for better security and scalability.
    
    Attributes:
        id (UUIDField): Primary key using UUID4 instead of sequential integers.
        avatar_url (URLField, optional): URL to user's avatar image.
        created_at (DateTimeField): Timestamp when the account was created.
        
    Inherits from AbstractUser:
        username, email, password, first_name, last_name, is_active, 
        is_staff, is_superuser, date_joined, last_login
        
    Related Objects:
        sent_messages: Messages sent by this user (reverse FK from Message.sender)
        received_messages: Private messages received by this user (reverse FK from Message.receiver)
        lobby_set: Game lobbies owned by this user (reverse FK from Lobby.owner)
        lobbyplayer_set: Lobby memberships (reverse FK from LobbyPlayer.user)
        gameplayer_set: Game participations (reverse FK from GamePlayer.user)
        playerhand_set: Cards in player's hands (reverse FK from PlayerHand.player)
        turn_set: Turns taken by this player (reverse FK from Turn.player)
        
    Example:
        # Create a new user
        user = User.objects.create_user(
            username='player1',
            email='player1@example.com',
            password='secure_password'
        )
        user.avatar_url = 'https://example.com/avatar.jpg'
        user.save()
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avatar_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return string representation of the user.
        
        Returns:
            str: The username of the user.
        """
        return self.username
    
    def get_full_display_name(self):
        """Get user's display name with fallback to username.
        
        Returns:
            str: Full name if available, otherwise username.
        """
        full_name = self.get_full_name()
        return full_name if full_name else self.username
    
    def has_avatar(self):
        """Check if user has an avatar set.
        
        Returns:
            bool: True if avatar_url is set, False otherwise.
        """
        return bool(self.avatar_url)
    
    def get_active_lobby(self):
        """Get the lobby this user is currently participating in.
        
        Returns:
            Lobby: The lobby where user has active status, or None.
        """
        from game.models import LobbyPlayer
        try:
            lobby_player = LobbyPlayer.objects.get(
                user=self,
                status__in=['waiting', 'ready', 'playing']
            )
            return lobby_player.lobby
        except LobbyPlayer.DoesNotExist:
            return None
    
    def get_current_game(self):
        """Get the game this user is currently playing.
        
        Returns:
            Game: The active game the user is participating in, or None.
        """
        from game.models import GamePlayer
        try:
            game_player = GamePlayer.objects.select_related('game').get(
                user=self,
                game__status='in_progress'
            )
            return game_player.game
        except GamePlayer.DoesNotExist:
            return None
    
    def can_join_lobby(self, lobby):
        """Check if this user can join a specific lobby.
        
        Args:
            lobby (Lobby): The lobby to check joining permissions for.
            
        Returns:
            bool: True if user can join, False otherwise.
        """
        # User cannot join if already in a lobby
        if self.get_active_lobby():
            return False
        
        # Cannot join if lobby is full
        if lobby.is_full():
            return False
        
        # Cannot join closed lobbies
        if lobby.status == 'closed':
            return False
        
        return True
    
    def leave_current_lobby(self):
        """Remove this user from their current lobby if they're in one.
        
        Returns:
            bool: True if user was in a lobby and left, False if not in a lobby.
        """
        from game.models import LobbyPlayer
        try:
            lobby_player = LobbyPlayer.objects.get(
                user=self,
                status__in=['waiting', 'ready', 'playing']
            )
            lobby_player.leave_lobby()
            return True
        except LobbyPlayer.DoesNotExist:
            return False
    
    def get_game_statistics(self):
        """Get basic game statistics for this user.
        
        Returns:
            dict: Dictionary containing games played, won, and win rate.
        """
        from game.models import Game, GamePlayer
        
        # Get all finished games this user participated in
        finished_games = Game.objects.filter(
            players__user=self,
            status='finished'
        )
        
        total_games = finished_games.count()
        if total_games == 0:
            return {
                'total_games': 0,
                'games_won': 0,
                'games_lost': 0,
                'win_rate': 0.0
            }
        
        # Count losses (games where this user is the loser)
        games_lost = finished_games.filter(loser=self).count()
        games_won = total_games - games_lost
        win_rate = (games_won / total_games) * 100 if total_games > 0 else 0.0
        
        return {
            'total_games': total_games,
            'games_won': games_won,
            'games_lost': games_lost,
            'win_rate': round(win_rate, 1)
        }
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['username']
