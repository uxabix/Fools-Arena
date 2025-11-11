"""Tests for the Message model in the chat app."""

import pytest
from django.core.exceptions import ValidationError
from chat.models import Message


@pytest.mark.django_db
class TestMessageModel:
    """Test suite for Message model."""

    def test_private_message_creation(self, test_user, second_user):
        """Tests that private Message instances are created correctly."""
        message = Message.objects.create(
            sender=test_user,
            receiver=second_user,
            content="Hello, this is a private message!"
        )
        assert message.sender == test_user
        assert message.receiver == second_user
        assert message.lobby is None
        assert message.content == "Hello, this is a private message!"

    def test_lobby_message_creation(self, test_user, basic_lobby):
        """Tests that lobby Message instances are created correctly."""
        message = Message.objects.create(
            sender=test_user,
            lobby=basic_lobby,
            content="Hello everyone in the lobby!"
        )
        assert message.sender == test_user
        assert message.lobby == basic_lobby
        assert message.receiver is None
        assert message.content == "Hello everyone in the lobby!"

    def test_message_uuid_generation(self, test_user, second_user):
        """Tests that UUID is automatically generated for messages."""
        message = Message.objects.create(
            sender=test_user, receiver=second_user, content="Test"
        )
        assert message.id is not None
        assert len(str(message.id)) == 36

    def test_message_sent_at_auto_generation(self, test_user, second_user):
        """Tests that sent_at timestamp is automatically set."""
        message = Message.objects.create(
            sender=test_user, receiver=second_user, content="Test"
        )
        assert message.sent_at is not None

    def test_message_str_representation(self, test_user, second_user):
        """Tests string representation of Message."""
        short_content = "Short message"
        message = Message.objects.create(
            sender=test_user, receiver=second_user, content=short_content
        )
        assert str(message) == f"{test_user.username}: {short_content}"

    def test_is_private_method(self, test_user, second_user, basic_lobby):
        """Tests is_private() method for private and lobby messages."""
        private_message = Message.objects.create(
            sender=test_user, receiver=second_user, content="Private"
        )
        lobby_message = Message.objects.create(
            sender=test_user, lobby=basic_lobby, content="Public"
        )
        assert private_message.is_private() is True
        assert lobby_message.is_private() is False

    def test_is_lobby_message_method(self, test_user, second_user, basic_lobby):
        """Tests is_lobby_message() method for private and lobby messages."""
        private_message = Message.objects.create(
            sender=test_user, receiver=second_user, content="Private"
        )
        lobby_message = Message.objects.create(
            sender=test_user, lobby=basic_lobby, content="Public"
        )
        assert lobby_message.is_lobby_message() is True
        assert private_message.is_lobby_message() is False

    def test_get_chat_context(self, test_user, second_user, basic_lobby):
        """Tests get_chat_context() for lobby and private messages."""
        private_message = Message.objects.create(
            sender=test_user, receiver=second_user, content="Test"
        )
        lobby_message = Message.objects.create(
            sender=test_user, lobby=basic_lobby, content="Test"
        )

        private_context = private_message.get_chat_context()
        assert private_context['type'] == 'private'
        assert private_context['context'] == second_user

        lobby_context = lobby_message.get_chat_context()
        assert lobby_context['type'] == 'lobby'
        assert lobby_context['context'] == basic_lobby

    def test_clean_validation_both_lobby_and_receiver(
            self, test_user, second_user, basic_lobby
    ):
        """Tests clean() raises ValidationError when both lobby and receiver are set."""
        message = Message(
            sender=test_user,
            receiver=second_user,
            lobby=basic_lobby,
            content="Invalid"
        )
        with pytest.raises(ValidationError, match="both lobby and receiver"):
            message.clean()

    def test_clean_validation_neither_lobby_nor_receiver(self, test_user):
        """Tests clean() raises ValidationError when neither lobby nor receiver is set."""
        message = Message(sender=test_user, content="Invalid")
        with pytest.raises(ValidationError, match="either lobby or receiver"):
            message.clean()
