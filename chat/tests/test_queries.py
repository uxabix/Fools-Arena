"""Tests for query methods on the Message model."""

import pytest
from chat.models import Message
from game.models import Lobby


@pytest.mark.django_db
class TestMessageQueries:
    """Test suite for class methods on Message that perform queries."""

    @pytest.fixture(autouse=True)
    def set_up(self, test_user, second_user, basic_lobby):
        """Sets up users and a lobby for the tests."""
        self.user1 = test_user
        self.user2 = second_user
        self.lobby = basic_lobby

    def test_get_lobby_messages(self):
        """Tests that get_lobby_messages() retrieves only relevant lobby messages."""
        msg1 = Message.objects.create(sender=self.user1, lobby=self.lobby, content="1")
        msg2 = Message.objects.create(sender=self.user2, lobby=self.lobby, content="2")
        # Private message, should not be included
        Message.objects.create(sender=self.user1, receiver=self.user2, content="private")

        messages = list(Message.get_lobby_messages(self.lobby))
        assert len(messages) == 2
        # Should be ordered by sent_at descending (newest first)
        assert messages[0] == msg2
        assert messages[1] == msg1

    def test_get_lobby_messages_limit(self):
        """Tests that get_lobby_messages() respects the limit parameter."""
        for i in range(5):
            Message.objects.create(
                sender=self.user1, lobby=self.lobby, content=f"Msg {i}"
            )

        messages = list(Message.get_lobby_messages(self.lobby, limit=3))
        assert len(messages) == 3

    def test_get_lobby_messages_empty(self, lobby_factory):
        """Tests get_lobby_messages() for a lobby with no messages."""
        empty_lobby = lobby_factory(owner=self.user1, name="Empty")
        messages = list(Message.get_lobby_messages(empty_lobby))
        assert len(messages) == 0

    def test_get_private_conversation(self, user_factory):
        """Tests get_private_conversation() retrieves a full conversation."""
        user3 = user_factory(username='user3')
        # Conversation between user1 and user2
        msg1 = Message.objects.create(sender=self.user1, receiver=self.user2, content="Hi")
        msg2 = Message.objects.create(sender=self.user2, receiver=self.user1, content="Hello")
        # Other messages that should be ignored
        Message.objects.create(sender=self.user1, lobby=self.lobby, content="Lobby msg")
        Message.objects.create(sender=self.user1, receiver=user3, content="To user3")

        messages = list(Message.get_private_conversation(self.user1, self.user2))
        assert len(messages) == 2
        assert msg1 in messages
        assert msg2 in messages

    def test_get_private_conversation_order(self):
        """Tests get_private_conversation() returns messages in descending order."""
        msg1 = Message.objects.create(sender=self.user1, receiver=self.user2, content="First")
        msg2 = Message.objects.create(sender=self.user2, receiver=self.user1, content="Second")

        messages = list(Message.get_private_conversation(self.user1, self.user2))
        assert messages[0] == msg2
        assert messages[1] == msg1

    def test_get_private_conversation_limit(self):
        """Tests get_private_conversation() respects the limit parameter."""
        for i in range(5):
            Message.objects.create(
                sender=self.user1, receiver=self.user2, content=f"Msg {i}"
            )

        messages = list(Message.get_private_conversation(self.user1, self.user2, limit=3))
        assert len(messages) == 3

    def test_get_private_conversation_symmetry(self):
        """Tests get_private_conversation() works regardless of parameter order."""
        Message.objects.create(sender=self.user1, receiver=self.user2, content="Test")

        messages1 = list(Message.get_private_conversation(self.user1, self.user2))
        messages2 = list(Message.get_private_conversation(self.user2, self.user1))

        assert len(messages1) == 1
        assert messages1 == messages2
