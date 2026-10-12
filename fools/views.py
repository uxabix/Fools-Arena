"""Thin template views: pages load all state via ``/api/fools/`` from JavaScript."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from fools.models import LobbyPlayer


@login_required
def lobby_list_page(request):
    """Render the public lobby browser and the create-lobby form.

    The list itself is loaded by the page script. The current lobby is
    passed here so a private room, which is absent from that list, can
    still offer a way back in.
    """
    membership = (
        LobbyPlayer.objects.filter(
            user=request.user,
            status__in=["waiting", "ready", "playing"],
        )
        .select_related("lobby")
        .first()
    )
    return render(
        request,
        "fools/lobby_list.html",
        {"current_lobby": membership.lobby if membership else None},
    )


@login_required
def lobby_detail_page(request, lobby_id):
    """Render a single lobby + chat shell; ``lobby_id`` is only in the URL path.

    Args:
        request: Django request (must be authenticated).
        lobby_id: UUID from the route; the template reads the same id client-side.

    Returns:
        HttpResponse: ``lobby_detail.html`` without server-side lobby context.
    """
    return render(request, "fools/lobby_detail.html")


@login_required
def game_play_page(request, game_id):
    """Render the table UI shell for a running ``Game`` id.

    Args:
        request: Authenticated request.
        game_id: UUID string from the URL.

    Returns:
        HttpResponse: ``play.html`` with no game payload embedded server-side.
    """
    return render(request, "fools/play.html")
