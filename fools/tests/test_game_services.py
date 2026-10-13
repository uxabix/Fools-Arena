"""Unit tests for `fools.services` lobby and gameplay helpers."""

import pytest
from django.contrib.auth import get_user_model

from fools.models import (
    Card,
    CardRank,
    CardSuit,
    Game,
    GameDeck,
    GamePlayer,
    Lobby,
    LobbyPlayer,
    LobbySettings,
    PlayerHand,
    TableCard,
)
from fools.services import (
    GameError,
    PHASE_BETWEEN,
    PHASE_BUILD,
    _table_attack_ranks,
    create_lobby,
    join_lobby,
    PHASE_TAKING,
    pass_throw,
    play_attack,
    release_finished_seats,
    set_ready,
    start_game,
    take_table,
    transfer_attack,
)

User = get_user_model()


@pytest.mark.django_db
class TestLobbyServices:
    """Tests for lobby creation, joining, and fools start preconditions."""

    def test_create_public_lobby(self, test_user):
        """A public lobby should persist with settings and owner membership."""
        lobby = create_lobby(test_user, "Room A", is_private=False)
        assert lobby.name == "Room A"
        assert not lobby.is_private
        assert LobbyPlayer.objects.filter(lobby=lobby, user=test_user).exists()

    def test_private_lobby_requires_password_on_create(self, test_user):
        """Serializer layer enforces password; service still stores hash when given."""
        lobby = create_lobby(
            test_user, "Secret", is_private=True, password="hunter2"
        )
        assert lobby.is_private
        assert lobby.password_hash

    def test_join_wrong_password(self, test_user, second_user, user_factory):
        """Joining a private lobby with a bad password raises GameError."""
        host = user_factory(username="host_x")
        lobby = create_lobby(host, "P", is_private=True, password="ok")
        with pytest.raises(GameError) as exc:
            join_lobby(lobby, test_user, password="nope")
        assert exc.value.code == "auth"

    def test_start_game_requires_owner(self, test_user, second_user, durak_deck_36):
        """Only the lobby owner may call `start_game`."""
        lobby = create_lobby(test_user, "G1", is_private=False)
        join_lobby(lobby, second_user)
        set_ready(lobby, test_user, True)
        set_ready(lobby, second_user, True)
        with pytest.raises(GameError) as exc:
            start_game(lobby, second_user)
        assert exc.value.code == "forbidden"

    def test_start_game_happy_path(self, test_user, second_user, durak_deck_36):
        """Two ready players and a seeded deck produce an in-progress `Game`."""
        lobby = create_lobby(test_user, "G2", is_private=False)
        join_lobby(lobby, second_user)
        set_ready(lobby, test_user, True)
        set_ready(lobby, second_user, True)
        game = start_game(lobby, test_user)
        assert game.status == "in_progress"
        assert game.players.count() == 2
        assert "attacker_id" in (game.runtime_state or {})
        lobby.refresh_from_db()
        assert lobby.status == "playing"

    def test_start_game_dedupes_duplicate_suit_rank_rows(self, test_user, second_user, durak_deck_36):
        """Duplicate ``Card`` rows for the same suit+rank must not appear in one shoe."""
        hearts = CardSuit.objects.get(name="Hearts")
        ace = CardRank.objects.get(value=14)
        Card.objects.create(suit=hearts, rank=ace)
        lobby = create_lobby(test_user, "G-dedupe", is_private=False)
        join_lobby(lobby, second_user)
        set_ready(lobby, test_user, True)
        set_ready(lobby, second_user, True)
        game = start_game(lobby, test_user)
        hand_ids = list(PlayerHand.objects.filter(fools=game).values_list("card_id", flat=True))
        assert len(hand_ids) == len(set(hand_ids))
        suit_rank = {
            (ph.card.suit_id, ph.card.rank_id)
            for ph in PlayerHand.objects.filter(fools=game).select_related("card")
        }
        assert len(suit_rank) == len(hand_ids)
        trump_id = game.trump_card_id
        assert trump_id not in hand_ids
        bottom = GameDeck.objects.filter(fools=game).order_by("-position").first()
        assert bottom.card_id == trump_id

    def test_start_game_auto_seeds_cards_when_missing(self, test_user, second_user, durak_deck_36):
        """If normal playing cards were removed, ``start_game`` repopulates the catalog."""
        lobby = create_lobby(test_user, "G-autoseed", is_private=False)
        join_lobby(lobby, second_user)
        set_ready(lobby, test_user, True)
        set_ready(lobby, second_user, True)
        Card.objects.filter(special_card__isnull=True).delete()
        assert Card.objects.filter(special_card__isnull=True).count() == 0
        game = start_game(lobby, test_user)
        assert game.status == "in_progress"
        assert Card.objects.filter(special_card__isnull=True).count() >= 36


@pytest.mark.django_db
def test_active_game_blocks_second_start(test_user, second_user, durak_deck_36):
    """Starting again while a game is in progress must raise GameError."""
    lobby = create_lobby(test_user, "G3", is_private=False)
    join_lobby(lobby, second_user)
    set_ready(lobby, test_user, True)
    set_ready(lobby, second_user, True)
    start_game(lobby, test_user)
    # Lobby still 'playing' but can_start_game is False — service checks active Game.
    with pytest.raises(GameError) as exc:
        start_game(lobby, test_user)
    assert exc.value.code == "state"


@pytest.mark.django_db
def test_attack_stays_in_build_for_parallel_defense(test_user, second_user, durak_deck_36):
    """Wave stays in ``build`` so the defender can beat while others still throw in."""
    lobby = create_lobby(test_user, "parallel-wave", is_private=False)
    join_lobby(lobby, second_user)
    set_ready(lobby, test_user, True)
    set_ready(lobby, second_user, True)
    game = start_game(lobby, test_user)
    rs = game.runtime_state or {}
    assert rs.get("phase") == "between"
    attacker = test_user if str(test_user.id) == rs.get("attacker_id") else second_user
    hands = PlayerHand.objects.filter(fools=game, player=attacker).select_related("card__rank")
    by_rank_value = {}
    for ph in hands:
        by_rank_value.setdefault(ph.card.rank.value, []).append(ph.card.id)
    chosen = max(by_rank_value, key=lambda v: len(by_rank_value[v]))
    card_ids = by_rank_value[chosen]
    play_attack(game, attacker, card_ids)
    game.refresh_from_db()
    assert (game.runtime_state or {}).get("phase") == PHASE_BUILD


@pytest.mark.django_db
def test_table_attack_ranks_includes_defensive_card(durak_deck_36, test_user):
    """Podkidnoy: ranks on covered cards (defense) count for matching throw-ins."""
    lobby = Lobby.objects.create(owner=test_user, name="throw-ranks", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(lobby=lobby, trump_card=trump, status="in_progress", runtime_state={})
    eight = Card.objects.filter(rank__value=8, special_card__isnull=True).first()
    q_cover = Card.objects.filter(rank__value=12, special_card__isnull=True).first()
    TableCard.objects.create(fools=game, attack_card=eight, defense_card=q_cover)
    allowed = _table_attack_ranks(game)
    assert 8 in allowed
    assert 12 in allowed


@pytest.mark.django_db
def test_third_player_may_throw_rank_seen_only_on_defense(durak_deck_36, user_factory):
    """Third player can throw a queen when the only queen on table is the defender's card."""
    a = user_factory(username="pod_a")
    b = user_factory(username="pod_b")
    c = user_factory(username="pod_c")
    lobby = Lobby.objects.create(owner=a, name="podkidnut", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(a.id),
            "defender_id": str(b.id),
        },
    )
    for seat, u in enumerate((a, b, c), start=1):
        GamePlayer.objects.create(fools=game, user=u, seat_position=seat, cards_remaining=0)
    eight = Card.objects.filter(rank__value=8, special_card__isnull=True).first()
    queens = list(Card.objects.filter(rank__value=12, special_card__isnull=True)[:2])
    q_cover, q_hand = queens[0], queens[1]
    blocked = {eight.id, q_cover.id, q_hand.id}
    filler = list(Card.objects.filter(special_card__isnull=True).exclude(id__in=blocked)[:6])
    for i, card in enumerate(filler):
        PlayerHand.objects.create(fools=game, player=b, card=card, order_in_hand=i + 1)
    GamePlayer.objects.filter(fools=game, user=b).update(cards_remaining=len(filler))
    TableCard.objects.create(fools=game, attack_card=eight, defense_card=q_cover)
    PlayerHand.objects.create(fools=game, player=c, card=q_hand, order_in_hand=1)
    GamePlayer.objects.filter(fools=game, user=c).update(cards_remaining=1)

    play_attack(game, c, [q_hand.id])
    assert TableCard.objects.filter(fools=game).count() == 2


@pytest.mark.django_db
def test_throw_eight_when_two_tens_beaten_by_eight_and_queen(durak_deck_36, user_factory):
    """Ranks from all defense cards count with multiple table rows (two attacks)."""
    a = user_factory(username="mix_a")
    b = user_factory(username="mix_b")
    c = user_factory(username="mix_c")
    lobby = Lobby.objects.create(owner=a, name="mix-throw", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(a.id),
            "defender_id": str(b.id),
        },
    )
    for seat, u in enumerate((a, b, c), start=1):
        GamePlayer.objects.create(fools=game, user=u, seat_position=seat, cards_remaining=0)
    tens = list(Card.objects.filter(rank__value=10, special_card__isnull=True)[:2])
    eights = list(Card.objects.filter(rank__value=8, special_card__isnull=True)[:2])
    queens = list(Card.objects.filter(rank__value=12, special_card__isnull=True)[:1])
    blocked = {tens[0].id, tens[1].id, eights[0].id, eights[1].id, queens[0].id}
    filler = list(Card.objects.filter(special_card__isnull=True).exclude(id__in=blocked)[:6])
    for i, card in enumerate(filler):
        PlayerHand.objects.create(fools=game, player=b, card=card, order_in_hand=i + 1)
    GamePlayer.objects.filter(fools=game, user=b).update(cards_remaining=len(filler))
    TableCard.objects.create(fools=game, attack_card=tens[0], defense_card=eights[0])
    TableCard.objects.create(fools=game, attack_card=tens[1], defense_card=queens[0])
    PlayerHand.objects.create(fools=game, player=c, card=eights[1], order_in_hand=1)
    GamePlayer.objects.filter(fools=game, user=c).update(cards_remaining=1)

    assert 8 in _table_attack_ranks(game)
    play_attack(game, c, [eights[1].id])
    assert TableCard.objects.filter(fools=game).count() == 3


@pytest.mark.django_db
def test_beaten_attacks_do_not_use_up_the_defenders_hand(durak_deck_36, user_factory):
    """Three beaten attacks and three cards in hand still allow another throw."""
    attacker = user_factory(username="cap_a")
    defender = user_factory(username="cap_b")
    thrower = user_factory(username="cap_c")
    lobby = Lobby.objects.create(owner=attacker, name="cap", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(attacker.id),
            "defender_id": str(defender.id),
        },
    )
    for seat, user in enumerate((attacker, defender, thrower), start=1):
        GamePlayer.objects.create(fools=game, user=user, seat_position=seat, cards_remaining=0)
    sixes = list(Card.objects.filter(rank__value=6, special_card__isnull=True)[:4])
    covers = list(Card.objects.filter(rank__value=7, special_card__isnull=True)[:3])
    used = {card.id for card in sixes + covers}
    held = list(Card.objects.filter(special_card__isnull=True).exclude(id__in=used)[:3])
    for attack, cover in zip(sixes[:3], covers):
        TableCard.objects.create(fools=game, attack_card=attack, defense_card=cover)
    for index, card in enumerate(held):
        PlayerHand.objects.create(fools=game, player=defender, card=card, order_in_hand=index + 1)
    PlayerHand.objects.create(fools=game, player=thrower, card=sixes[3], order_in_hand=1)

    play_attack(game, thrower, [sixes[3].id])
    assert TableCard.objects.filter(fools=game).count() == 4


@pytest.mark.django_db
def test_uncovered_attacks_still_limit_the_throw(durak_deck_36, user_factory):
    """Open attacks already fill the defender's hand, so another card is refused."""
    attacker = user_factory(username="open_a")
    defender = user_factory(username="open_b")
    thrower = user_factory(username="open_c")
    lobby = Lobby.objects.create(owner=attacker, name="open-cap", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(attacker.id),
            "defender_id": str(defender.id),
        },
    )
    for seat, user in enumerate((attacker, defender, thrower), start=1):
        GamePlayer.objects.create(fools=game, user=user, seat_position=seat, cards_remaining=0)
    sixes = list(Card.objects.filter(rank__value=6, special_card__isnull=True)[:4])
    used = {card.id for card in sixes}
    held = list(Card.objects.filter(special_card__isnull=True).exclude(id__in=used)[:3])
    for attack in sixes[:3]:
        TableCard.objects.create(fools=game, attack_card=attack)
    for index, card in enumerate(held):
        PlayerHand.objects.create(fools=game, player=defender, card=card, order_in_hand=index + 1)
    PlayerHand.objects.create(fools=game, player=thrower, card=sixes[3], order_in_hand=1)

    with pytest.raises(GameError) as exc:
        play_attack(game, thrower, [sixes[3].id])
    assert exc.value.code == "rules"


@pytest.mark.django_db
def test_first_bout_stops_at_five_attacking_cards(durak_deck_36, user_factory):
    """Before the first discard the sixth attacking card is refused."""
    attacker = user_factory(username="five_a")
    defender = user_factory(username="five_b")
    thrower = user_factory(username="five_c")
    lobby = Lobby.objects.create(owner=attacker, name="five-cap", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(attacker.id),
            "defender_id": str(defender.id),
        },
    )
    for seat, user in enumerate((attacker, defender, thrower), start=1):
        GamePlayer.objects.create(fools=game, user=user, seat_position=seat, cards_remaining=0)
    attacks = [
        Card.objects.filter(rank__value=value, special_card__isnull=True).first()
        for value in (6, 7, 8, 9, 10)
    ]
    thrown = Card.objects.filter(rank__value=6, special_card__isnull=True).exclude(
        id=attacks[0].id
    ).first()
    used = {card.id for card in attacks} | {thrown.id}
    held = list(Card.objects.filter(special_card__isnull=True).exclude(id__in=used)[:6])
    for attack in attacks:
        TableCard.objects.create(fools=game, attack_card=attack)
    for index, card in enumerate(held):
        PlayerHand.objects.create(fools=game, player=defender, card=card, order_in_hand=index + 1)
    PlayerHand.objects.create(fools=game, player=thrower, card=thrown, order_in_hand=1)

    with pytest.raises(GameError) as exc:
        play_attack(game, thrower, [thrown.id])
    assert "5" in exc.value.message

    from fools.models import DiscardPile
    spare = Card.objects.filter(special_card__isnull=True).exclude(
        id__in=used | {card.id for card in held}
    ).first()
    DiscardPile.objects.create(fools=game, card=spare)
    play_attack(game, thrower, [thrown.id])
    assert TableCard.objects.filter(fools=game).count() == 6


@pytest.mark.django_db
def test_trump_is_drawn_last(test_user, second_user, durak_deck_36):
    """The face-up trump stays at the bottom until it is the last card dealt."""
    lobby = create_lobby(test_user, "trump-bottom", is_private=False)
    join_lobby(lobby, second_user)
    set_ready(lobby, test_user, True)
    set_ready(lobby, second_user, True)
    game = start_game(lobby, test_user)
    trump_id = game.trump_card_id
    while GameDeck.objects.filter(fools=game).count() > 1:
        GameDeck.draw_card(game)
    last = GameDeck.get_top_card(game)
    assert last.card_id == trump_id
    GameDeck.draw_card(game)
    assert not GameDeck.objects.filter(fools=game, card_id=trump_id).exists()


@pytest.mark.django_db
def test_empty_hand_is_not_asked_to_attack(durak_deck_36, user_factory):
    """After the deck is gone, a player with no cards does not open the next attack."""
    finished = user_factory(username="out_a")
    nxt = user_factory(username="out_b")
    third = user_factory(username="out_c")
    lobby = Lobby.objects.create(owner=finished, name="out-seats", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=4, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BETWEEN,
            "attacker_id": str(finished.id),
            "defender_id": str(nxt.id),
        },
    )
    for seat, user in enumerate((finished, nxt, third), start=1):
        GamePlayer.objects.create(fools=game, user=user, seat_position=seat, cards_remaining=0)
    held = list(Card.objects.filter(special_card__isnull=True).exclude(id=trump.id)[:4])
    for index, card in enumerate(held[:2]):
        PlayerHand.objects.create(fools=game, player=nxt, card=card, order_in_hand=index + 1)
    for index, card in enumerate(held[2:]):
        PlayerHand.objects.create(fools=game, player=third, card=card, order_in_hand=index + 1)

    release_finished_seats(game)
    game.refresh_from_db()
    assert game.runtime_state["attacker_id"] == str(nxt.id)
    assert game.runtime_state["defender_id"] == str(third.id)


@pytest.mark.django_db
def test_take_waits_until_the_attacker_is_done(durak_deck_36, user_factory):
    """A take stays on the table until the other player confirms they are done."""
    attacker = user_factory(username="take_a")
    defender = user_factory(username="take_b")
    lobby = Lobby.objects.create(owner=attacker, name="take-wait", status="playing")
    LobbySettings.objects.create(lobby=lobby, max_players=2, card_count=36)
    trump = Card.objects.filter(special_card__isnull=True).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(attacker.id),
            "defender_id": str(defender.id),
        },
    )
    for seat, user in enumerate((attacker, defender), start=1):
        GamePlayer.objects.create(fools=game, user=user, seat_position=seat, cards_remaining=0)
    attack = Card.objects.filter(rank__value=6, special_card__isnull=True).first()
    extra = Card.objects.filter(rank__value=6, special_card__isnull=True).exclude(id=attack.id).first()
    held = list(
        Card.objects.filter(special_card__isnull=True).exclude(id__in=[attack.id, extra.id, trump.id])[:3]
    )
    TableCard.objects.create(fools=game, attack_card=attack)
    PlayerHand.objects.create(fools=game, player=attacker, card=extra, order_in_hand=1)
    for index, card in enumerate(held):
        PlayerHand.objects.create(fools=game, player=defender, card=card, order_in_hand=index + 1)

    take_table(game, defender)
    game.refresh_from_db()
    assert game.runtime_state["phase"] == PHASE_TAKING
    assert TableCard.objects.filter(fools=game, attack_card=attack).exists()

    pass_throw(game, attacker)
    game.refresh_from_db()
    assert game.runtime_state["phase"] == PHASE_BETWEEN
    assert not TableCard.objects.filter(fools=game).exists()
    assert PlayerHand.objects.filter(fools=game, player=defender, card=attack).exists()


@pytest.mark.django_db
def test_transfer_passes_the_attack_to_the_next_player(durak_deck_36, user_factory):
    """A same-rank pass makes the next seat the defender and keeps the attacker."""
    attacker = user_factory(username="pass_a")
    defender = user_factory(username="pass_b")
    nxt = user_factory(username="pass_c")
    lobby = Lobby.objects.create(owner=attacker, name="transfer", status="playing")
    LobbySettings.objects.create(
        lobby=lobby, max_players=3, card_count=36, is_transferable=True
    )
    trump = Card.objects.filter(special_card__isnull=True, rank__value=14).first()
    game = Game.objects.create(
        lobby=lobby,
        trump_card=trump,
        status="in_progress",
        runtime_state={
            "phase": PHASE_BUILD,
            "attacker_id": str(attacker.id),
            "defender_id": str(defender.id),
        },
    )
    for seat, user in enumerate((attacker, defender, nxt), start=1):
        GamePlayer.objects.create(fools=game, user=user, seat_position=seat, cards_remaining=0)
    sixes = list(Card.objects.filter(rank__value=6, special_card__isnull=True)[:3])
    filler = list(
        Card.objects.filter(special_card__isnull=True).exclude(
            id__in=[card.id for card in sixes] + [trump.id]
        )[:4]
    )
    TableCard.objects.create(fools=game, attack_card=sixes[0])
    PlayerHand.objects.create(fools=game, player=defender, card=sixes[1], order_in_hand=1)
    PlayerHand.objects.create(fools=game, player=defender, card=sixes[2], order_in_hand=2)
    for index, card in enumerate(filler[:3]):
        PlayerHand.objects.create(fools=game, player=nxt, card=card, order_in_hand=index + 1)
    PlayerHand.objects.create(fools=game, player=attacker, card=filler[3], order_in_hand=1)

    transfer_attack(game, defender, [sixes[1].id, sixes[2].id])
    game.refresh_from_db()
    assert game.runtime_state["attacker_id"] == str(attacker.id)
    assert game.runtime_state["defender_id"] == str(nxt.id)
    assert TableCard.objects.filter(fools=game).count() == 3

    with pytest.raises(GameError):
        transfer_attack(game, nxt, [filler[0].id])
