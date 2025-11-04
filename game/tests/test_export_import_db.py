"""Tests for database export/import management commands.

This module contains tests that exercise the `export_db` and `import_db`
Django management commands to ensure data exported to JSON can be imported
back and recreate the expected model instances.
"""

import pytest

from django.core.management import call_command

from game.models import Lobby
from accounts.models import User


@pytest.mark.django_db
def test_export_import_db_creates_objects(user_factory, tmp_path):
    """Verify that exporting the DB to JSON and re-importing recreates objects.

    The test performs the following steps:
    1. Create a test user and a Lobby owned by that user.
    2. Export the database to a temporary JSON file using the ``export_db``
       management command.
    3. Remove the created objects from the database to simulate a fresh import.
    4. Run the ``import_db`` management command to import from the JSON file.
    5. Assert that the Lobby and User objects exist after import.
    """

    user = user_factory(username="player1")
    lobby_name = "TestLobby"
    Lobby.objects.create(owner=user, name=lobby_name)

    # Export to temp file using --output
    tmp_file = tmp_path / "backup.json"
    call_command("export_db", f"--output={str(tmp_file)}")

    # Clear DB (simulate fresh import)
    Lobby.objects.all().delete()
    User.objects.filter(username="player1").delete()

    # Import back
    call_command("import_db", str(tmp_file))

    # Assertions
    assert Lobby.objects.filter(name=lobby_name).exists()
    assert User.objects.filter(username="player1").exists()
