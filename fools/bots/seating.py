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


def _seat_bot(lobby: Lobby, bot):
    """Put ``bot`` in ``lobby`` as ready, reactivating a previous seat.

    Args:
        lobby: Lobby receiving the bot.
        bot: Bot user.
    """
    existing = LobbyPlayer.objects.filter(lobby=lobby, user=bot).first()
    if existing is None:
        LobbyPlayer.objects.create(lobby=lobby, user=bot, status="ready")
        return
    existing.status = "ready"
    existing.save(update_fields=["status"])


def _new_bot():
    """Create the next ``Bot_N`` account.

    Returns:
        The new bot user.
    """
    number = User.objects.filter(is_bot=True).count() + 1
    while User.objects.filter(username=f"Bot_{number}").exists():
        number += 1
    user = User(username=f"Bot_{number}", email=None, is_bot=True, is_active=True)
    user.set_unusable_password()
    user.save()
    return user


def fill_empty_seats(lobby: Lobby):
    """Mark bots ready until the lobby reaches ``max_players``.

    Lobbies that only bots are sitting in are closed first, so those
    accounts can be seated again. If every existing bot is at a table
    with a human, a new bot account is created.

    Args:
        lobby: Waiting lobby whose empty chairs should be filled.

    Returns:
        How many bots were seated.
    """
    from fools.services import close_abandoned_bot_lobbies

    close_abandoned_bot_lobbies()
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
    candidates = list(ensure_bot_pool())
    while added < missing:
        bot = None
        for candidate in candidates:
            if candidate.id in taken or candidate.id in busy or candidate.id in seated_elsewhere:
                continue
            bot = candidate
            break
        if bot is None:
            bot = _new_bot()
            candidates.append(bot)
        _seat_bot(lobby, bot)
        taken.add(bot.id)
        added += 1
    return added
