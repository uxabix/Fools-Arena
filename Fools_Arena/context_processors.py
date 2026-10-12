"""Template context helpers for the project."""

from django.conf import settings


def _mtime(path):
    """Return a file's mtime as an int, or 0 when the file is missing."""
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return 0


def asset_versions(_request):
    """Expose file mtimes so static URLs can bust browser cache after CSS/JS edits."""
    static_root = settings.BASE_DIR
    return {
        "asset_css_v": _mtime(static_root / "fools" / "static" / "fools" / "css" / "fools.css"),
        "asset_js_v": _mtime(static_root / "fools" / "static" / "fools" / "js" / "play_table.js"),
        "asset_auth_js_v": _mtime(
            static_root / "accounts" / "static" / "accounts" / "js" / "auth_form.js"
        ),
        "asset_lobby_js_v": _mtime(
            static_root / "fools" / "static" / "fools" / "js" / "lobby_list.js"
        ),
    }
