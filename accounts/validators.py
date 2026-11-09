"""Username rules shared by the registration form, the API, and the user model.

New accounts must use a short ASCII name. Accounts that already exist keep
their current names; sign-in does not re-check these rules.
"""

import re
import unicodedata

from django.core.exceptions import ValidationError

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30

# Exact names, compared without case or underscores, so "Ad_min" is blocked.
RESERVED_USERNAMES = frozenset(
    {
        "admin",
        "administrator",
        "system",
        "support",
        "help",
        "root",
        "moderator",
        "mod",
        "staff",
        "security",
        "official",
        "owner",
        "superuser",
        "null",
        "undefined",
        "api",
        "www",
        "mail",
        "email",
        "webmaster",
        "hostmaster",
        "postmaster",
        "abuse",
        "noreply",
        "foolsarena",
        "fools",
        "arena",
    }
)

_ALLOWED_RE = re.compile(r"^[A-Za-z0-9_]+\Z")
_HTML_RE = re.compile(r"[<>&\"'`]")
_URL_RE = re.compile(
    r"(https?:)|(www\.)|([A-Za-z0-9-]+\.[A-Za-z]{2,})|[/\\@]",
    re.IGNORECASE,
)


def is_reserved_username(username):
    """Return whether ``username`` matches a reserved word.

    Comparison ignores case and underscores, so ``Ad_min`` is reserved
    because it collapses to ``admin``.

    Args:
        username (str): Candidate name.

    Returns:
        bool: True when the name must not be given to a new account.
    """
    folded = (username or "").casefold()
    squashed = folded.replace("_", "")
    return folded in RESERVED_USERNAMES or squashed in RESERVED_USERNAMES


def validate_username_format(value):
    """Reject usernames that are unsafe or outside the allowed shape.

    Allowed characters are ASCII letters, digits, and underscore.
    Spaces, control characters, HTML, and web addresses are rejected
    with their own messages so the person knows what to change.

    Args:
        value (str): Username as submitted, including any spaces.

    Raises:
        ValidationError: When the value breaks a username rule.
    """
    if value in (None, ""):
        return
    if any(ch.isspace() or unicodedata.category(ch).startswith("Z") for ch in value):
        raise ValidationError("Usernames cannot contain spaces.")
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise ValidationError(
            "Usernames cannot contain invisible or control characters."
        )
    if _HTML_RE.search(value):
        raise ValidationError("Usernames cannot contain HTML.")
    if _URL_RE.search(value):
        raise ValidationError("Usernames cannot contain a web address.")
    if not _ALLOWED_RE.match(value):
        raise ValidationError("Use only letters, numbers, and underscore.")
    if len(value) < USERNAME_MIN_LENGTH:
        raise ValidationError(
            "Use at least %d characters." % USERNAME_MIN_LENGTH
        )
