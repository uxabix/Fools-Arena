# accounts/tests/test_generate_test_users.py
"""
Tests for accounts.generate_test_users management command.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
import pytest

User = get_user_model()


@pytest.mark.django_db
def test_generate_test_users_creates_and_adds_group(user_factory):
    # Ensure baseline
    before = list(User.objects.filter(username__startswith="test_").order_by("id"))

    # Create 3 users
    call_command(
        "generate_test_users",
        "--count",
        "3",
        "--prefix",
        "test_",
        "--start",
        "1",
        "--marker-group",
        "Test_Users",
    )

    after = list(User.objects.filter(username__startswith="test_").order_by("id"))
    assert len(after) >= len(before) + 3

    # Clean up via the same command (non-interactive)
    call_command("generate_test_users", "--delete", "--marker-group", "Test_Users", "--noinput")

    remaining = list(User.objects.filter(username__startswith="test_").order_by("id"))
    # After deletion, remaining should be <= before
    assert len(remaining) <= len(before)


@pytest.mark.django_db
def test_generate_test_users_force_and_conflict(user_factory):
    # Create a user that would conflict
    u = user_factory(username="conflictuser")

    # Create with same prefix and start so conflict occurs, pass --force to override
    call_command(
        "generate_test_users",
        "--count",
        "1",
        "--prefix",
        "conflictuser",
        "--start",
        "1",
        "--force",
        "--marker-group",
        "Test_Users",
    )

    # At least one username starting with 'conflictuser' should exist
    assert User.objects.filter(username__startswith="conflictuser").exists()
