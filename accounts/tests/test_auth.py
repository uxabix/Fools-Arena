from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient


class TemplateAuthTests(TestCase):
    """UI-based authentication tests."""

    def test_register_valid(self):
        """User can register with valid data."""
        resp = self.client.post(reverse('register'), {
            'username': 'maksim',
            'email': 'm@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
        })
        self.assertRedirects(resp, reverse('profile'))
        self.assertTrue(User.objects.filter(username='maksim').exists())

    def test_register_invalid_password_mismatch(self):
        """Registration fails when passwords do not match."""
        resp = self.client.post(reverse('register'), {
            'username': 'bad',
            'email': 'b@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass124',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username='bad').exists())

    def test_login_valid(self):
        """User can log in with correct credentials."""
        User.objects.create_user('u', 'u@example.com', 'p@55word!')
        resp = self.client.post(reverse('login'), {
            'username': 'u',
            'password': 'p@55word!'
        })
        self.assertRedirects(resp, reverse('profile'))

    def test_login_invalid(self):
        """Login fails with invalid credentials."""
        resp = self.client.post(reverse('login'), {
            'username': 'nope',
            'password': 'wrong'
        })
        self.assertEqual(resp.status_code, 200)

    def test_profile_requires_authentication(self):
        """Profile page redirects unauthenticated users to login."""
        resp = self.client.get(reverse('profile'))
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_logout(self):
        """User can log out and is redirected to login page."""
        User.objects.create_user('u', 'u@example.com', 'p@55word!')
        self.client.post(reverse('login'), {'username': 'u', 'password': 'p@55word!'})
        resp = self.client.post(reverse('logout'))
        self.assertRedirects(resp, reverse('login'))


class APIAuthTests(TestCase):
    """API authentication endpoint tests."""

    def setUp(self):
        """Initialize API client before each test."""
        self.client = APIClient()

    def test_api_register_valid(self):
        """API: register user with valid data."""
        resp = self.client.post('/api/auth/register/', {
            'username': 'maksim_api',
            'email': 'mapi@example.com',
            'password': 'StrongPass123',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(User.objects.filter(username='maksim_api').exists())

    def test_api_register_invalid(self):
        """API: registration fails with invalid data."""
        resp = self.client.post('/api/auth/register/', {
            'username': '',
            'email': 'bad',
            'password': 'short',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_api_login_valid(self):
        """API: user can log in with correct credentials."""
        User.objects.create_user('uapi', 'uapi@example.com', 'p@55word!')
        resp = self.client.post('/api/auth/login/', {
            'username': 'uapi',
            'password': 'p@55word!'
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'uapi')

    def test_api_login_invalid(self):
        """API: login fails with invalid credentials."""
        resp = self.client.post('/api/auth/login/', {
            'username': 'nope',
            'password': 'wrong'
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_api_profile_authenticated(self):
        """API: authenticated user can access their profile."""
        User.objects.create_user('uapi', 'uapi@example.com', 'p@55word!')
        self.client.post('/api/auth/login/', {
            'username': 'uapi',
            'password': 'p@55word!'
        }, format='json')
        resp = self.client.get('/api/auth/profile/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'uapi')

    def test_api_profile_unauthenticated(self):
        """API: unauthenticated user cannot access profile."""
        resp = self.client.get('/api/auth/profile/')
        self.assertEqual(resp.status_code, 403)

    def test_api_logout(self):
        """API: user can log out successfully."""
        User.objects.create_user('uapi', 'uapi@example.com', 'p@55word!')
        self.client.post('/api/auth/login/', {
            'username': 'uapi',
            'password': 'p@55word!'
        }, format='json')
        resp = self.client.post('/api/auth/logout/')
        self.assertEqual(resp.status_code, 200)
