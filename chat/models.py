"""Chat models for the Durak card game application.

This module defines the core models for managing chat rooms and their participants
in the Durak online multiplayer system. It includes models for representing chats,
chat membership, and stored messages.

Classes:
    Chat: Represents a chat room (group, lobby or private).
    ChatParticipant: Defines user participation in a chat with assigned roles.
    Message: Represents a message sent inside a chat.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, models, transaction
from django.utils import timezone

User = get_user_model()


class ChatManager(models.Manager):
    """Custom manager with helpers for direct (1-on-1) chats."""

    def get_or_create_direct(self, user_a, user_b):
        """Return an existing or new direct message chat between two users.

        ``dm_pair_key`` enforces at most one Chat row per unordered user pair.

        Args:
            user_a (User): First participant.
            user_b (User): Second participant.

        Returns:
            tuple[Chat, bool]: The chat instance and True if it was created.

        Raises:
            ValueError: If both arguments refer to the same user.
        """
        if user_a.pk == user_b.pk:
            raise ValueError("Cannot create a direct chat with the same user.")

        key = dm_pair_key(user_a, user_b)
        existing = self.filter(dm_pair_key=key).first()
        if existing:
            return existing, False

        try:
            with transaction.atomic():
                chat = self.create(
                    name="",
                    is_group=False,
                    is_lobby=False,
                    is_global=False,
                    dm_pair_key=key,
                )
                chat.add_participant(user_a)
                chat.add_participant(user_b)
                return chat, True
        except IntegrityError:
            recovered = self.filter(dm_pair_key=key).first()
            if recovered:
                return recovered, False
            raise


def dm_pair_key(user_a, user_b):
    """Build a stable unique key for an unordered pair of users.

    Args:
        user_a (User): First user.
        user_b (User): Second user.

    Returns:
        str: Two UUIDs in lexicographic order, separated by ``':'``.
    """
    a, b = sorted([str(user_a.pk), str(user_b.pk)])
    return f"{a}:{b}"


class Chat(models.Model):
    """Represents a chat room (private, group, or lobby).

    Chats are used to isolate different communication contexts in the game:
    - private chats (DM between two users)
    - group chats
    - automatically created lobby chats (is_lobby=True)

    Messages are always attached to a Chat, not directly to a Lobby or users.
    """

    objects = ChatManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    is_group = models.BooleanField(default=False)
    is_lobby = models.BooleanField(default=False)
    is_global = models.BooleanField(default=False)

    lobby = models.ForeignKey(
        "game.Lobby",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chat"
    )

    dm_pair_key = models.CharField(
        max_length=73,
        null=True,
        blank=True,
        unique=True,
        help_text="Stable identifier for a 1-on-1 chat (two UUIDs, sorted).",
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Chat'
        verbose_name_plural = 'Chats'
        indexes = [
            models.Index(fields=["is_group", "created_at"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_global", "created_at"]),
        ]

    def __str__(self):
        """Return the chat name if available, otherwise fallback to ID."""
        return self.name or f"Chat {self.id}"

    def get_participants(self):
        """Return all users currently participating in this chat.

        Returns:
            QuerySet[User]: Distinct list of users.
        """
        return User.objects.filter(chat_participations__chat=self).distinct()

    def has_participant(self, user):
        """Determine whether a given user is part of this chat.

        Args:
            user (User): The user to check.

        Returns:
            bool: True if the user participates in the chat.
        """
        return ChatParticipant.objects.filter(chat=self, user=user).exists()

    def add_participant(self, user, role="member"):
        """Add a user to the chat or update their role.

        Args:
            user (User): User to add.
            role (str): One of: "owner", "admin", "member".

        Returns:
            tuple(ChatParticipant, bool): participant instance and created flag
        """
        with transaction.atomic():
            participant, created = ChatParticipant.objects.get_or_create(
                chat=self,
                user=user,
                defaults={"role": role}
            )
            if not created and participant.role != role:
                participant.role = role
                participant.save(update_fields=["role"])

        return participant, created

    def remove_participant(self, user):
        """Remove a participant from the chat.

        Args:
            user (User): User to remove.

        Returns:
            int: Number of deleted records (0 or 1).
        """
        return ChatParticipant.objects.filter(chat=self, user=user).delete()[0]

    def get_owners(self):
        """Return all owners of this chat."""
        return ChatParticipant.objects.filter(chat=self, role="owner").select_related("user")

    def get_admins(self):
        """Return all admins (role admin or owner)."""
        return ChatParticipant.objects.filter(
            chat=self, role__in=["admin", "owner"]
        ).select_related("user")

    def is_direct_message(self):
        """Return True if this chat is a private 1-on-1 (not lobby/group/global)."""
        return (
            not self.is_group
            and not self.is_lobby
            and not self.is_global
        )

    def get_other_participant(self, user):
        """Return the other user in a direct chat.

        Args:
            user (User): One of the two participants.

        Returns:
            User | None: The counterpart, or None if not applicable.
        """
        if not self.is_direct_message():
            return None
        return self.get_participants().exclude(pk=user.pk).first()


class ChatParticipant(models.Model):
    """Represents a user's membership in a chat with assigned permissions.

    Each user can belong to multiple chats and have different roles in each.
    """

    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    user = models.ForeignKey('accounts.User', related_name='chat_participations', on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chat Participant"
        verbose_name_plural = "Chat Participants"
        unique_together = ("chat", "user")
        indexes = [
            models.Index(fields=["chat", "user"]),
            models.Index(fields=["role"]),
            models.Index(fields=["joined_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.chat}"

    def is_owner(self):
        """Return True if participant is the owner."""
        return self.role == "owner"

    def is_admin(self):
        """Return True if participant has admin or owner rights."""
        return self.role in ("admin", "owner")

    def promote(self):
        """Promote user to admin."""
        if self.role == "member":
            self.role = "admin"
            self.save(update_fields=["role"])

    def demote(self):
        """Demote admin to member."""
        if self.role == "admin":
            self.role = "member"
            self.save(update_fields=["role"])

class Message(models.Model):
    """Represents a text message inside a chat.

    Messages belong strictly to a ``Chat`` instance. Lobby and direct messages
    differ by chat type only; there are no separate lobby or receiver fields
    on this model.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='sent_messages')
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return a concise textual preview."""
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.sender.username}: {preview}"

    def is_lobby_message(self):
        """Determine if this message belongs to a lobby chat."""
        return self.chat.is_lobby

    def is_private(self):
        """Determine if this is a private 1-on-1 message."""
        return self.chat.is_direct_message()

    def get_chat_context(self):
        """Return structured information about the chat type.

        Returns:
            dict: ``type`` is one of ``private``, ``group``, ``lobby``, ``global``;
            ``name`` is a short display label.
        """
        if self.chat.is_lobby:
            return {"type": "lobby", "name": self.chat.name or "Lobby"}

        if self.chat.is_global:
            return {"type": "global", "name": self.chat.name or "Global"}

        if self.chat.is_group:
            return {"type": "group", "name": self.chat.name or "Group Chat"}

        return {"type": "private", "name": "Private Chat"}

    class Meta:
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['sender', 'chat', '-sent_at']),
            models.Index(fields=['-sent_at']),
        ]
