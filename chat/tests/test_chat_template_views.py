"""Tests for server-rendered chat pages (template parity with the API)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

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

    def test_start_direct_labels_are_not_nested(self, client, test_user):
        """Each label wraps only its caption, and hints are escaped text."""
        import re

        client.force_login(test_user)
        html = client.get(reverse("chat:start_direct")).content.decode()
        labels = re.findall(r"<label\b[^>]*>.*?</label>", html, flags=re.I | re.S)
        assert labels
        for label in labels:
            assert label.lower().count("<label") == 1
        assert 'class="field-hint"' in html
        assert "<ul>" not in html.split('class="field-hint"', 1)[-1][:200]

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

    def test_inbox_orders_by_latest_message(self, client, test_user, second_user, user_factory):
        """An older chat with a new line sorts above a newer empty chat."""
        third = user_factory(username="thirdplayer")
        older, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        newer, _ = Chat.objects.get_or_create_direct(test_user, third)
        Chat.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=2))
        message = Message.objects.create(sender=second_user, chat=older, content="still talking")
        message.sent_at = timezone.now()
        message.save(update_fields=["sent_at"])
        client.force_login(test_user)
        html = client.get(reverse("chat:inbox")).content.decode()
        assert html.find(str(older.pk)) < html.find(str(newer.pk))
        assert "still talking" in html
        assert "No messages yet" in html

    def test_start_direct_unknown_user_marks_the_field(self, client, test_user):
        """A missing username is explained on the field, with the typed value kept."""
        client.force_login(test_user)
        html = client.post(
            reverse("chat:start_direct"),
            {"other_username": "missing-player"},
        ).content.decode()
        assert "No player with that username." in html
        assert 'value="missing-player"' in html or "missing-player" in html
        assert 'class="field-error"' in html

    def test_room_renders_each_message_once(self, client, test_user, second_user):
        """The page prints the latest page once and has a single composer."""
        client.force_login(test_user)
        chat, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        Message.objects.create(sender=second_user, chat=chat, content="unique-line-42")
        html = client.get(reverse("chat:room", kwargs={"chat_id": chat.pk})).content.decode()
        assert html.count("data-message-id=") == 1
        assert "unique-line-42" in html
        assert reverse("player-profile", kwargs={"username": second_user.username}) in html
        assert "Send via WS" not in html
        assert "Live updates" not in html
        assert html.count('id="chat-form"') == 1

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

    def test_direct_tab_hides_lobby_until_the_match_starts(
        self, client, test_user, second_user, basic_lobby
    ):
        """Direct, lobby, and game folders follow the chat type and lobby status."""
        direct, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        lobby_chat = Chat.objects.create(
            name="Waiting room",
            is_lobby=True,
            is_group=True,
            lobby=basic_lobby,
        )
        lobby_chat.add_participant(test_user)
        client.force_login(test_user)
        direct_html = client.get(reverse("chat:inbox") + "?tab=direct").content.decode()
        assert str(direct.pk) in direct_html
        assert str(lobby_chat.pk) not in direct_html
        lobby_html = client.get(reverse("chat:inbox") + "?tab=lobby").content.decode()
        assert str(lobby_chat.pk) in lobby_html
        basic_lobby.status = "playing"
        basic_lobby.save(update_fields=["status"])
        game_html = client.get(reverse("chat:inbox") + "?tab=game").content.decode()
        assert str(lobby_chat.pk) in game_html
        assert str(direct.pk) not in game_html

    def test_inbox_search_keeps_the_query_for_the_browser(self, client, test_user, second_user, user_factory):
        """Name search is stored in the field; every chat in the folder stays in the HTML."""
        matched, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        other = user_factory(username="otherseek")
        skipped, _ = Chat.objects.get_or_create_direct(test_user, other)
        client.force_login(test_user)
        html = client.get(reverse("chat:inbox") + "?q=player2").content.decode()
        assert str(matched.pk) in html
        assert str(skipped.pk) in html
        assert 'value="player2"' in html
        assert 'data-search="otherseek"' in html

    def test_room_search_shows_matching_text_only(self, client, test_user, second_user):
        """In-thread search does not render lines that do not contain the text."""
        client.force_login(test_user)
        chat, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        Message.objects.create(sender=second_user, chat=chat, content="alpha-needle")
        Message.objects.create(sender=test_user, chat=chat, content="unrelated-line")
        html = client.get(
            reverse("chat:room", kwargs={"chat_id": chat.pk}) + "?find=needle"
        ).content.decode()
        assert "alpha-needle" in html
        assert html.count("data-message-id=") == 1
        assert "Clear the search to send a message." in html
