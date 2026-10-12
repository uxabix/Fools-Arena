"""Profile page: identity, resume action, record, and account changes."""

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from fools.models import GamePlayer, LobbyPlayer


@pytest.mark.django_db
class TestProfilePage:
    """The signed-in profile shows one name, a resume action, and a record."""

    def test_profile_shows_username_once_and_empty_record(self, client, test_user):
        """A new player sees initials, no repeated nickname, and no win rate."""
        test_user.email = None
        test_user.save(update_fields=["email"])
        client.force_login(test_user)
        html = client.get(reverse("profile")).content.decode()
        assert f"<h1" in html
        assert test_user.username in html
        assert "Signed in as" not in html
        assert "You haven&#x27;t played yet." in html or "You haven't played yet." in html
        assert 'aria-label="Not available"' in html
        assert "Add an email" in html
        assert "Find a game" in html

    def test_profile_returns_to_lobby(self, client, test_user, basic_lobby):
        """A player who is waiting in a lobby is offered that lobby."""
        LobbyPlayer.objects.create(lobby=basic_lobby, user=test_user, status="waiting")
        client.force_login(test_user)
        html = client.get(reverse("profile")).content.decode()
        assert "Return to lobby" in html
        assert reverse("fools-lobby-detail-page", args=[basic_lobby.id]) in html

    def test_profile_returns_to_game(self, client, test_user, basic_game):
        """An in-progress match is preferred over a lobby link."""
        GamePlayer.objects.create(
            fools=basic_game,
            user=test_user,
            seat_position=1,
            cards_remaining=6,
        )
        client.force_login(test_user)
        html = client.get(reverse("profile")).content.decode()
        assert "Return to game" in html
        assert reverse("fools-play-page", args=[basic_game.id]) in html

    def test_change_email_requires_current_password(self, client, test_user):
        """A wrong password keeps the typed address and does not save it."""
        client.force_login(test_user)
        resp = client.post(reverse("profile"), {
            "action": "email",
            "email": "new-address@example.com",
            "current_password": "not-the-password",
        })
        assert resp.status_code == 200
        assert b"Current password is incorrect." in resp.content
        assert b"new-address@example.com" in resp.content
        test_user.refresh_from_db()
        assert test_user.email != "new-address@example.com"

    def test_change_email(self, client, user_factory):
        """A correct password updates the email."""
        user = user_factory(password="StrongPass123", email="old@example.com")
        client.force_login(user)
        email_resp = client.post(reverse("profile"), {
            "action": "email",
            "email": "fresh@example.com",
            "current_password": "StrongPass123",
        })
        assert email_resp.status_code == 302
        user.refresh_from_db()
        assert user.email == "fresh@example.com"

    def test_password_change_emails_a_reset_link(self, client, user_factory):
        """The profile sends the public reset link and does not change the password yet."""
        user = user_factory(password="StrongPass123", email="player@example.com")
        client.force_login(user)
        page = client.get(reverse("profile"))
        assert b"Send reset link" in page.content
        assert b"Current password" not in page.content.split(b"Change password", 1)[-1]
        sent = client.post(reverse("profile"), {"action": "password"})
        assert sent.status_code == 302
        follow = client.get(sent.url)
        assert b"We sent a link to choose a new password." in follow.content
        user.refresh_from_db()
        assert user.check_password("StrongPass123")
        assert mail.outbox[0].to == ["player@example.com"]
        link = mail.outbox[0].body.split("http://testserver", 1)[1].split()[0]
        confirm = client.get(link, follow=True)
        assert b"Choose a new password" in confirm.content
        saved = client.post(confirm.request["PATH_INFO"], {
            "new_password1": "AnotherStrongPass123",
            "new_password2": "AnotherStrongPass123",
        })
        assert saved.status_code == 302
        user.refresh_from_db()
        assert user.check_password("AnotherStrongPass123")

    def test_password_change_without_email_sends_nothing(self, client, user_factory):
        """An account with no address cannot start a password reset."""
        user = user_factory(password="StrongPass123", email=None)
        client.force_login(user)
        resp = client.post(reverse("profile"), {"action": "password"})
        assert resp.status_code == 200
        assert b"Add an email before changing your password." in resp.content
        assert mail.outbox == []
        user.refresh_from_db()
        assert user.check_password("StrongPass123")

    def test_password_change_uses_the_email_limit(self, client, user_factory):
        """Profile reset mail counts toward the shared email limit."""
        cache.clear()
        user = user_factory(password="StrongPass123", email="limited@example.com")
        client.force_login(user)
        with override_settings(ACCOUNT_EMAIL_RATE_LIMIT=1):
            allowed = client.post(reverse("profile"), {"action": "password"})
            blocked = client.post(reverse("profile"), {"action": "password"})
        assert allowed.status_code == 302
        assert blocked.status_code == 200
        assert b"Too many attempts. Try again later." in blocked.content
        assert len(mail.outbox) == 1
        cache.clear()
