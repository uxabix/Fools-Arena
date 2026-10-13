"""Seat reusable bot accounts into empty lobby chairs.

Bots are ordinary users with ``is_bot`` set and no password, so they can
sit at a table but cannot sign in. A bot already in another lobby or
match is left alone.
"""

from django.contrib.auth import get_user_model

from fools.models import GamePlayer, Lobby, LobbyPlayer

User = get_user_model()

BOT_POOL = 8


def ensure_bot_pool():
    """Create ``Bot_1`` … ``Bot_8`` when they do not exist yet.

    Returns:
        List of bot users in username order.
    """
    bots = []
    for index in range(1, BOT_POOL + 1):
        username = f"Bot_{index}"
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User(username=username, email=None, is_bot=True, is_active=True)
            user.set_unusable_password()
            user.save()
        elif not user.is_bot:
            continue
        bots.append(user)
    return bots


def fill_empty_seats(lobby: Lobby):
    """Mark bots ready until the lobby reaches ``max_players``.

    Args:
        lobby: Waiting lobby whose empty chairs should be filled.

    Returns:
        How many bots were seated.
    """
    settings = lobby.settings
    active = list(lobby.players.exclude(status="left").select_related("user"))
    missing = settings.max_players - len(active)
    if missing <= 0:
        return 0
    taken = {row.user_id for row in active}
    busy = set(
        GamePlayer.objects.filter(fools__status="in_progress").values_list(
            "user_id", flat=True
        )
    )
    seated_elsewhere = set(
        LobbyPlayer.objects.exclude(status="left")
        .exclude(lobby=lobby)
        .values_list("user_id", flat=True)
    )
    added = 0
    for bot in ensure_bot_pool():
        if added >= missing:
            break
        if bot.id in taken or bot.id in busy or bot.id in seated_elsewhere:
            continue
        LobbyPlayer.objects.create(lobby=lobby, user=bot, status="ready")
        added += 1
    return added
