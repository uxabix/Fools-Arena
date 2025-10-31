import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestTemplateAuth:
    """UI-based authentication tests."""

    def test_register_valid(self, client):
        # Valid registration should redirect to profile and create a user
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
        # Registration with mismatched passwords should fail and not create a user
        resp = client.post(reverse('register'), {
            'username': 'bad',
            'email': 'b@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass124',
        })
        assert resp.status_code == 200
        assert not User.objects.filter(username='bad').exists()

    def test_login_valid(self, client, user_factory):
        # Valid login should redirect to profile
        user = user_factory(password="test123")
        resp = client.post(reverse('login'), {
            'username': user.username,
            'password': 'test123',
        })
        assert resp.status_code == 302
        assert resp.url == reverse('profile')

    def test_login_invalid(self, client):
        # Invalid login should return the login page with no redirect
        resp = client.post(reverse('login'), {
            'username': 'nope',
            'password': 'wrong'
        })
        assert resp.status_code == 200

    def test_profile_requires_authentication(self, client):
        # Accessing profile without login should redirect to login page
        resp = client.get(reverse('profile'))
        assert resp.status_code == 302
        assert reverse('login') in resp.url

    def test_logout(self, client, user_factory):
        # Logged-in user should be logged out and redirected to login
        user = user_factory(password="test123")
        client.post(reverse('login'), {'username': user.username, 'password': 'test123'})
        resp = client.post(reverse('logout'))
        assert resp.status_code == 302
        assert resp.url == reverse('login')


@pytest.mark.django_db
class TestAPIAuth:
    """API authentication endpoint tests."""

    def test_api_register_valid(self, api_client):
        # Valid API registration should return 201 and create a user
        register_url = reverse("api_register")
        resp = api_client.post(register_url, {
            'username': 'maksim_api',
            'email': 'mapi@example.com',
            'password': 'StrongPass123',
        }, format='json')
        assert resp.status_code == 201
        assert User.objects.filter(username='maksim_api').exists()

    def test_api_register_invalid(self, api_client):
        # Invalid API registration should return 400
        register_url = reverse("api_register")
        resp = api_client.post(register_url, {
            'username': '',
            'email': 'bad',
            'password': 'short',
        }, format='json')
        assert resp.status_code == 400

    def test_api_login_valid(self, api_client, user_factory):
        # Valid API login should return profile data
        user = user_factory(password="test123")
        url = reverse("api_login")
        resp = api_client.post(url, {
            'username': user.username,
            'password': 'test123'
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['username'] == user.username

    def test_api_login_invalid(self, api_client):
        # Invalid API login should return 400
        url = reverse("api_login")
        resp = api_client.post(url, {
            'username': 'nope',
            'password': 'wrong'
        }, format='json')
        assert resp.status_code == 400

    def test_api_profile_authenticated(self, api_client, user_factory):
        # Authenticated user should receive profile data
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
        # Unauthenticated request to profile should return 403
        profile_url = reverse("api_profile")
        resp = api_client.get(profile_url)
        assert resp.status_code == 403

    def test_api_logout(self, api_client, user_factory):
        # Authenticated user should be able to log out successfully
        login_url = reverse("api_login")
        user = user_factory(password="test123")
        api_client.post(login_url, {
            'username': user.username,
            'password': 'test123'
        }, format='json')
        logout_url = reverse("api_logout")
        resp = api_client.post(logout_url)
        assert resp.status_code == 200
