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

A transferable lobby lets the defender pass the attack to the next seat with one or more cards of that same rank, before any card is beaten. Every attack on the table must share that rank, and the next player must hold enough cards for the whole pile. With three or more seats the original attacker does not change. With two seats the pass lands on that attacker, so the player who passed becomes the attacker and the former attacker defends. One seat is never both. The attacker is the seat that may throw further cards and that ends a beaten wave. This is enforced by `transfer_attack` in `fools/services.py`. A pass is refused after a card is beaten. Several attacking cards may be played at once. Uncovered attacks plus the new cards must fit in the defender's current hand; cards already beaten do not spend that hand. The table holds at most five attacking cards until the first cards go to the discard pile, and at most six after that. Throwing extra cards is still limited by the neighbor rule when that option is on. The table broadcast names the seat and the card that just landed; it does not include anyone else's hand or a private list of legal cards.

A new lobby is refused when its deck cannot deal 6 cards to every seat. 24 cards seat at most 4, 36 seat at most 6, and 52 seat at most 8. A smaller table may use a larger deck. This is checked in `LobbyCreateSerializer`, `create_lobby`, and again in `start_game` for the players actually about to sit. While the lobby is still waiting, the host can change that deck from the lobby page under the same rule.

While a lobby is waiting and no match is in progress, only the host can change the rules that affect play: seats, deck, transfer, neighbors only, bots, and hand signals. This is `update_lobby_settings` in `fools/services.py`, exposed as `PATCH /api/fools/lobbies/<id>/settings/`. The lobby name, privacy, and password are not part of that request. The new seat count cannot be lower than the number of people still seated, and the deck must still cover 6 cards for every seat. Saving the same values does nothing. When a value changes, every ready member becomes waiting, including the host. The lobby chat stores a system line (`Message.kind` is `system`) that names who changed which settings and that readiness was cleared. Members cannot post that kind; a normal chat line stays `user`. The lobby page flashes the settings and shows a notice. Jokers and the turn timer are stored on the lobby but are not on this form. Joining and toggling ready lock the lobby row first, so those actions cannot land in the middle of a settings save.

`fill_with_bots` seats bot accounts in the empty chairs when the owner starts. Every human still in the lobby must be ready first. Bots are ignored in that count, so one ready human is enough only when that person is the only human and the table has room for at least two. A human who is still waiting blocks the start and is not removed. `set_ready` accepts a change only while the lobby status is `waiting`. When the owner leaves and another human remains, that human is the one who took a seat earliest (`LobbyPlayer.joined_at`, set again if they rejoin). Bots are not chosen. Rows created before that field existed share one timestamp. The lobby page asks before leaving when the player is ready, is the host, or is already in a match. Leaving during a match still forfeits. Bots left in a lobby with no human are released first, so a new game can use them. If every existing bot is sitting with a human, a new bot account is created. Bots cannot sign in. They play through a replaceable strategy; the built-in one always uses the lowest legal card and will transfer, throw in, defend, take, or end the wave when that action is legal. Taking the cards, passing the attack, and ending the wave are announced on the table and then paused (`TABLE_ACTION_DELAY`, default 0.85s) so the cards stay visible. When `BOT_STEP_DELAY` is above zero, each later bot card is a separate step: a defense waits under about a second, and a throw-in waits a random interval that can run several seconds so a person can throw first. A bot does not end a beaten wave while another player can still throw in; that wait is also several seconds. Tests set both delays to zero, and then bots play through without those pauses. The list has no search or filters.

The trump card is the bottom card of the deck. It is dealt when the draw reaches it, and the suit stays known after that card has left the deck. The face is shown under the deck only while the card is still in the deck.

Once the deck is empty, a player with no cards is out. They are not asked to open the next attack or to defend it. If the defender has no cards left while attacks are still open, they declare that they are taking the table.

When the defender takes, the cards stay on the table until every player who may still throw in either adds a card or confirms they are done. A player with no cards is not asked. A new throw-in clears those confirmations. The defender cannot take once every card on the table is beaten; the attacker ends that wave. After the cards are picked up, the next seat clockwise opens the attack and the seat after that defends. With two players that is the same attacker again. This is enforced by `take_table`, `pass_throw`, and `_rotate_roles_after_take` in `fools/services.py`. The defender does not keep beating after they have chosen to take. Refill to six cards starts with the player who attacked, continues clockwise, and gives the player who beat or took whatever is left. If the deck is empty and nobody holds a card, the match ends with no fool. One player left holding cards is still the fool. A player can leave an in-progress match from the table; that forfeits, the leaver is the fool, and the match ends. The leaver is removed from the lobby at that moment, whether or not anyone else is still there. If no human remains, the lobby is closed and drops off the list; bots do not keep it open. Other humans stay. Leaving the lobby during a match forfeits the same way. The public list only shows a waiting lobby that still has a human in it. Search, sorting, and filters on that list run in the browser and do not reveal private lobbies. The table uses the same lobby chat. The last public announcements — who played a shown card, who took, transferred, confirmed, or ended the wave — are stored on the match and sent with the table state. They do not include hidden cards. The host of a finished match can deal again from the table. That readies every person still seated, then uses the same start rules. Bots do not keep a lobby seat after the match ends: those seats are marked left, and empty chairs are filled again only when the next game starts and `fill_with_bots` is still on. Someone who already left is not seated again, and this does not invite anyone new. Only the host can start it. This is `rematch` and `release_lobby_bots` in `fools/services.py`.

## Hand signals

A lobby can share two tells: which positions in a hand are lifted, and that the hand was reordered. The switch is `LobbySettings.share_hand_signals`. It defaults to on. The host turns it off in the create-lobby form, and can change it later from the lobby while the lobby is still waiting. `accept_hand_signal` in `fools/hand_signals.py` drops the tell when the switch is off, the match is not in progress, or the sender is not seated.

The match socket accepts `{"action": "hand_signal", "sort": ..., "selected": [indexes]}`. Indexes are positions in the sender's own fan, checked against the number of cards that seat still holds. The broadcast and the cache store only the seat id, the sort mode, and those indexes. Card ids, suits, and ranks are ignored if a client sends them. A seat may send at most 20 tells per second; further tells are dropped. The cache keeps the latest tell so a player who opens the table later can see it. If the cache cannot be reached, the tell is still broadcast and a warning is logged. Bots do not send tells. This does not hide which card is later played onto the table.

## Game and chat authority

The browser is not trusted to decide a legal move. Attack, defense, and the other table actions are checked in `fools/services.py` (whose turn it is, the phase, and whether the card is a legal defense). Lobby actions check membership and ownership there as well. A lobby-room or match WebSocket is accepted only for the signed-in user, and only if that user is still in that lobby or seated in that match. The public list socket is the exception: any signed-in user may listen, and private lobby contents are not sent on it.

There is no separate anti-cheat layer beyond those server checks. Timing, collusion between seats, and automated play are not detected.

## What this file is for

Add a short section when a change introduces or alters a limit, a privacy choice, an authentication rule, or a server-side game rule. Do not paste implementation tours. State the rule, where it is enforced, and what it deliberately does not do.
