"""Chat models for the Durak card game application.

This module defines the core models for managing chat rooms and their participants
in the Durak online multiplayer system. It includes models for representing chats,
user roles, and membership management.

Classes:
    Chat: Represents a chat room (group or private) used for communication.
    ChatParticipant: Defines user participation in a chat, including their role
        and join date.
    Message: Represents a single message sent between users in a chat.
"""

import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


class Chat(models.Model):
    """Represents a chat room, either group or private.

        Each chat can contain multiple participants and messages. This model is used
        to logically separate different communication contexts (e.g., private DM or
        group lobby discussion).

        Attributes:
            id (UUIDField): Primary key (UUID4) for unique chat identification.
            name (CharField): Optional name of the chat room (e.g., "Lobby 1").
            description (TextField): Optional text describing the chat purpose.
            is_group (BooleanField): Defines if chat is a group or private conversation.
            created_at (DateTimeField): Timestamp for chat creation.

        Example:
            chat = Chat.objects.create(
                name="General Lobby",
                description="Main lobby for all players",
                is_group=True
            )
        """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    is_group = models.BooleanField(default=False)
    is_lobby = models.BooleanField(default=False)
    lobby = models.ForeignKey(
        "game.Lobby",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chat"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Chat'
        verbose_name_plural = 'Chats'
        indexes = [
            models.Index(fields=["is_group", "created_at"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        """Return a readable representation of the chat.

        Returns:
            str: Chat name or fallback to ID.
        """
        return self.name or f"Chat {self.id}"

    def get_participants(self):
        """Return a QuerySet of users participating in this chat.

        Returns:
            QuerySet[User]: Users who are members of this chat.
        """
        return User.objects.filter(chat_participations__chat=self).select_related().distinct()

    def has_participant(self, user):
        """Check if a user is a member of the chat.

        Args:
            user (User): The user to check.

        Returns:
            bool: True if user participates in this chat.
        """
        return ChatParticipant.objects.filter(chat=self, user=user).exists()

    def add_participant(self, user, role="member"):
        """Add a user to the chat with an optional role.

        If the user already exists in the chat, do not create a duplicate; optionally
        update their role if it differs.

        Args:
            user (User): The user to add.
            role (str): Role in the chat ("owner", "admin", or "member").
        Returns:
            ChatParticipant: The participant instance and a boolean created flag.
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
        """Remove a user from the chat.

        Args:
            user (User): The user to remove.

        Returns:
            int: Number of deleted rows (0 or 1).
        """
        return ChatParticipant.objects.filter(chat=self, user=user).delete()[0]

    def get_owners(self):
        """Return a QuerySet of ChatParticipant objects with role 'owner'.

        Returns:
            QuerySet[ChatParticipant]: Participant records for owners (selects related user).
        """
        return ChatParticipant.objects.filter(chat=self, role="owner").select_related("user")

    def get_admins(self):
        """Return a QuerySet of ChatParticipant objects with role 'admin'.

        Returns:
            QuerySet[ChatParticipant]: Participant records for admins (selects related user).
        """
        return ChatParticipant.objects.filter(chat=self, role="admin").select_related("user")


class ChatParticipant(models.Model):
    """Defines a user's participation and role within a chat.

        Each record represents one user's membership in one chat. Roles determine
        their permissions (e.g., ownership, admin privileges, or regular member).

        Attributes:
            id (UUIDField): Primary key (UUID4) for unique participant record.
            chat (ForeignKey): The chat this user belongs to.
            user (ForeignKey): The user participating in the chat.
            role (CharField): User's role in the chat ("owner", "admin", "member").
            joined_at (DateTimeField): Timestamp of when the user joined the chat.

        Example:
            participant = ChatParticipant.objects.create(
                chat=chat,
                user=user,
                role="admin"
            )
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
        """Return readable representation of the participant.

        Returns:
            str: User’s username and chat name.
        """
        return f"User {self.user.username} in {self.chat} chat"

    def is_owner(self):
        """Check if the participant is the chat owner.

        Returns:
            bool: True if participant has 'owner' role.
        """
        return self.role == "owner"

    def is_admin(self):
        """Check if the participant has admin privileges.

        Returns:
            bool: True if role is 'admin' or 'owner'.
        """
        return self.role in ("admin", "owner")

    def promote(self):
        """Promote participant to admin if not already."""
        if self.role == "member":
            self.role = "admin"
            self.save(update_fields=["role"])

    def demote(self):
        """Demote participant to member if currently admin."""
        if self.role == "admin":
            self.role = "member"
            self.save(update_fields=["role"])


class Message(models.Model):
    """Chat message model for storing messages in lobbies and private conversations.
    
    This model handles both lobby-based group messages and private direct messages
    between users. Messages can be associated with either a lobby (for public chat)
    or a receiver (for private messaging).
    
    Attributes:
        id (UUIDField): Primary key using UUID4 for unique message identification.
        sender (ForeignKey): Reference to the User who sent the message.
        receiver (ForeignKey, optional): Target User for private messages. Null for lobby messages.
        lobby (ForeignKey, optional): Target Lobby for group messages. Null for private messages.
        content (TextField): The actual message content/text.
        sent_at (DateTimeField): Timestamp when the message was created (auto-generated).
        
    Note:
        Either 'receiver' or 'lobby' should be set, but not both. This creates a logical
        separation between private messages and lobby-based group chat.
        
    Example:
        # Create a lobby message
        Message.objects.create(
            sender=user,
            lobby=lobby,
            content="Hello everyone!"
        )
        
        # Create a private message
        Message.objects.create(
            sender=user1,
            receiver=user2,
            content="Private message"
        )
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='sent_messages')
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return string representation of the message.
        
        Returns:
            str: Formatted string showing sender and message preview.
        """
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.sender.username}: {preview}"

    def is_private(self):
        """Check if this is a private message between users.
        
        Returns:
            bool: True if message has a receiver (private), False if lobby message.
        """
        return self.receiver is not None

    def is_lobby_message(self):
        """Check if this is a lobby/group message.
        
        Returns:
            bool: True if message belongs to a lobby, False if private message.
        """
        return self.lobby is not None

    def get_chat_context(self):
        """Get the context (lobby or private chat) for this message.
        
        Returns:
            dict: Dictionary with context type and relevant object.
        """
        if self.lobby:
            return {
                'type': 'lobby',
                'context': self.lobby,
                'context_name': self.lobby.name
            }
        elif self.receiver:
            return {
                'type': 'private',
                'context': self.receiver,
                'context_name': f"Private chat with {self.receiver.username}"
            }
        return {'type': 'unknown', 'context': None, 'context_name': 'Unknown'}

    @classmethod
    def get_lobby_messages(cls, lobby, limit=50):
        """Get recent messages for a specific lobby.
        
        Args:
            lobby (Lobby): The lobby to get messages for.
            limit (int): Maximum number of messages to retrieve.
            
        Returns:
            QuerySet: Recent messages in the lobby.
        """
        return cls.objects.filter(lobby=lobby).order_by('-sent_at')[:limit]

    @classmethod
    def get_private_conversation(cls, user1, user2, limit=50):
        """Get recent private messages between two users.
        
        Args:
            user1 (User): First user in the conversation.
            user2 (User): Second user in the conversation.
            limit (int): Maximum number of messages to retrieve.
            
        Returns:
            QuerySet: Recent messages between the users.
        """
        return cls.objects.filter(
            models.Q(sender=user1, receiver=user2) |
            models.Q(sender=user2, receiver=user1),
            lobby__isnull=True
        ).order_by('-sent_at')[:limit]

    def clean(self):
        """Validate that message has either lobby or receiver, but not both.
        
        Raises:
            ValidationError: If both lobby and receiver are set, or if neither is set.
        """
        from django.core.exceptions import ValidationError

        if self.lobby and self.receiver:
            raise ValidationError("Message cannot have both lobby and receiver.")
        if not self.lobby and not self.receiver:
            raise ValidationError("Message must have either lobby or receiver.")

    def save(self, *args, **kwargs):
        """Override save to ensure message validation.
        
        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['sender', 'chat', '-sent_at']),
            models.Index(fields=['-sent_at']),
        ]
