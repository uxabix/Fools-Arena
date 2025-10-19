from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from chat.models import Message
from game.models import Lobby

User = get_user_model()


class MessageModelTest(TestCase):
    """Test suite for Message model."""

    def setUp(self):
        """Set up test data for Message tests."""
        self.user1 = User.objects.create_user(
            username="sender",
            password="test123"
        )

        self.user2 = User.objects.create_user(
            username="receiver",
            password="test123"
        )

        self.lobby = Lobby.objects.create(
            owner=self.user1,
            name="Test Lobby",
            status='waiting'
        )

    def test_private_message_creation(self):
        """Test that private Message instances are created correctly."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Hello, this is a private message!"
        )

        self.assertEqual(message.sender, self.user1)
        self.assertEqual(message.receiver, self.user2)
        self.assertIsNone(message.lobby)
        self.assertEqual(message.content, "Hello, this is a private message!")

    def test_lobby_message_creation(self):
        """Test that lobby Message instances are created correctly."""
        message = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="Hello everyone in the lobby!"
        )

        self.assertEqual(message.sender, self.user1)
        self.assertEqual(message.lobby, self.lobby)
        self.assertIsNone(message.receiver)
        self.assertEqual(message.content, "Hello everyone in the lobby!")

    def test_message_uuid_generation(self):
        """Test that UUID is automatically generated for messages."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Test"
        )

        self.assertIsNotNone(message.id)
        # UUID should be a valid UUID4
        self.assertEqual(len(str(message.id)), 36)

    def test_message_sent_at_auto_generation(self):
        """Test that sent_at timestamp is automatically set."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Test"
        )

        self.assertIsNotNone(message.sent_at)

    def test_message_str_representation_short(self):
        """Test string representation of Message with short content."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Short message"
        )

        self.assertEqual(str(message), "sender: Short message")

    def test_message_str_representation_long(self):
        """Test string representation of Message with long content."""
        long_content = "This is a very long message " * 10
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content=long_content
        )

        str_repr = str(message)
        self.assertIn("sender:", str_repr)
        self.assertIn("...", str_repr)
        self.assertEqual(len(str_repr.split(": ", 1)[1]), 53)  # 50 chars + "..."

    def test_is_private_method_private_message(self):
        """Test is_private() returns True for private messages."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Private"
        )

        self.assertTrue(message.is_private())

    def test_is_private_method_lobby_message(self):
        """Test is_private() returns False for lobby messages."""
        message = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="Public"
        )

        self.assertFalse(message.is_private())

    def test_is_lobby_message_method_lobby_message(self):
        """Test is_lobby_message() returns True for lobby messages."""
        message = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="Lobby message"
        )

        self.assertTrue(message.is_lobby_message())

    def test_is_lobby_message_method_private_message(self):
        """Test is_lobby_message() returns False for private messages."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Private"
        )

        self.assertFalse(message.is_lobby_message())

    def test_get_chat_context_lobby_message(self):
        """Test get_chat_context() for lobby messages."""
        message = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="Test"
        )

        context = message.get_chat_context()

        self.assertEqual(context['type'], 'lobby')
        self.assertEqual(context['context'], self.lobby)
        self.assertEqual(context['context_name'], 'Test Lobby')

    def test_get_chat_context_private_message(self):
        """Test get_chat_context() for private messages."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Test"
        )

        context = message.get_chat_context()

        self.assertEqual(context['type'], 'private')
        self.assertEqual(context['context'], self.user2)
        self.assertEqual(context['context_name'], 'Private chat with receiver')

    def test_get_chat_context_invalid_message(self):
        """Test get_chat_context() for message without lobby or receiver.

        Note: This should not happen in practice due to validation,
        but we test the fallback behavior.
        """
        # Create message without validation
        message = Message(
            sender=self.user1,
            content="Invalid"
        )

        context = message.get_chat_context()

        self.assertEqual(context['type'], 'unknown')
        self.assertIsNone(context['context'])
        self.assertEqual(context['context_name'], 'Unknown')

    def test_get_lobby_messages_method(self):
        """Test get_lobby_messages() retrieves lobby messages."""
        # Create multiple messages
        message1 = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="First message"
        )
        
        message2 = Message.objects.create(
            sender=self.user2,
            lobby=self.lobby,
            content="Second message"
        )
        
        # Create a private message that should not be included
        Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Private"
        )
        
        messages = list(Message.get_lobby_messages(self.lobby))
        
        self.assertEqual(len(messages), 2)
        # Should be ordered by sent_at descending (newest first)
        self.assertEqual(messages[0], message2)
        self.assertEqual(messages[1], message1)

    def test_get_lobby_messages_limit(self):
        """Test get_lobby_messages() respects limit parameter."""
        # Create 10 messages
        for i in range(10):
            Message.objects.create(
                sender=self.user1,
                lobby=self.lobby,
                content=f"Message {i}"
            )
        
        messages = list(Message.get_lobby_messages(self.lobby, limit=5))
        
        self.assertEqual(len(messages), 5)

    def test_get_lobby_messages_empty_lobby(self):
        """Test get_lobby_messages() returns empty queryset for lobby with no messages."""
        empty_lobby = Lobby.objects.create(
            owner=self.user2,
            name="Empty Lobby",
            status='waiting'
        )
        
        messages = list(Message.get_lobby_messages(empty_lobby))
        
        self.assertEqual(len(messages), 0)

    def test_get_private_conversation_method(self):
        """Test get_private_conversation() retrieves conversation between two users."""
        # Create messages in both directions
        message1 = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Hello from user1"
        )
        
        message2 = Message.objects.create(
            sender=self.user2,
            receiver=self.user1,
            content="Reply from user2"
        )
        
        message3 = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Another message from user1"
        )
        
        # Create a lobby message that should not be included
        Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="Lobby message"
        )
        
        # Create a message to another user that should not be included
        user3 = User.objects.create_user(username="user3", password="test")
        Message.objects.create(
            sender=self.user1,
            receiver=user3,
            content="Message to user3"
        )
        
        messages = list(Message.get_private_conversation(self.user1, self.user2))
        
        self.assertEqual(len(messages), 3)

    def test_get_private_conversation_order(self):
        """Test get_private_conversation() returns messages in descending order."""
        message1 = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="First"
        )
        
        message2 = Message.objects.create(
            sender=self.user2,
            receiver=self.user1,
            content="Second"
        )
        
        messages = list(Message.get_private_conversation(self.user1, self.user2))
        
        # Should be ordered by sent_at descending (newest first)
        self.assertEqual(messages[0], message2)
        self.assertEqual(messages[1], message1)

    def test_get_private_conversation_limit(self):
        """Test get_private_conversation() respects limit parameter."""
        # Create 10 messages
        for i in range(10):
            Message.objects.create(
                sender=self.user1,
                receiver=self.user2,
                content=f"Message {i}"
            )
        
        messages = list(Message.get_private_conversation(self.user1, self.user2, limit=5))
        
        self.assertEqual(len(messages), 5)

    def test_get_private_conversation_no_messages(self):
        """Test get_private_conversation() returns empty queryset when no conversation exists."""
        messages = list(Message.get_private_conversation(self.user1, self.user2))
        
        self.assertEqual(len(messages), 0)

    def test_get_private_conversation_symmetry(self):
        """Test get_private_conversation() works regardless of parameter order."""
        Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Test"
        )
        
        messages1 = list(Message.get_private_conversation(self.user1, self.user2))
        messages2 = list(Message.get_private_conversation(self.user2, self.user1))
        
        self.assertEqual(len(messages1), len(messages2))
        self.assertEqual(messages1, messages2)

    def test_clean_validation_both_lobby_and_receiver(self):
        """Test clean() raises ValidationError when both lobby and receiver are set."""
        message = Message(
            sender=self.user1,
            receiver=self.user2,
            lobby=self.lobby,
            content="Invalid message"
        )

        with self.assertRaises(ValidationError) as context:
            message.clean()

        self.assertIn("both lobby and receiver", str(context.exception))

    def test_clean_validation_neither_lobby_nor_receiver(self):
        """Test clean() raises ValidationError when neither lobby nor receiver is set."""
        message = Message(
            sender=self.user1,
            content="Invalid message"
        )

        with self.assertRaises(ValidationError) as context:
            message.clean()

        self.assertIn("either lobby or receiver", str(context.exception))

    def test_clean_validation_passes_with_receiver(self):
        """Test clean() passes validation with receiver set."""
        message = Message(
            sender=self.user1,
            receiver=self.user2,
            content="Valid private message"
        )

        # Should not raise ValidationError
        message.clean()

    def test_clean_validation_passes_with_lobby(self):
        """Test clean() passes validation with lobby set."""
        message = Message(
            sender=self.user1,
            lobby=self.lobby,
            content="Valid lobby message"
        )

        # Should not raise ValidationError
        message.clean()

    def test_save_calls_clean(self):
        """Test that save() method calls clean() for validation."""
        message = Message(
            sender=self.user1,
            receiver=self.user2,
            lobby=self.lobby,
            content="Invalid"
        )

        with self.assertRaises(ValidationError):
            message.save()

    def test_save_valid_message(self):
        """Test that save() works for valid messages."""
        message = Message(
            sender=self.user1,
            receiver=self.user2,
            content="Valid message"
        )

        # Should not raise any exception
        message.save()

        self.assertIsNotNone(message.id)

    def test_message_ordering(self):
        """Test that messages are ordered by sent_at descending."""
        message1 = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="First"
        )

        message2 = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Second"
        )

        message3 = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Third"
        )

        messages = list(Message.objects.all())

        # Should be ordered newest first
        self.assertEqual(messages[0], message3)
        self.assertEqual(messages[1], message2)
        self.assertEqual(messages[2], message1)

    def test_message_indexes_exist(self):
        """Test that database indexes are properly configured.

        This test ensures the model has the expected index definitions.
        Actual index creation is verified by migrations.
        """
        # Check that indexes are defined in Meta
        self.assertEqual(len(Message._meta.indexes), 3)

    def test_message_content_can_be_long(self):
        """Test that message content can store long text."""
        long_content = "A" * 10000  # 10,000 characters

        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content=long_content
        )

        message.refresh_from_db()
        self.assertEqual(len(message.content), 10000)

    def test_message_related_names(self):
        """Test that related names work correctly."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Test"
        )

        # Test sender's sent_messages
        self.assertIn(message, self.user1.sent_messages.all())

        # Test receiver's received_messages
        self.assertIn(message, self.user2.received_messages.all())

        # Test lobby's messages (for lobby message)
        lobby_message = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="Lobby test"
        )

        self.assertIn(lobby_message, self.lobby.messages.all())

    def test_message_cascade_delete_sender(self):
        """Test that messages are deleted when sender is deleted."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Test"
        )

        message_id = message.id
        self.user1.delete()

        # Message should be deleted
        self.assertFalse(Message.objects.filter(id=message_id).exists())

    def test_message_cascade_delete_receiver(self):
        """Test that private messages are deleted when receiver is deleted."""
        message = Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="Test"
        )

        message_id = message.id
        self.user2.delete()

        # Message should be deleted
        self.assertFalse(Message.objects.filter(id=message_id).exists())

    def test_message_cascade_delete_lobby(self):
        """Test that lobby messages are deleted when lobby is deleted."""
        message = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="Test"
        )

        message_id = message.id
        self.lobby.delete()

        # Message should be deleted
        self.assertFalse(Message.objects.filter(id=message_id).exists())

    def test_multiple_users_can_message_same_lobby(self):
        """Test that multiple users can send messages to the same lobby."""
        user3 = User.objects.create_user(username="user3", password="test")
        
        message1 = Message.objects.create(
            sender=self.user1,
            lobby=self.lobby,
            content="From user1"
        )
        
        message2 = Message.objects.create(
            sender=self.user2,
            lobby=self.lobby,
            content="From user2"
        )
        
        message3 = Message.objects.create(
            sender=user3,
            lobby=self.lobby,
            content="From user3"
        )
        
        lobby_messages = list(Message.get_lobby_messages(self.lobby))
        self.assertEqual(len(lobby_messages), 3)

    def test_user_can_have_conversations_with_multiple_users(self):
        """Test that a user can have separate conversations with multiple users."""
        user3 = User.objects.create_user(username="user3", password="test")
        
        # Conversation with user2
        Message.objects.create(
            sender=self.user1,
            receiver=self.user2,
            content="To user2"
        )
        
        # Conversation with user3
        Message.objects.create(
            sender=self.user1,
            receiver=user3,
            content="To user3"
        )
        
        conv_user2 = list(Message.get_private_conversation(self.user1, self.user2))
        conv_user3 = list(Message.get_private_conversation(self.user1, user3))
        
        self.assertEqual(len(conv_user2), 1)
        self.assertEqual(len(conv_user3), 1)
        self.assertEqual(conv_user2[0].receiver, self.user2)
        self.assertEqual(conv_user3[0].receiver, user3)