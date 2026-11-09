"""Tests for private DM REST endpoints and blocking rules."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models import Block
from chat.models import Chat, Message


@pytest.mark.django_db
class TestPrivateMessagingAPI:
    """End-to-end API tests for direct chats and message posts."""

    def _login(self, api_client, user):
        """Attach a session for the given user."""
        api_client.force_login(user)

    def test_direct_chat_create_and_idempotent(
        self, api_client, test_user, second_user
    ):
        """POST /chats/direct/ returns one chat; repeat returns the same id."""
        self._login(api_client, test_user)
        url = reverse("chat-direct-create")
        r1 = api_client.post(
            url,
            {"other_user_id": str(second_user.pk)},
            format="json",
        )
        assert r1.status_code in (200, 201)
        chat_id = r1.data["id"]
        r2 = api_client.post(
            url,
            {"other_user_id": str(second_user.pk)},
            format="json",
        )
        assert r2.status_code in (200, 201)
        assert r2.data["id"] == chat_id
        assert Chat.objects.filter(dm_pair_key__isnull=False).count() == 1

    def test_direct_chat_self_rejected(self, api_client, test_user):
        """Cannot open a DM with yourself."""
        self._login(api_client, test_user)
        url = reverse("chat-direct-create")
        r = api_client.post(
            url,
            {"other_user_id": str(test_user.pk)},
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_post_message_in_dm(self, api_client, test_user, second_user):
        """Messages persist and appear in list for both participants."""
        self._login(api_client, test_user)
        durl = reverse("chat-direct-create")
        r = api_client.post(
            durl,
            {"other_user_id": str(second_user.pk)},
            format="json",
        )
        chat_id = r.data["id"]
        murl = reverse("chat-messages", kwargs={"chat_id": chat_id})
        pr = api_client.post(murl, {"content": "  hello  "}, format="json")
        assert pr.status_code == status.HTTP_201_CREATED
        self._login(api_client, second_user)
        gr = api_client.get(murl)
        assert gr.status_code == status.HTTP_200_OK
        assert any(m["content"] == "hello" for m in gr.data)
        found = api_client.get(murl, {"q": "hello", "envelope": "1"})
        assert found.status_code == status.HTTP_200_OK
        assert [row["content"] for row in found.data["results"]] == ["hello"]

    def test_blocked_user_cannot_post_dm(
        self, api_client, test_user, second_user
    ):
        """If second_user blocks test_user, test_user cannot post in the DM."""
        self._login(api_client, test_user)
        durl = reverse("chat-direct-create")
        r = api_client.post(
            durl,
            {"other_user_id": str(second_user.pk)},
            format="json",
        )
        chat_id = r.data["id"]
        murl = reverse("chat-messages", kwargs={"chat_id": chat_id})
        Block.objects.create(blocker=second_user, blocked=test_user)
        pr = api_client.post(murl, {"content": "nope"}, format="json")
        assert pr.status_code == status.HTTP_403_FORBIDDEN
        assert Message.objects.filter(chat_id=chat_id, content="nope").count() == 0

    def test_lobby_message_ignores_block(
        self, api_client, test_user, second_user, basic_lobby
    ):
        """Pairwise blocks do not block lobby channel messages (API layer)."""
        lobby_chat = Chat.objects.create(
            name="Lobby",
            is_lobby=True,
            is_group=True,
            lobby=basic_lobby,
        )
        lobby_chat.add_participant(test_user)
        lobby_chat.add_participant(second_user)
        Block.objects.create(blocker=second_user, blocked=test_user)
        self._login(api_client, test_user)
        murl = reverse("chat-messages", kwargs={"chat_id": str(lobby_chat.pk)})
        pr = api_client.post(murl, {"content": "lobby ok"}, format="json")
        assert pr.status_code == status.HTTP_201_CREATED
        assert Message.objects.filter(chat=lobby_chat, content="lobby ok").exists()

    def test_non_participant_cannot_post(self, api_client, test_user, user_factory):
        """User who is not in the chat gets 403 from membership check."""
        outsider = user_factory(username="outsider99")
        chat = Chat.objects.create(name="G", is_group=True)
        chat.add_participant(test_user)
        self._login(api_client, outsider)
        murl = reverse("chat-messages", kwargs={"chat_id": str(chat.pk)})
        pr = api_client.post(murl, {"content": "x"}, format="json")
        assert pr.status_code == status.HTTP_403_FORBIDDEN

    def test_message_pages_and_read_mark(self, api_client, test_user, second_user):
        """Older pages walk backward, and reading the newest line clears unread."""
        self._login(api_client, test_user)
        chat, _ = Chat.objects.get_or_create_direct(test_user, second_user)
        first = Message.objects.create(sender=second_user, chat=chat, content="one")
        second = Message.objects.create(sender=second_user, chat=chat, content="two")
        third = Message.objects.create(sender=test_user, chat=chat, content="three")
        Message.objects.filter(pk=first.pk).update(sent_at=timezone.now() - timedelta(minutes=3))
        Message.objects.filter(pk=second.pk).update(sent_at=timezone.now() - timedelta(minutes=2))
        Message.objects.filter(pk=third.pk).update(sent_at=timezone.now() - timedelta(minutes=1))
        murl = reverse("chat-messages", kwargs={"chat_id": chat.pk})
        page = api_client.get(murl, {"limit": 2, "envelope": "1"})
        assert page.status_code == status.HTTP_200_OK
        assert page.data["has_older"] is True
        assert [row["content"] for row in page.data["results"]] == ["two", "three"]
        older = api_client.get(
            murl,
            {"limit": 2, "envelope": "1", "before": page.data["results"][0]["id"]},
        )
        assert [row["content"] for row in older.data["results"]] == ["one"]
        assert older.data["has_older"] is False
        listed = api_client.get(reverse("chat-list"))
        row = next(item for item in listed.data if item["id"] == str(chat.pk))
        assert row["unread_count"] == 2
        assert row["last_message"]["content"] == "three"
        read = api_client.post(
            reverse("chat-read", kwargs={"chat_id": chat.pk}),
            {"message_id": str(third.pk)},
            format="json",
        )
        assert read.status_code == status.HTTP_200_OK
        listed = api_client.get(reverse("chat-list"))
        row = next(item for item in listed.data if item["id"] == str(chat.pk))
        assert row["unread_count"] == 0

    def test_user_search_is_a_short_prefix(self, api_client, test_user, user_factory):
        """Suggestions need two characters and skip bots and the caller."""
        self._login(api_client, test_user)
        user_factory(username="AlphaOne")
        user_factory(username="Alphabot", is_bot=True)
        url = reverse("chat-user-search")
        short = api_client.get(url, {"q": "a"})
        assert short.status_code == status.HTTP_400_BAD_REQUEST
        found = api_client.get(url, {"q": "alp"})
        assert found.status_code == status.HTTP_200_OK
        names = [row["username"] for row in found.data["results"]]
        assert names == ["AlphaOne"]
        assert "email" not in found.data["results"][0]
