"""Authentication tests for both UI and REST API endpoints.

This module contains test cases for verifying authentication flows in
a Django application that provides both template-based (UI) and
REST API endpoints. Tests cover registration, login, logout, and
profile access behaviors.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestTemplateAuth:
    """Test suite for UI-based authentication using Django templates."""

    def test_register_valid(self, client):
        """Test successful registration through UI.

        Sends valid registration data through a POST request to the 'register' view.
        Ensures that the user is created and redirected to the profile page.

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
        assert resp.url == reverse('profile')
        assert User.objects.filter(username='maksim').exists()

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

    def test_login_valid(self, client, user_factory):
        """Test successful login through UI.

        Verifies that valid credentials redirect the user to the profile page.
        """
        user = user_factory(password="test123")
        resp = client.post(reverse('login'), {
            'username': user.username,
            'password': 'test123',
        })
        assert resp.status_code == 302
        assert resp.url == reverse('profile')

    def test_login_invalid(self, client):
        """Test login with invalid credentials.

        Ensures the response remains on the login page (status 200) and does not redirect.
        """
        resp = client.post(reverse('login'), {
            'username': 'nope',
            'password': 'wrong'
        })
        assert resp.status_code == 200

    def test_profile_requires_authentication(self, client):
        """Test profile page access without authentication.

        Ensures that unauthenticated users are redirected to the login page.
        """
        resp = client.get(reverse('profile'))
        assert resp.status_code == 302
        assert reverse('login') in resp.url

    def test_logout(self, client, user_factory):
        """Test logout functionality through UI.

        Verifies that an authenticated user is logged out and redirected to the login page.
        """
        user = user_factory(password="test123")
        client.post(reverse('login'), {'username': user.username, 'password': 'test123'})
        resp = client.post(reverse('logout'))
        assert resp.status_code == 302
        assert resp.url == reverse('login')


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
        assert User.objects.filter(username='maksim_api').exists()

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
