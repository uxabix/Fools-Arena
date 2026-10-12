"""Django settings for automated tests (no Redis dependency).

Extends production settings but swaps the Channels layer for an in-memory
backend so ``pytest`` does not require a running Redis instance.
"""

from Fools_Arena.settings import *  # noqa: F401,F403 pylint:disable=wildcard-import,unused-wildcard-import

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
ACCOUNT_EMAIL_CONFIRMATION_REQUIRED = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "accounts-tests",
    }
}
ACCOUNT_EMAIL_RATE_LIMIT = 1000
