"""Tests for the User model in the accounts app."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Test suite for the User model."""

    def test_user_creation(self, test_user):
        """Tests that User instances are created correctly."""
        assert test_user.username == "player1"
        assert test_user.email == "player1@example.com"
        assert test_user.check_password("test123")

    def test_user_uuid_generation(self, test_user):
        """Tests that UUID is automatically generated for users."""
        assert test_user.id is not None
        assert len(str(test_user.id)) == 36

    def test_user_str_representation(self, test_user):
        """Tests string representation of User."""
        assert str(test_user) == "player1"

    def test_user_created_at_auto_generation(self, test_user):
        """Tests that created_at timestamp is automatically set."""
        assert test_user.created_at is not None

    def test_get_full_display_name_with_full_name(self, test_user):
        """Tests get_full_display_name() returns full name when available."""
        test_user.first_name = "John"
        test_user.last_name = "Doe"
        test_user.save()
        assert test_user.get_full_display_name() == "John Doe"

    def test_get_full_display_name_without_full_name(self, test_user):
        """Tests get_full_display_name() falls back to username."""
        assert test_user.get_full_display_name() == "player1"

    def test_has_avatar_true(self, user_factory):
        """Tests has_avatar() returns True when avatar is set."""
        user_with_avatar = user_factory(
            username="avataruser",
            avatar_url="https://example.com/avatar.jpg"
        )
        assert user_with_avatar.has_avatar() is True

    def test_has_avatar_false(self, test_user):
        """Tests has_avatar() returns False when avatar is not set."""
        assert test_user.has_avatar() is False

    def test_user_ordering(self, user_factory):
        """Tests that users are ordered by username."""
        user_factory(username="zzz")
        user_factory(username="aaa")
        users = list(User.objects.all())
        assert users[0].username == "aaa"
        assert users[-1].username == "zzz"

    def test_create_superuser(self):
        """Tests creating a superuser."""
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin123"
        )
        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_password_hashing(self, test_user):
        """Tests that passwords are properly hashed."""
        assert test_user.password != "test123"
        assert test_user.check_password("test123")
        assert not test_user.check_password("wrongpassword")

    def test_authentication_fields(self, test_user):
        """Tests that inherited authentication fields work correctly."""
        assert test_user.is_active is True
        assert test_user.is_staff is False
        assert test_user.is_superuser is False
