"""Limits how often account emails can be requested.

Registration, confirmation resend, password reset, and a password change started from the profile share one window.
The same response is used whether or not an account exists, so the limit
does not reveal who is registered.
"""

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

TOO_MANY_EMAIL_REQUESTS = "Too many attempts. Try again later."


def client_ip(request):
    """Return the direct client address.

    ``X-Forwarded-For`` is ignored. A proxy can spoof that header, and
    trusting it would let a caller reset someone else's quota.

    Args:
        request: HTTP request.

    Returns:
        str: ``REMOTE_ADDR``, or ``unknown`` when it is missing.
    """
    return (request.META.get("REMOTE_ADDR") or "unknown")[:64]


def email_request_blocked(request, email):
    """Count this attempt and report whether it is over the limit.

    The client IP is always counted. A non-empty address is counted too.
    The attempt is recorded only when it is still allowed, so a blocked
    caller does not keep extending the window.

    Args:
        request: HTTP request.
        email (str): Normalized address, or an empty string.

    Returns:
        bool: True when the IP or the address is already at the limit.
    """
    limit = int(settings.ACCOUNT_EMAIL_RATE_LIMIT)
    window = int(settings.ACCOUNT_EMAIL_RATE_WINDOW)
    address = (email or "").strip().lower()
    ip_key = f"acct-email:ip:{client_ip(request)}"
    address_key = f"acct-email:addr:{address}" if address else ""
    try:
        ip_count = cache.get(ip_key, 0) or 0
        address_count = cache.get(address_key, 0) or 0 if address_key else 0
    except Exception:
        logger.warning("Account email rate limit cache is unavailable")
        return False
    if ip_count >= limit or address_count >= limit:
        logger.info("Account email request blocked for ip=%s", client_ip(request))
        return True
    _record(ip_key, window)
    if address_key:
        _record(address_key, window)
    return False


def _record(key, window):
    """Increment ``key``, starting a new window when it is missing."""
    try:
        if cache.add(key, 1, timeout=window):
            return
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
    except Exception:
        logger.warning("Account email rate limit cache is unavailable")
