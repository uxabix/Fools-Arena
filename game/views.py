"""Thin template views: pages load all state via ``/api/game/`` from JavaScript."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def lobby_list_page(request):
    """Render the public lobby browser shell (data via fetch)."""
    return render(request, "game/lobby_list.html")


@login_required
def lobby_detail_page(request, lobby_id):
    """Render a single lobby + chat shell; ``lobby_id`` is only in the URL path.

    Args:
        request: Django request (must be authenticated).
        lobby_id: UUID from the route; the template reads the same id client-side.

    Returns:
        HttpResponse: ``lobby_detail.html`` without server-side lobby context.
    """
    return render(request, "game/lobby_detail.html")


@login_required
def game_play_page(request, game_id):
    """Render the table UI shell for a running ``Game`` id.

    Args:
        request: Authenticated request.
        game_id: UUID string from the URL.

    Returns:
        HttpResponse: ``play.html`` with no game payload embedded server-side.
    """
    return render(request, "game/play.html")
