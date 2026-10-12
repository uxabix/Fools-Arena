"""Account models for the Durak online multiplayer card game (Fools Arena).

This module defines the User and Block models used for authentication,
player identity management, and handling of user-to-user blocking within
the Durak multiplayer application.
"""

import uuid
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from .validators import (
    USERNAME_MAX_LENGTH,
    is_reserved_username,
    validate_username_format,
)


class User(AbstractUser):
    """Extended user model for the Fools Arena accounts app.

    Extends Django ``AbstractUser`` with fools-specific fields and helpers.
    Uses a UUID primary key. Inherits standard auth fields from ``AbstractUser``
    (username, email, password, ``is_active``, ``is_staff``, etc.).
    Reverse relations include lobby membership, fools participation, messages,
    hands, and turns.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(
        "username",
        max_length=USERNAME_MAX_LENGTH,
        unique=True,
        help_text="3–30 characters. Letters, numbers, and underscore only.",
        validators=[validate_username_format],
        error_messages={
            "unique": "A user with that username already exists.",
            "max_length": "Use %d characters or fewer." % USERNAME_MAX_LENGTH,
        },
    )
    email = models.EmailField("email address", unique=True, null=True, blank=True)
    avatar_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return the string representation of the user.

        Returns:
            str: The username of the user.
        """
        return self.username

    def save(self, *args, **kwargs):
        """Store a trimmed, lowercased email, or NULL when it is empty.

        Empty strings cannot share a unique column. NULL can, so accounts
        created before email was required do not collide.
        """
        if self.email is not None:
            normalized = self.email.strip().lower()
            self.email = normalized or None
        if self._state.adding and is_reserved_username(self.username or ""):
            raise ValidationError({"username": "This username is reserved."})
        super().save(*args, **kwargs)

    def clean(self):
        """Reject a new account that takes a reserved username.

        An account that already has a reserved name, such as an existing
        ``admin`` user, can still be saved.
        """
        super().clean()
        username = self.username or ""
        if not is_reserved_username(username):
            return
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values_list(
                "username", flat=True
            ).first()
            if previous and previous.casefold() == username.casefold():
                return
        raise ValidationError({"username": "This username is reserved."})

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
        from fools.models import LobbyPlayer
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
            Game | None: The active fools instance, or None if the user
            is not participating in an in-progress match.
        """
        from fools.models import GamePlayer
        try:
            game_player = GamePlayer.objects.select_related('fools').get(
                user=self,
                fools__status='in_progress'
            )
            return game_player.fools
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
        from fools.models import LobbyPlayer
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
        from fools.models import Game, GamePlayer

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
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="accounts_user_username_ci",
            ),
        ]


class Block(models.Model):
    """Represents a unilateral user block between two users.

    A block prevents the ``blocked`` user from interacting with the
    ``blocker`` (e.g., sending messages, joining their lobby, sending invites).
    The pair ``(blocker, blocked)`` is unique and indexed for lookups.
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
