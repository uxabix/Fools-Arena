"""Pytest fixtures for game API and service tests."""

import pytest
from django.core.management import call_command


@pytest.fixture
def durak_deck_36(db):
    """Ensure a standard 36-card deck exists in the database (idempotent).

    Returns:
        None: Modifies the database in place.
    """
    call_command("init_game_data", deck_size=36)
