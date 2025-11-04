"""
Tests for accounts.generate_test_users management command.

This module exercises the `generate_test_users` management command by:
- creating a set of test users with a given prefix and marker group,
- asserting the expected count changes,
- verifying that deletion via the same command removes the created users,
- and checking conflict/force behavior and group membership.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
import pytest

User = get_user_model()


@pytest.mark.django_db
def test_generate_test_users_creates_and_adds_group(user_factory):
    """Create a small batch of test users and verify they are added to a group.

    The test records the baseline set of users with the given prefix, runs the
    command to create `test_users_count` users, asserts the user count grew by
    that amount, and then deletes those users using the command's `--delete`
    flag and verifies cleanup.
    """

    # Configuration for this test (easy to change in one place)
    test_users_count = 3
    prefix = "test_"
    marker_group = "Test_Users"

    # Baseline
    before = list(User.objects.filter(username__startswith=prefix).order_by("id"))

    # Create test users
    call_command(
        "generate_test_users",
        "--count",
        str(test_users_count),
        "--prefix",
        prefix,
        "--start",
        "1",
        "--marker-group",
        marker_group,
    )

    after = list(User.objects.filter(username__startswith=prefix).order_by("id"))
    assert len(after) >= len(before) + test_users_count

    # Ensure marker group exists and some of the created users are in it
    group = Group.objects.filter(name=marker_group).first()
    assert group is not None, "Expected the marker group to be created"
    assert group.user_set.filter(username__startswith=prefix).exists()

    # Clean up via the same command (non-interactive)
    call_command("generate_test_users", "--delete", "--marker-group", marker_group, "--noinput")

    remaining = list(User.objects.filter(username__startswith=prefix).order_by("id"))
    # After deletion, remaining should be <= before
    assert len(remaining) <= len(before)


@pytest.mark.django_db
def test_generate_test_users_force_and_conflict(user_factory):
    """Test behavior when existing usernames conflict with the generated prefix.

    The test creates an existing user whose username would conflict with the
    generated users' prefix, then runs the command with `--force` and asserts
    that at least one user with that prefix exists and that the marker group
    contains at least one such user (i.e. the command created or assigned a
    user to the group).
    """

    prefix = "conflictuser"
    marker_group = "Test_Users"

    # Create a user that would share the prefix
    u = user_factory(username=prefix)

    before_count = User.objects.filter(username__startswith=prefix).count()

    # Create with same prefix and start so a conflict may occur, pass --force
    call_command(
        "generate_test_users",
        "--count",
        "1",
        "--prefix",
        prefix,
        "--start",
        "1",
        "--force",
        "--marker-group",
        marker_group,
    )

    after_count = User.objects.filter(username__startswith=prefix).count()
    # Ensure count did not decrease and (ideally) increased by at least 1
    assert after_count > before_count

    # Ensure marker group exists and contains at least one user with the prefix
    group = Group.objects.filter(name=marker_group).first()
    assert group is not None, "Expected the marker group to be created"
    assert group.user_set.filter(username__startswith=prefix).exists()
