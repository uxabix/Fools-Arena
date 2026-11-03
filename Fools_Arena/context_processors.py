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
        "asset_lobby_detail_js_v": _mtime(
            static_root / "fools" / "static" / "fools" / "js" / "lobby_detail.js"
        ),
        "asset_chat_thread_js_v": _mtime(
            static_root / "fools" / "static" / "fools" / "js" / "chat_thread.js"
        ),
        "asset_chat_room_js_v": _mtime(
            static_root / "chat" / "static" / "chat" / "js" / "room.js"
        ),
        "asset_chat_start_js_v": _mtime(
            static_root / "chat" / "static" / "chat" / "js" / "start_direct.js"
        ),
    }


def chat_unread(request):
    """Expose the signed-in user's unread chat total for navigation."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"chat_unread_count": 0, "chat_unread_label": ""}
    from chat.services import unread_badge_label, unread_message_count

    count = unread_message_count(user)
    return {
        "chat_unread_count": count,
        "chat_unread_label": unread_badge_label(count),
    }
