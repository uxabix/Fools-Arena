import pytest
from django.core.management import call_command
from game.models import Lobby
from accounts.models import User

@pytest.mark.django_db
def test_export_import_db_creates_objects(user_factory, tmp_path):
    user = user_factory(username="player1")
    lobby_name = "TestLobby"
    Lobby.objects.create(owner=user, name=lobby_name)

    # Export to temp file using --output
    tmp_file = tmp_path / "backup.json"
    call_command("export_db", f"--output={tmp_file}")

    # Clear DB (simulate fresh import)
    Lobby.objects.all().delete()
    User.objects.filter(username="player1").delete()

    # Import back
    call_command("import_db", str(tmp_file))

    # Assertions
    assert Lobby.objects.filter(name=lobby_name).exists()
    assert User.objects.filter(username="player1").exists()
