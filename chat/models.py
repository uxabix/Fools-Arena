"""Chat models for the Durak card game application.

This module contains all the Django models used in the chat system for
the online multiplayer Durak card game.
"""

import uuid
from django.db import models


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
    receiver = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True,
                                 related_name='received_messages')
    lobby = models.ForeignKey('game.Lobby', on_delete=models.CASCADE, null=True, blank=True, 
                              related_name='messages')
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
            models.Index(fields=['lobby', '-sent_at']),
            models.Index(fields=['sender', 'receiver', '-sent_at']),
            models.Index(fields=['-sent_at']),
        ]
