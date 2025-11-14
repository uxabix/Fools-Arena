"""Account models for the Durak online multiplayer card game.

This module defines the User and Block models used for authentication,
player identity management, and handling of user-to-user blocking within
the Durak multiplayer application.
"""

import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user model for the Durak card game application.

    This model extends Django's ``AbstractUser`` to support additional
    game-specific fields and convenience methods. A UUID is used as a
    primary key to improve security, avoid predictable identifiers, and
    support distributed systems.

    Attributes:
        id (UUIDField): Primary key using UUID4.
        avatar_url (URLField): Optional URL to the user's avatar image.
        created_at (DateTimeField): Timestamp of when the user account was created.

    Inherited Attributes from ``AbstractUser``:
        username, email, password, first_name, last_name,
        is_active, is_staff, is_superuser,
        date_joined, last_login

    Reverse Relations:
        sent_messages (QuerySet[Message]): Messages sent by the user.
        received_messages (QuerySet[Message]): Private messages received by the user.
        lobby_set (QuerySet[Lobby]): Lobbies created by the user.
        lobbyplayer_set (QuerySet[LobbyPlayer]): Lobby participation records.
        gameplayer_set (QuerySet[GamePlayer]): Game participation records.
        playerhand_set (QuerySet[PlayerHand]): Cards owned by the user in a match.
        turn_set (QuerySet[Turn]): Turns made by the user.

    Example:
        user = User.objects.create_user(
            username="player1",
            email="player1@example.com",
            password="secure_password"
        )
        user.avatar_url = "https://example.com/avatar.jpg"
        user.save()
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avatar_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return the string representation of the user.

        Returns:
            str: The username of the user.
        """
        return self.username

    def get_full_display_name(self):
        """Return the user's display name with fallback to username.

        Returns:
            str: The user's full name if available, otherwise username.
        """
        full_name = self.get_full_name()
        return full_name if full_name else self.username

    def has_avatar(self):
        """Check whether the user has an avatar set.

        Returns:
            bool: True if ``avatar_url`` is defined, otherwise False.
        """
        return bool(self.avatar_url)

    def get_active_lobby(self):
        """Return the lobby in which the user is currently active.

        A user is considered active if their lobby status is one of:
        ``waiting``, ``ready``, or ``playing``.

        Returns:
            Lobby | None: The active lobby instance, or None if the user
            is not currently in any lobby.
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
        """Return the game the user is currently playing.

        Returns:
            Game | None: The active game instance, or None if the user
            is not participating in an in-progress match.
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
        """Determine whether the user is allowed to join the specified lobby.

        Args:
            lobby (Lobby): The lobby to evaluate.

        Returns:
            bool: True if the user is allowed to join the lobby, otherwise False.
        """
        if self.get_active_lobby():
            return False

        if lobby.is_full():
            return False

        if lobby.status == 'closed':
            return False

        return True

    def leave_current_lobby(self):
        """Remove the user from their active lobby if they are currently in one.

        Returns:
            bool: True if the user left a lobby, False if they were not part of any lobby.
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
        """Return basic gameplay statistics for the user.

        The statistics include:
        - total number of finished games
        - number of wins
        - number of losses
        - win rate percentage

        Returns:
            dict: A dictionary containing:
                total_games (int)
                games_won (int)
                games_lost (int)
                win_rate (float)
        """
        from game.models import Game, GamePlayer

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

        games_lost = finished_games.filter(loser=self).count()
        games_won = total_games - games_lost
        win_rate = (games_won / total_games) * 100

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


class Block(models.Model):
    """Represents a unilateral user block between two users.

    A block prevents the ``blocked`` user from interacting with the
    ``blocker`` (e.g., sending messages, joining their lobby, sending invites).

    Attributes:
        blocker (ForeignKey[User]): The user who initiated the block.
        blocked (ForeignKey[User]): The user who is being blocked.
        created_at (DateTimeField): Timestamp of when the block was created.

    Constraints:
        - A user cannot block the same user more than once (unique_together).
        - Indexed lookups for efficient permission checks.

    Example:
        Block.objects.create(blocker=user1, blocked=user2)
    """

    blocker = models.ForeignKey(
        User,
        related_name="blocks_initiated",
        on_delete=models.CASCADE
    )
    blocked = models.ForeignKey(
        User,
        related_name="blocks_received",
        on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("blocker", "blocked")
        indexes = [
            models.Index(fields=["blocker", "blocked"]),
        ]

    def __str__(self):
        """Return a human-readable representation of the block relation.

        Returns:
            str: A formatted string describing the block.
        """
        return f"{self.blocker} blocked {self.blocked}"
