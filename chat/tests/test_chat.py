"""Tests for the Chat and ChatParticipant models in the chat app."""

import pytest
from django.contrib.auth import get_user_model

from chat.models import Chat, ChatParticipant

User = get_user_model()


@pytest.mark.django_db
class TestChatModel:
    """Tests for the Chat model and its participant management."""

    def test_create_chat(self):
        """Test creating a chat instance."""
        chat = Chat.objects.create(name="Test Chat", is_group=True)
        assert chat.name == "Test Chat"
        assert chat.is_group is True
        assert chat.get_participants().count() == 0

    def test_add_participant(self, test_user):
        """Test adding a user to a chat."""
        chat = Chat.objects.create(name="Test Chat")
        participant, created = chat.add_participant(test_user, role="admin")

        assert created is True
        assert participant.user == test_user
        assert participant.role == "admin"
        assert chat.has_participant(test_user) is True

    def test_add_existing_participant_updates_role(self, test_user):
        """Test that adding an existing participant updates their role."""
        chat = Chat.objects.create(name="Another Chat")
        chat.add_participant(test_user, role="member")
        participant, created = chat.add_participant(test_user, role="admin")

        assert created is False
        assert participant.role == "admin"

    def test_remove_participant(self, test_user):
        """Test removing a participant from a chat."""
        chat = Chat.objects.create(name="Chat Remove")
        chat.add_participant(test_user)
        deleted_count = chat.remove_participant(test_user)

        assert deleted_count == 1
        assert chat.has_participant(test_user) is False

    def test_get_owners_and_admins(self, user_factory):
        """Test retrieving owners and admins from a chat."""
        owner = user_factory(username="owner")
        admin = user_factory(username="admin")
        member = user_factory(username="member")
        chat = Chat.objects.create(name="Roles Chat")

        chat.add_participant(owner, role="owner")
        chat.add_participant(admin, role="admin")
        chat.add_participant(member, role="member")

        owners = chat.get_owners()
        admins = chat.get_admins()

        assert owners.count() == 1
        assert owners.first().user == owner
        assert admins.count() == 1
        assert admins.first().user == admin


@pytest.mark.django_db
class TestChatParticipantModel:
    """Tests for ChatParticipant model methods like role checks and promotion/demotion."""

    def test_is_owner_and_is_admin(self, test_user, second_user):
        """Test role checks for owner, admin, and member."""
        chat = Chat.objects.create(name="Role Check Chat")
        owner = chat.add_participant(test_user, role="owner")[0]
        admin = chat.add_participant(second_user, role="admin")[0]

        assert owner.is_owner() is True
        assert owner.is_admin() is True
        assert admin.is_owner() is False
        assert admin.is_admin() is True

        # Test member
        member_user = get_user_model().objects.create_user(username="member")
        member = chat.add_participant(member_user, role="member")[0]
        assert member.is_owner() is False
        assert member.is_admin() is False

    def test_promote_and_demote(self, test_user):
        """Test promoting a member to admin and demoting an admin."""
        chat = Chat.objects.create(name="Promotion Chat")
        participant = chat.add_participant(test_user, role="member")[0]

        # Promote member
        participant.promote()
        participant.refresh_from_db()
        assert participant.role == "admin"

        # Demote admin
        participant.demote()
        participant.refresh_from_db()
        assert participant.role == "member"

    def test_promote_owner_does_nothing(self, test_user):
        """Owner role should not be changed by promote/demote."""
        chat = Chat.objects.create(name="Owner Chat")
        participant = chat.add_participant(test_user, role="owner")[0]

        participant.promote()
        participant.refresh_from_db()
        assert participant.role == "owner"

        participant.demote()
        participant.refresh_from_db()
        assert participant.role == "owner"
