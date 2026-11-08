"""Tests for server-rendered chat pages (template parity with the API)."""

import pytest
from django.urls import reverse

from accounts.models import Block
from chat.models import Chat, Message


@pytest.mark.django_db
class TestChatTemplateViews:
    """Login-protected template flows: inbox, start DM, room + post."""

    def test_inbox_redirects_anonymous(self, client):
        """Inbox requires login."""
        r = client.get(reverse("chat:inbox"))
        assert r.status_code == 302
        assert "/accounts/login/" in r.url

    def test_inbox_lists_chats(self, client, test_user, second_user):
        """Authenticated user sees direct chat in the list."""
        client.force_login(test_user)
        chat, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        r = client.get(reverse("chat:inbox"))
        assert r.status_code == 200
        assert str(chat.pk) in r.content.decode()

    def test_start_direct_opens_room(self, client, test_user, second_user):
        """Posting username redirects to the shared DM room."""
        client.force_login(test_user)
        r = client.post(
            reverse("chat:start_direct"),
            {"other_username": second_user.username},
        )
        chat, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        assert r.status_code == 302
        assert r.url == reverse("chat:room", kwargs={"chat_id": chat.pk})

    def test_room_post_creates_message(self, client, test_user, second_user):
        """HTTP form post stores a message like the API."""
        client.force_login(test_user)
        chat, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        r = client.post(
            reverse("chat:room", kwargs={"chat_id": chat.pk}),
            {"content": "  template hi  "},
        )
        assert r.status_code == 302
        assert Message.objects.filter(
            chat=chat, sender=test_user, content="template hi"
        ).exists()

    def test_room_blocked_post_fails(self, client, test_user, second_user):
        """Template path shows error and does not store when blocked."""
        chat, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        Block.objects.create(blocker=second_user, blocked=test_user)
        client.force_login(test_user)
        r = client.post(
            reverse("chat:room", kwargs={"chat_id": chat.pk}),
            {"content": "blocked"},
        )
        assert r.status_code == 200
        assert not Message.objects.filter(
            chat=chat, content="blocked"
        ).exists()

    def test_room_forbidden_for_non_member(self, client, test_user, user_factory):
        """Non-participant is redirected to inbox with a message."""
        other = user_factory(username="onlymember")
        chat = Chat.objects.create(name="X", is_group=True)
        chat.add_participant(other)
        client.force_login(test_user)
        r = client.get(
            reverse("chat:room", kwargs={"chat_id": chat.pk}),
        )
        assert r.status_code == 302
        assert r.url == reverse("chat:inbox")
