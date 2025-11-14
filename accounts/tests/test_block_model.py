"""Pytest test suite for the Block model in the Durak card game application.

This module contains unit tests for the accounts.models.Block model,
which represents unilateral user blocking relationships. The tests
cover creation, uniqueness constraints, string representation,
cascade deletions, and multiple block scenarios.
"""
import pytest
from django.db import IntegrityError, transaction

from accounts.models import Block


@pytest.mark.django_db
def test_create_block(test_user, second_user):
    """Test that a Block instance can be created successfully."""
    block = Block.objects.create(blocker=test_user, blocked=second_user)

    assert block.blocker == test_user
    assert block.blocked == second_user
    assert Block.objects.count() == 1


@pytest.mark.django_db
def test_block_unique_constraint(test_user, second_user):
    """Test that duplicate blocker-blocked pairs are not allowed."""
    Block.objects.create(blocker=test_user, blocked=second_user)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Block.objects.create(blocker=test_user, blocked=second_user)

    assert Block.objects.count() == 1


@pytest.mark.django_db
def test_block_str_representation(test_user, second_user):
    """Test __str__ returns a human-readable representation."""
    block = Block.objects.create(blocker=test_user, blocked=second_user)

    expected = f"{test_user} blocked {second_user}"
    assert str(block) == expected


@pytest.mark.django_db
def test_delete_blocker_cascades(test_user, second_user):
    """Test that deleting the blocker deletes related Block rows."""
    Block.objects.create(blocker=test_user, blocked=second_user)

    test_user.delete()

    assert Block.objects.count() == 0


@pytest.mark.django_db
def test_delete_blocked_cascades(test_user, second_user):
    """Test that deleting the blocked user deletes related Block rows."""
    Block.objects.create(blocker=test_user, blocked=second_user)

    second_user.delete()

    assert Block.objects.count() == 0


@pytest.mark.django_db
def test_block_multiple_users(user_factory):
    """Test blocking works across many dynamically created users."""
    u1 = user_factory(username="alpha")
    u2 = user_factory(username="beta")
    u3 = user_factory(username="gamma")

    Block.objects.create(blocker=u1, blocked=u2)
    Block.objects.create(blocker=u1, blocked=u3)
    Block.objects.create(blocker=u2, blocked=u3)

    assert Block.objects.count() == 3
