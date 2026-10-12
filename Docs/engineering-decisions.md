# Engineering decisions

Record important behavior here when it changes: limits, privacy, account rules, and how the game decides what a player is allowed to do. Write in English. Keep each note short enough that the next change can update it in the same commit.

## Account email

New accounts stay inactive until the person opens the confirmation link. Sign-in does not say whether the username exists, the password is wrong, or the account is still inactive. The message is always "Incorrect username or password."

`ACCOUNT_EMAIL_CONFIRMATION_REQUIRED` defaults to true. Set it to false only for local testing: registration then creates an active account, sends no mail, and signs the person in. If `DEBUG` is false and the switch is false, Django refuses to start and `manage.py check` reports `accounts.E001`.

Until SMTP is configured, mail is printed in the `web` container logs (`EMAIL_BACKEND` defaults to the console backend). Real delivery needs `EMAIL_HOST` and `django.core.mail.backends.smtp.EmailBackend`.

Password reset and confirmation links expire after Django's `PASSWORD_RESET_TIMEOUT` (three days). A confirmation link stops working once the account is activated. Password reset mail is sent only to active accounts. Someone who has not confirmed yet uses the confirmation link, or the resend form. The resend answer is the same whether or not an account is waiting.

## Email request limit

Registration, the confirmation resend form, and password reset share one limit: `ACCOUNT_EMAIL_RATE_LIMIT` attempts per `ACCOUNT_EMAIL_RATE_WINDOW` seconds (defaults: 5 per hour). The same numbers apply to API registration, because it sends the same confirmation mail.

Each attempt counts against the caller IP (`REMOTE_ADDR`) and, when an address was submitted, against that address. The attempt is counted even when no account exists, so a rate-limit response does not reveal who is registered. A blocked call does not send mail and, for registration, does not create the account. The message is "Too many attempts. Try again later."

`X-Forwarded-For` is not trusted. A client can forge it. Behind a reverse proxy, the limit must be taught the real client address before it is useful.

The counters live in Redis (`REDIS_URL`, database 1, separate from Channels). If the cache cannot be reached, the request is allowed and a warning is logged, so a cache outage does not lock everyone out. Tests use a local memory cache and a high limit so the suite does not trip the cap.

## Passwords and usernames

Passwords are hashed by Django. They are never written to logs. New passwords must pass `AUTH_PASSWORD_VALIDATORS` and be at most 128 characters. The registration page shows those rules and does not block paste.

Usernames for new accounts are 3–30 characters and may contain only letters, digits, and underscore. Uniqueness ignores case (`accounts_user_username_ci`). Spaces, control characters, HTML markers, and web addresses are rejected. Reserved names such as `admin` and `support` cannot be registered; underscores do not bypass that (`Ad_min` is still reserved). Accounts created before these rules, including the existing `admin` user, keep their names and can still sign in.

Email addresses are stored in lower case and are unique. Older rows may have no email. Those accounts can sign in with a username, but password reset has nowhere to send mail until an address is set.

## Game and chat authority

The browser is not trusted to decide a legal move. Attack, defense, and the other table actions are checked in `fools/services.py` (whose turn it is, the phase, and whether the card is a legal defense). Lobby actions check membership and ownership there as well. WebSocket connections are accepted only for the signed-in user, and only if that user is still in the lobby or seated in that match.

There is no separate anti-cheat layer beyond those server checks. Timing, collusion between seats, and automated play are not detected.

## What this file is for

Add a short section when a change introduces or alters a limit, a privacy choice, an authentication rule, or a server-side game rule. Do not paste implementation tours. State the rule, where it is enforced, and what it deliberately does not do.
