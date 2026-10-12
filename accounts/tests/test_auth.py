"""Authentication tests for both UI and REST API endpoints.

This module contains test cases for verifying authentication flows in
a Django application that provides both template-based (UI) and
REST API endpoints. Tests cover registration, login, logout, and
profile access behaviors.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestTemplateAuth:
    """Test suite for UI-based authentication using Django templates."""

    def test_register_valid(self, client):
        """Test successful registration through UI.

        Sends valid registration data through a POST request to the 'register' view.
        Ensures that the user is created inactive and sent to the check-email page.

        Args:
            client (django.test.Client): Django test client fixture.
        """        
        resp = client.post(reverse('register'), {
            'username': 'maksim',
            'email': 'm@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
        })
        assert resp.status_code == 302
        assert resp.url == reverse('register-done')
        user = User.objects.get(username='maksim')
        assert user.is_active is False
        assert len(mail.outbox) == 1
        assert "confirm-email" in mail.outbox[0].body

    def test_register_invalid_password_mismatch(self, client):
        """Test registration with mismatched passwords.

        Ensures that invalid password confirmation prevents user creation
        and that the registration form is re-rendered with status 200.
        """
        resp = client.post(reverse('register'), {
            'username': 'bad',
            'email': 'b@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass124',
        })
        assert resp.status_code == 200
        assert not User.objects.filter(username='bad').exists()
        body = resp.content.decode()
        assert "Passwords do not match." in body
        assert 'value="bad"' in body
        assert 'value="b@example.com"' in body
        assert 'value="StrongPass123"' in body
        assert 'value="StrongPass124"' in body

    def test_login_valid(self, client, user_factory):
        """Test successful login through UI.

        Verifies that valid credentials redirect the user to the lobby list.
        """
        user = user_factory(password="test123")
        resp = client.post(reverse('login'), {
            'username': user.username,
            'password': 'test123',
        })
        assert resp.status_code == 302
        assert resp.url == reverse('fools-lobby-list-page')

    def test_login_invalid(self, client):
        """Test login with invalid credentials.

        Ensures the response remains on the login page (status 200) and does not redirect.
        """
        resp = client.post(reverse('login'), {
            'username': 'nope',
            'password': 'wrong'
        })
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Incorrect username or password." in body
        assert "Please enter a correct" not in body
        assert "exists" not in body.lower()
        assert "inactive" not in body.lower()
        assert 'value="nope"' in body
        assert 'value="wrong"' in body

    def test_profile_requires_authentication(self, client):
        """Test profile page access without authentication.

        Ensures that unauthenticated users are redirected to the login page.
        """
        resp = client.get(reverse('profile'))
        assert resp.status_code == 302
        assert reverse('login') in resp.url

    def test_profile_cards_use_icons(self, client, test_user):
        """Profile shortcuts are icons, and hover does not restyle them as text."""
        client.force_login(test_user)
        html = client.get(reverse("profile")).content.decode()
        assert "Games &amp; lobbies" not in html
        assert "Messages" in html
        assert "Find a game" in html
        assert "🃏" not in html
        assert "💬" not in html
        assert "Sign out" in html
        assert "<svg" in html

    def test_logout(self, client, user_factory):
        """Test logout functionality through UI.

        Verifies that an authenticated user is logged out and redirected to the login page.
        """
        user = user_factory(password="test123")
        client.post(reverse('login'), {'username': user.username, 'password': 'test123'})
        resp = client.post(reverse('logout'))
        assert resp.status_code == 302
        assert resp.url == reverse('login')

    def test_login_wrong_password_hides_account(self, client, user_factory):
        """A wrong password must not reveal that the account exists."""
        user = user_factory(password="test123")
        resp = client.post(reverse('login'), {
            'username': user.username,
            'password': 'not-the-password',
        })
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Incorrect username or password." in body
        assert "exists" not in body.lower()
        assert "inactive" not in body.lower()
        assert 'value="%s"' % user.username in body
        assert 'value="not-the-password"' in body

    def test_login_inactive_uses_same_message(self, client, user_factory):
        """An inactive account gets the same message as a bad password."""
        user = user_factory(password="test123", is_active=False)
        resp = client.post(reverse('login'), {
            'username': user.username,
            'password': 'test123',
        })
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Incorrect username or password." in body
        assert "inactive" not in body.lower()
        assert "disabled" not in body.lower()

    def test_register_page_shows_rules_and_action(self, client):
        """Registration shows persistent labels, rules, and an action button."""
        resp = client.get(reverse('register'))
        body = resp.content.decode()
        assert "At least 8 characters" in body
        assert "Not only numbers" in body
        assert "Create account" in body
        assert 'placeholder="name@example.com"' in body
        assert "Show password" in body
        password_inputs = [
            tag for tag in body.split("<input")
            if 'type="password"' in tag
        ]
        assert len(password_inputs) == 2
        for tag in password_inputs:
            assert "maxlength" not in tag
            assert "onpaste" not in tag

    def test_register_accepts_long_password(self, client):
        """Passwords longer than 16 characters are allowed, past 128 are not."""
        long_ok = "StrongPass123" + "x" * 20
        assert 16 < len(long_ok) <= 128
        resp = client.post(reverse('register'), {
            'username': 'longpassuser',
            'email': 'longpass@example.com',
            'password1': long_ok,
            'password2': long_ok,
        }, follow=True)
        assert resp.status_code == 200
        assert b"Account created. We sent a confirmation link" in resp.content
        created = User.objects.get(username='longpassuser')
        assert created.is_active is False

        too_long = "StrongPass123" + "y" * 120
        assert len(too_long) > 128
        resp = client.post(reverse('register'), {
            'username': 'toolonguser',
            'email': 'toolong@example.com',
            'password1': too_long,
            'password2': too_long,
        })
        assert resp.status_code == 200
        assert b"Use 128 characters or fewer." in resp.content
        assert not User.objects.filter(username='toolonguser').exists()

    def test_confirm_email_signs_in(self, client):
        """Opening the confirmation link activates the account and signs in."""
        client.post(reverse('register'), {
            'username': 'confirmme',
            'email': 'confirmme@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
        })
        link = mail.outbox[0].body.split("http://testserver", 1)[1].split()[0]
        resp = client.get(link)
        assert resp.status_code == 302
        assert resp.url == reverse('fools-lobby-list-page')
        assert User.objects.get(username='confirmme').is_active is True

    def test_password_reset_hides_whether_the_account_exists(self, client, user_factory):
        """Known and unknown addresses get the same reset response."""
        user = user_factory(password="StrongPass123", email="known@example.com")
        known = client.post(reverse('password-reset'), {'email': user.email})
        unknown = client.post(reverse('password-reset'), {'email': 'missing@example.com'})
        assert known.status_code == unknown.status_code == 302
        assert known.url == unknown.url == reverse('password-reset-done')
        done = client.get(reverse('password-reset-done'))
        body = done.content.decode().lower()
        assert "if an account with that email exists" in body
        assert "does not exist" not in body
        assert len(mail.outbox) == 1
        assert user.email in mail.outbox[0].to
        link = mail.outbox[0].body.split("http://testserver", 1)[1].split()[0]
        confirm = client.get(link, follow=True)
        assert confirm.status_code == 200
        assert b"Choose a new password" in confirm.content
        saved = client.post(confirm.request["PATH_INFO"], {
            "new_password1": "AnotherStrongPass123",
            "new_password2": "AnotherStrongPass123",
        })
        assert saved.status_code == 302
        assert saved.url == reverse("password-reset-complete")
        finished = client.get(saved.url)
        assert b"Password updated" in finished.content
        user.refresh_from_db()
        assert user.check_password("AnotherStrongPass123")

    def test_username_rules(self, client, user_factory):
        """New usernames follow length, character, reserved, and case rules."""
        user_factory(username="player_one", password="StrongPass123")
        cases = {
            "ab": "Use at least 3 characters.",
            "bad name": "Usernames cannot contain spaces.",
            "evil.com": "Usernames cannot contain a web address.",
            "<b>": "Usernames cannot contain HTML.",
            "admin": "This username is reserved.",
            "Ad_min": "This username is reserved.",
            "Player_One": "A user with that username already exists.",
            "ab\u200bc": "Usernames cannot contain invisible or control characters.",
        }
        for username, message in cases.items():
            local = username.replace(" ", "").replace("<", "").replace(">", "")
            resp = client.post(reverse("register"), {
                "username": username,
                "email": local + "@example.com",
                "password1": "StrongPass123",
                "password2": "StrongPass123",
            })
            assert message in resp.content.decode(), username

    def test_confirmation_can_be_skipped_only_for_local_debug(self, client):
        """The skip switch signs the person in, and production must refuse it."""
        from django.test import override_settings

        from accounts.checks import check_email_confirmation_required

        with override_settings(ACCOUNT_EMAIL_CONFIRMATION_REQUIRED=False):
            resp = client.post(reverse("register"), {
                "username": "skiptest",
                "email": "skiptest@example.com",
                "password1": "StrongPass123",
                "password2": "StrongPass123",
            })
        assert resp.status_code == 302
        assert resp.url == reverse("fools-lobby-list-page")
        assert User.objects.get(username="skiptest").is_active is True
        assert mail.outbox == []
        with override_settings(DEBUG=False, ACCOUNT_EMAIL_CONFIRMATION_REQUIRED=False):
            assert check_email_confirmation_required(None)
        with override_settings(DEBUG=True, ACCOUNT_EMAIL_CONFIRMATION_REQUIRED=False):
            assert check_email_confirmation_required(None) == []

    def test_email_requests_are_rate_limited(self, client, user_factory, api_client):
        """Password reset and registration stop after the configured number of tries."""
        from django.core.cache import cache
        from django.test import override_settings

        cache.clear()
        user = user_factory(password="StrongPass123", email="rate@example.com")
        with override_settings(ACCOUNT_EMAIL_RATE_LIMIT=2):
            for _ in range(2):
                allowed = client.post(reverse("password-reset"), {"email": "missing@example.com"})
                assert allowed.status_code == 302
            blocked = client.post(reverse("password-reset"), {"email": user.email})
        assert blocked.status_code == 200
        assert b"Too many attempts. Try again later." in blocked.content
        assert mail.outbox == []
        cache.clear()
        with override_settings(ACCOUNT_EMAIL_RATE_LIMIT=1):
            first = api_client.post(reverse("api_register"), {
                "username": "ratelimituser",
                "email": "ratelimit@example.com",
                "password": "StrongPass123",
            }, format="json")
            second = api_client.post(reverse("api_register"), {
                "username": "ratelimituser2",
                "email": "ratelimit2@example.com",
                "password": "StrongPass123",
            }, format="json")
        assert first.status_code == 201
        assert second.status_code == 429
        assert not User.objects.filter(username="ratelimituser2").exists()
        cache.clear()

    def test_login_page_links_to_password_reset(self, client):
        """The sign-in form offers a password reset next to the password."""
        resp = client.get(reverse('login'))
        assert b"Forgot password?" in resp.content
        assert reverse('password-reset').encode() in resp.content


@pytest.mark.django_db
class TestAPIAuth:
    """Test suite for REST API authentication endpoints."""

    def test_api_register_valid(self, api_client):
        """Test successful API registration.

        Sends valid user data to the registration endpoint and verifies
        that a new user is created with HTTP 201 Created.
        """
        register_url = reverse("api_register")
        resp = api_client.post(register_url, {
            'username': 'maksim_api',
            'email': 'mapi@example.com',
            'password': 'StrongPass123',
        }, format='json')
        assert resp.status_code == 201
        created = User.objects.get(username='maksim_api')
        assert created.is_active is False
        assert len(mail.outbox) == 1
        assert "confirmation link" in resp.data["detail"].lower()

    def test_api_register_invalid(self, api_client):
        """Test API registration with invalid data.

        Ensures that malformed input returns HTTP 400 Bad Request.
        """
        register_url = reverse("api_register")
        resp = api_client.post(register_url, {
            'username': '',
            'email': 'bad',
            'password': 'short',
        }, format='json')
        assert resp.status_code == 400

    def test_api_register_rejects_numeric_password(self, api_client):
        """API registration uses the same password rules as the HTML form."""
        resp = api_client.post(reverse("api_register"), {
            'username': 'digits',
            'email': 'digits@example.com',
            'password': '12345678',
        }, format='json')
        assert resp.status_code == 400
        assert not User.objects.filter(username='digits').exists()

    def test_api_register_rejects_bad_username(self, api_client):
        """API registration uses the same username rules as the HTML form."""
        resp = api_client.post(reverse("api_register"), {
            "username": "admin",
            "email": "admin2@example.com",
            "password": "StrongPass123",
        }, format="json")
        assert resp.status_code == 400
        assert not User.objects.filter(email="admin2@example.com").exists()

    def test_api_login_valid(self, api_client, user_factory):
        """Test successful API login.

        Sends valid credentials to the login endpoint and verifies that
        profile data is returned in the response.
        """
        user = user_factory(password="test123")
        url = reverse("api_login")
        resp = api_client.post(url, {
            'username': user.username,
            'password': 'test123'
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['username'] == user.username

    def test_api_login_invalid(self, api_client):
        """Test API login with invalid credentials.

        Ensures that incorrect credentials return HTTP 400 Bad Request.
        """
        url = reverse("api_login")
        resp = api_client.post(url, {
            'username': 'nope',
            'password': 'wrong'
        }, format='json')
        assert resp.status_code == 400
        assert "Incorrect username or password." in str(resp.data)
        assert "exists" not in str(resp.data).lower()

    def test_api_profile_authenticated(self, api_client, user_factory):
        """Test authenticated API profile access.

        After logging in, verifies that the authenticated user can retrieve
        their own profile data.
        """
        login_url = reverse("api_login")
        user = user_factory(password="test123")
        api_client.post(login_url, {
            'username': user.username,
            'password': 'test123'
        }, format='json')
        profile_url = reverse("api_profile")
        resp = api_client.get(profile_url)
        assert resp.status_code == 200
        assert resp.data['username'] == user.username

    def test_api_profile_unauthenticated(self, api_client):
        """Test unauthenticated API profile access.

        Ensures that accessing the profile endpoint without authentication
        returns HTTP 403 Forbidden.
        """
        profile_url = reverse("api_profile")
        resp = api_client.get(profile_url)
        assert resp.status_code == 403

    def test_api_logout(self, api_client, user_factory):
        """Test API logout.

        Verifies that an authenticated user can log out successfully,
        receiving HTTP 200 OK in response.
        """
        login_url = reverse("api_login")
        user = user_factory(password="test123")
        api_client.post(login_url, {
            'username': user.username,
            'password': 'test123'
        }, format='json')
        logout_url = reverse("api_logout")
        resp = api_client.post(logout_url)
        assert resp.status_code == 200
