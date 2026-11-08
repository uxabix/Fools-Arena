"""Tests for common query patterns on the Message model."""

import pytest

from chat.models import Chat, Message
from game.models import Lobby


@pytest.mark.django_db
class TestMessageQueries:
    """Test suite for typical query scenarios around Message objects."""

    @pytest.fixture(autouse=True)
    def set_up(self, test_user, second_user, basic_lobby):
        """Prepare users, lobby, and base chats for the query tests.

        Creates:
            - user1, user2: Two distinct users.
            - lobby: A lobby instance.
            - lobby_chat: Group chat attached to the lobby.
            - private_chat: Direct private chat between user1 and user2.
        """
        self.user1 = test_user
        self.user2 = second_user
        self.lobby: Lobby = basic_lobby

        self.lobby_chat = Chat.objects.create(
            name="Lobby Chat",
            is_group=True,
            is_lobby=True,
            lobby=self.lobby,
        )
        self.private_chat = Chat.objects.create(
            name="Private Chat",
            is_group=False,
            is_lobby=False,
        )

    def test_get_lobby_messages(self):
        """Tests that lobby messages are retrieved only from the lobby chat.

        Only messages attached to the lobby_chat should be returned and they
        must be ordered by sent_at descending (newest first).
        """
        msg1 = Message.objects.create(
            sender=self.user1,
            chat=self.lobby_chat,
            content="1",
        )
        msg2 = Message.objects.create(
            sender=self.user2,
            chat=self.lobby_chat,
            content="2",
        )
        # Message in a different chat, should not be included
        Message.objects.create(
            sender=self.user1,
            chat=self.private_chat,
            content="private",
        )

        messages = list(
            Message.objects.filter(chat=self.lobby_chat).order_by("-sent_at")
        )
        assert len(messages) == 2
        assert messages[0] == msg2
        assert messages[1] == msg1

    def test_get_lobby_messages_limit(self):
        """Tests that limiting lobby messages via slice returns expected count."""
        for i in range(5):
            Message.objects.create(
                sender=self.user1,
                chat=self.lobby_chat,
                content=f"Msg {i}",
            )

        messages = list(
            Message.objects.filter(chat=self.lobby_chat)
            .order_by("-sent_at")[:3]
        )
        assert len(messages) == 3

    def test_get_lobby_messages_empty(self, lobby_factory):
        """Tests lobby chat with no messages returns an empty result."""
        empty_lobby = lobby_factory(owner=self.user1, name="Empty")
        empty_lobby_chat = Chat.objects.create(
            name="Empty Lobby Chat",
            is_group=True,
            is_lobby=True,
            lobby=empty_lobby,
        )

        messages = list(
            Message.objects.filter(chat=empty_lobby_chat).order_by("-sent_at")
        )
        assert len(messages) == 0

    def test_get_private_conversation(self, user_factory):
        """Tests retrieving a private conversation within a dedicated chat.

        Only messages inside the given private chat between user1 and user2
        should be returned; other chats or users must be ignored.
        """
        user3 = user_factory(username="user3")

        # Conversation between user1 and user2 in the private_chat
        msg1 = Message.objects.create(
            sender=self.user1,
            chat=self.private_chat,
            content="Hi",
        )
        msg2 = Message.objects.create(
            sender=self.user2,
            chat=self.private_chat,
            content="Hello",
        )

        # Other messages that should be ignored
        other_private_chat = Chat.objects.create(
            name="Other Private",
            is_group=False,
            is_lobby=False,
        )
        Message.objects.create(
            sender=self.user1,
            chat=self.lobby_chat,
            content="Lobby msg",
        )
        Message.objects.create(
            sender=self.user1,
            chat=other_private_chat,
            content="To user3",
        )

        messages = list(
            Message.objects.filter(chat=self.private_chat).order_by("-sent_at")
        )
        assert len(messages) == 2
        assert msg1 in messages
        assert msg2 in messages

    def test_get_private_conversation_order(self):
        """Tests that private messages are ordered newest first inside a chat."""
        msg1 = Message.objects.create(
            sender=self.user1,
            chat=self.private_chat,
            content="First",
        )
        msg2 = Message.objects.create(
            sender=self.user2,
            chat=self.private_chat,
            content="Second",
        )

        messages = list(
            Message.objects.filter(chat=self.private_chat).order_by("-sent_at")
        )
        assert messages[0] == msg2
        assert messages[1] == msg1

    def test_get_private_conversation_limit(self):
        """Tests limiting private conversation size via slice."""
        for i in range(5):
            Message.objects.create(
                sender=self.user1,
                chat=self.private_chat,
                content=f"Msg {i}",
            )

        messages = list(
            Message.objects.filter(chat=self.private_chat)
            .order_by("-sent_at")[:3]
        )
        assert len(messages) == 3

    def test_private_conversation_is_chat_specific(self):
        """Tests that private conversation is isolated per chat instance.

        Messages from another private chat between the same users should not
        appear when querying by the original chat.
        """
        # Messages in the original private_chat
        Message.objects.create(
            sender=self.user1,
            chat=self.private_chat,
            content="Original chat",
        )

        # Same users, but another chat
        another_private_chat = Chat.objects.create(
            name="Another Private Chat",
            is_group=False,
            is_lobby=False,
        )
        Message.objects.create(
            sender=self.user1,
            chat=another_private_chat,
            content="Another chat message",
        )

        messages_original = list(
            Message.objects.filter(chat=self.private_chat).order_by("-sent_at")
        )
        messages_other = list(
            Message.objects.filter(chat=another_private_chat).order_by("-sent_at")
        )

        assert len(messages_original) == 1
        assert len(messages_other) == 1
        assert messages_original[0].chat == self.private_chat
        assert messages_other[0].chat == another_private_chat
