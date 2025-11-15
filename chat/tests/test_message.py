"""Tests for the Message model in the chat app."""

import pytest
from django.utils import timezone

from chat.models import Chat, Message


@pytest.mark.django_db
class TestMessageModel:
    """Test suite for Message model with chat-based messaging."""

    def test_message_creation_in_lobby_chat(self, test_user, basic_lobby):
        """Tests that messages are created correctly for lobby-attached chats.

        This scenario represents a group chat bound to a specific lobby.
        """
        chat = Chat.objects.create(
            name="Lobby Chat",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )

        message = Message.objects.create(
            sender=test_user,
            chat=chat,
            content="Hello lobby chat!",
        )

        assert message.sender == test_user
        assert message.chat == chat
        assert message.chat.is_lobby is True
        assert message.chat.lobby == basic_lobby
        assert message.content == "Hello lobby chat!"
        assert message.sent_at is not None

    def test_message_creation_in_private_chat(self, test_user, second_user):
        """Tests that messages are created correctly for private chats.

        This scenario represents a direct chat between two users without an attached lobby.
        """
        private_chat = Chat.objects.create(
            name="Private Chat",
            is_group=False,
            is_lobby=False,
        )

        message = Message.objects.create(
            sender=test_user,
            chat=private_chat,
            content="Hello in private chat!",
        )

        assert message.sender == test_user
        assert message.chat == private_chat
        assert message.chat.is_group is False
        assert message.chat.is_lobby is False
        assert message.content == "Hello in private chat!"
        assert message.sent_at is not None

    def test_message_uuid_generation(self, test_user, basic_lobby):
        """Tests that UUID is automatically generated for messages."""
        chat = Chat.objects.create(
            name="UUID Chat",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )

        message = Message.objects.create(
            sender=test_user,
            chat=chat,
            content="Test",
        )

        assert message.id is not None
        # UUID4 format length (including dashes) should be 36 characters.
        assert len(str(message.id)) == 36

    def test_message_sent_at_auto_generation(self, test_user, basic_lobby):
        """Tests that sent_at timestamp is automatically set on creation."""
        chat = Chat.objects.create(
            name="Timestamp Chat",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )

        before_creation = timezone.now()
        message = Message.objects.create(
            sender=test_user,
            chat=chat,
            content="Test timestamp",
        )

        assert message.sent_at is not None
        # sent_at should not be earlier than the check before creation
        assert message.sent_at >= before_creation

    def test_message_str_representation_short_content(self, test_user, basic_lobby):
        """Tests string representation of Message for short content."""
        chat = Chat.objects.create(
            name="Str Chat Short",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )

        short_content = "Short message"
        message = Message.objects.create(
            sender=test_user,
            chat=chat,
            content=short_content,
        )

        assert str(message) == f"{test_user.username}: {short_content}"

    def test_message_str_representation_long_content_truncated(
        self,
        test_user,
        basic_lobby,
    ):
        """Tests that long content is truncated in string representation."""
        chat = Chat.objects.create(
            name="Str Chat Long",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )

        long_content = "x" * 80
        message = Message.objects.create(
            sender=test_user,
            chat=chat,
            content=long_content,
        )

        preview = long_content[:50] + "..."
        assert str(message) == f"{test_user.username}: {preview}"

    def test_message_ordering_by_sent_at(self, test_user, basic_lobby):
        """Tests default ordering: newest messages should come first."""
        chat = Chat.objects.create(
            name="Ordering Chat",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )

        older_message = Message.objects.create(
            sender=test_user,
            chat=chat,
            content="Older message",
        )
        newer_message = Message.objects.create(
            sender=test_user,
            chat=chat,
            content="Newer message",
        )

        messages = list(Message.objects.filter(chat=chat))
        # Meta.ordering = ['-sent_at'], newest first
        assert messages[0] == newer_message
        assert messages[1] == older_message

    def test_is_lobby_message_and_is_private_flags(self, test_user, basic_lobby):
        """Tests is_lobby_message() and is_private() according to chat type."""
        lobby_chat = Chat.objects.create(
            name="Lobby Chat",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )
        private_chat = Chat.objects.create(
            name="Private Chat",
            is_group=False,
            is_lobby=False,
        )
        group_chat = Chat.objects.create(
            name="Group Chat",
            is_group=True,
            is_lobby=False,
        )

        lobby_msg = Message.objects.create(
            sender=test_user,
            chat=lobby_chat,
            content="Lobby",
        )
        private_msg = Message.objects.create(
            sender=test_user,
            chat=private_chat,
            content="Private",
        )
        group_msg = Message.objects.create(
            sender=test_user,
            chat=group_chat,
            content="Group",
        )

        assert lobby_msg.is_lobby_message() is True
        assert lobby_msg.is_private() is False

        assert private_msg.is_lobby_message() is False
        assert private_msg.is_private() is True

        assert group_msg.is_lobby_message() is False
        assert group_msg.is_private() is False

    def test_get_chat_context_for_different_chat_types(
        self,
        test_user,
        basic_lobby,
    ):
        """Tests get_chat_context() for lobby, group, and private chats."""
        lobby_chat = Chat.objects.create(
            name="Lobby Chat",
            is_group=True,
            is_lobby=True,
            lobby=basic_lobby,
        )
        group_chat = Chat.objects.create(
            name="Group Chat",
            is_group=True,
            is_lobby=False,
        )
        private_chat = Chat.objects.create(
            name="Private Chat",
            is_group=False,
            is_lobby=False,
        )

        lobby_msg = Message.objects.create(
            sender=test_user,
            chat=lobby_chat,
            content="Lobby",
        )
        group_msg = Message.objects.create(
            sender=test_user,
            chat=group_chat,
            content="Group",
        )
        private_msg = Message.objects.create(
            sender=test_user,
            chat=private_chat,
            content="Private",
        )

        lobby_ctx = lobby_msg.get_chat_context()
        assert lobby_ctx["type"] == "lobby"
        assert "name" in lobby_ctx

        group_ctx = group_msg.get_chat_context()
        assert group_ctx["type"] == "group"
        assert "name" in group_ctx

        private_ctx = private_msg.get_chat_context()
        assert private_ctx["type"] == "private"
        assert "name" in private_ctx
