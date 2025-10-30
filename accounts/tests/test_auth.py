import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
User = get_user_model()


@pytest.mark.django_db
class TestTemplateAuth:
    """UI-based authentication tests."""

    def test_register_valid(self, client):
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
        resp = client.post(reverse('register'), {
            'username': 'bad',
            'email': 'b@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass124',
        })
        assert resp.status_code == 200
        assert not User.objects.filter(username='bad').exists()

    def test_login_valid(self, client, user_factory):
        user = user_factory(password="test123")
        resp = client.post(reverse('login'), {
            'username': user.username,
            'password': 'test123',
        })
        assert resp.status_code == 302
        assert resp.url == reverse('profile')

    def test_login_invalid(self, client):
        resp = client.post(reverse('login'), {
            'username': 'nope',
            'password': 'wrong'
        })
        assert resp.status_code == 200

    def test_profile_requires_authentication(self, client):
        resp = client.get(reverse('profile'))
        assert resp.status_code == 302
        assert reverse('login') in resp.url

    def test_logout(self, client, user_factory):
        user = user_factory(password="test123")
        client.post(reverse('login'), {'username': user.username, 'password': 'test123'})
        resp = client.post(reverse('logout'))
        assert resp.status_code == 302
        assert resp.url == reverse('login')


@pytest.mark.django_db
class TestAPIAuth:
    """API authentication endpoint tests."""

    def test_api_register_valid(self, api_client):
        register_url = reverse("api_register")
        resp = api_client.post(register_url, {
            'username': 'maksim_api',
            'email': 'mapi@example.com',
            'password': 'StrongPass123',
        }, format='json')
        assert resp.status_code == 201
        assert User.objects.filter(username='maksim_api').exists()

    def test_api_register_invalid(self, api_client):
        register_url = reverse("api_register")
        resp = api_client.post(register_url, {
            'username': '',
            'email': 'bad',
            'password': 'short',
        }, format='json')
        assert resp.status_code == 400

    def test_api_login_valid(self, api_client, user_factory):
        user = user_factory(password="test123")
        url = reverse("api_login")
        resp = api_client.post(url, {
            'username': user.username,
            'password': 'test123'
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['username'] == user.username

    def test_api_login_invalid(self, api_client):
        url = reverse("api_login")
        resp = api_client.post(url, {
            'username': 'nope',
            'password': 'wrong'
        }, format='json')
        assert resp.status_code == 400

    def test_api_profile_authenticated(self, api_client, user_factory):
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
        profile_url = reverse("api_profile")
        resp = api_client.get(profile_url)
        assert resp.status_code == 403

    def test_api_logout(self, api_client, user_factory):
        login_url = reverse("api_login")
        user = user_factory(password="test123")
        api_client.post(login_url, {
            'username': user.username,
            'password': 'test123'
        }, format='json')
        logout_url = reverse("api_logout")
        resp = api_client.post(logout_url)
        assert resp.status_code == 200
