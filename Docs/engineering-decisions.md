# Engineering decisions

Record important behavior here when it changes: limits, privacy, account rules, and how the game decides what a player is allowed to do. Write in English. Keep each note short enough that the next change can update it in the same commit.

## Account email

New accounts stay inactive until the person opens the confirmation link. Sign-in does not say whether the username exists, the password is wrong, or the account is still inactive. The message is always "Incorrect username or password."

`ACCOUNT_EMAIL_CONFIRMATION_REQUIRED` defaults to true. Set it to false only for local testing: registration then creates an active account, sends no mail, and signs the person in. If `DEBUG` is false and the switch is false, Django refuses to start and `manage.py check` reports `accounts.E001`.

Until SMTP is configured, mail is printed in the `web` container logs (`EMAIL_BACKEND` defaults to the console backend). Real delivery needs `EMAIL_HOST` and `django.core.mail.backends.smtp.EmailBackend`.

Password reset and confirmation links expire after Django's `PASSWORD_RESET_TIMEOUT` (three days). A confirmation link stops working once the account is activated. Password reset mail is sent only to active accounts. Someone who has not confirmed yet uses the confirmation link, or the resend form. The resend answer is the same whether or not an account is waiting.

## Email request limit

Registration, the confirmation resend form, password reset, and the profile change-password button share one limit: `ACCOUNT_EMAIL_RATE_LIMIT` attempts per `ACCOUNT_EMAIL_RATE_WINDOW` seconds (defaults: 5 per hour). The same numbers apply to API registration, because it sends the same confirmation mail.

Each attempt counts against the caller IP (`REMOTE_ADDR`) and, when an address was submitted, against that address. The attempt is counted even when no account exists, so a rate-limit response does not reveal who is registered. A blocked call does not send mail and, for registration, does not create the account. The message is "Too many attempts. Try again later."

`X-Forwarded-For` is not trusted. A client can forge it. Behind a reverse proxy, the limit must be taught the real client address before it is useful.

The counters live in Redis (`REDIS_URL`, database 1, separate from Channels). If the cache cannot be reached, the request is allowed and a warning is logged, so a cache outage does not lock everyone out. Tests use a local memory cache and a high limit so the suite does not trip the cap.

## Passwords and usernames

Passwords are hashed by Django. They are never written to logs. New passwords must pass `AUTH_PASSWORD_VALIDATORS` and be at most 128 characters. The registration page shows those rules and does not block paste.

Usernames for new accounts are 3–30 characters and may contain only letters, digits, and underscore. Uniqueness ignores case (`accounts_user_username_ci`). Spaces, control characters, HTML markers, and web addresses are rejected. Reserved names such as `admin` and `support` cannot be registered; underscores do not bypass that (`Ad_min` is still reserved). Accounts created before these rules, including the existing `admin` user, keep their names and can still sign in.

Email addresses are stored in lower case and are unique. Older rows may have no email. Those accounts can sign in with a username, but password reset has nowhere to send mail until an address is set.

## Profile account changes

Changing an email on the profile requires the current password. The new address is stored immediately and is not confirmed by a second link.

Changing a password from the profile does not ask for the current password. The button emails the same reset link as the public password-reset form, to the address already stored on the account. The new password is chosen on that link. An account with no email cannot start this until an address is added. The request uses the shared email limit, and a blocked request does not send mail.

## Lobby list and creation

The public list shows waiting lobbies that are not private and still have someone in them. A full lobby stays on the list and is marked as having no seats. A private lobby is left off the list. Joining it requires the password; the link alone is not enough, and the password is stored only as a hash. Creating or joining a lobby leaves every other lobby the player is still in. The list page asks before either action when the player is already in a lobby: they can cancel, return to that lobby, or continue.

Signed-in users can subscribe to `ws/lobbies/` for list changes. That socket does not require membership in a lobby, and it only receives public waiting lobbies (or an id to remove). A lobby room socket still requires membership.

A transferable lobby lets the defender pass the attack with a card of the same rank, before any card is beaten, and only when the next player holds enough cards to receive it. Several attacking cards may be played at once. Uncovered attacks plus the new cards must fit in the defender's current hand; cards already beaten do not spend that hand. The table holds at most five attacking cards until the first cards go to the discard pile, and at most six after that. Throwing extra cards is still limited by the neighbor rule when that option is on. The table broadcast names the seat and the card that just landed; it does not include anyone else's hand or a private list of legal cards.

`fill_with_bots` seats bot accounts in the empty chairs when the owner starts. One ready human is enough to start when that option is on and the table has room for at least two. Bots left in a lobby with no human are released first, so a new game can use them. If every existing bot is sitting with a human, a new bot account is created. Bots cannot sign in. They play through a replaceable strategy; the built-in one always uses the lowest legal card and will transfer, throw in, defend, take, or end the wave when that action is legal. Taking the cards, passing the attack, and ending the wave are announced on the table and then paused (`TABLE_ACTION_DELAY`, default 0.85s) so the cards stay visible. When `BOT_STEP_DELAY` is above zero, each later bot card is a separate step: a defense waits under about a second, and a throw-in waits a random interval that can run several seconds so a person can throw first. A bot does not end a beaten wave while another player can still throw in; that wait is also several seconds. Tests set both delays to zero, and then bots play through without those pauses. The list has no search or filters.

The trump card is the bottom card of the deck. It is dealt when the draw reaches it, and the suit stays known after that card has left the deck. The face is shown under the deck only while the card is still in the deck.

Once the deck is empty, a player with no cards is out. They are not asked to open the next attack or to defend it. If the defender has no cards left while attacks are still open, they declare that they are taking the table.

When the defender takes, the cards stay on the table until every player who may still throw in either adds a card or confirms they are done. A player with no cards is not asked. A new throw-in clears those confirmations. This is enforced by `take_table` and `pass_throw` in `fools/services.py`. The defender does not keep beating after they have chosen to take. A player can leave an in-progress match from the table; that forfeits, the leaver is the fool, and the match ends. It does not keep the other seats playing. Leaving the lobby during a match does the same. Bots do not keep a lobby open. When the last human leaves, the lobby is closed and any match still running there is finished. The public list only shows a waiting lobby that still has a human in it.

## Game and chat authority

The browser is not trusted to decide a legal move. Attack, defense, and the other table actions are checked in `fools/services.py` (whose turn it is, the phase, and whether the card is a legal defense). Lobby actions check membership and ownership there as well. A lobby-room or match WebSocket is accepted only for the signed-in user, and only if that user is still in that lobby or seated in that match. The public list socket is the exception: any signed-in user may listen, and private lobby contents are not sent on it.

There is no separate anti-cheat layer beyond those server checks. Timing, collusion between seats, and automated play are not detected.

## What this file is for

Add a short section when a change introduces or alters a limit, a privacy choice, an authentication rule, or a server-side game rule. Do not paste implementation tours. State the rule, where it is enforced, and what it deliberately does not do.
