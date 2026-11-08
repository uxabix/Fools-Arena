"""Unit tests for `game.services` lobby and gameplay helpers."""

import pytest
from django.contrib.auth import get_user_model

from game.models import (
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
from game.services import (
    GameError,
    PHASE_BUILD,
    _table_attack_ranks,
    create_lobby,
    join_lobby,
    play_attack,
    set_ready,
    start_game,
)

User = get_user_model()


@pytest.mark.django_db
class TestLobbyServices:
    """Tests for lobby creation, joining, and game start preconditions."""

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
        hand_ids = list(PlayerHand.objects.filter(game=game).values_list("card_id", flat=True))
        assert len(hand_ids) == len(set(hand_ids))
        suit_rank = {
            (ph.card.suit_id, ph.card.rank_id)
            for ph in PlayerHand.objects.filter(game=game).select_related("card")
        }
        assert len(suit_rank) == len(hand_ids)
        trump_id = game.trump_card_id
        assert trump_id not in hand_ids
        assert not GameDeck.objects.filter(game=game, card_id=trump_id).exists()

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
    hands = PlayerHand.objects.filter(game=game, player=attacker).select_related("card__rank")
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
    TableCard.objects.create(game=game, attack_card=eight, defense_card=q_cover)
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
        GamePlayer.objects.create(game=game, user=u, seat_position=seat, cards_remaining=0)
    eight = Card.objects.filter(rank__value=8, special_card__isnull=True).first()
    queens = list(Card.objects.filter(rank__value=12, special_card__isnull=True)[:2])
    q_cover, q_hand = queens[0], queens[1]
    blocked = {eight.id, q_cover.id, q_hand.id}
    filler = list(Card.objects.filter(special_card__isnull=True).exclude(id__in=blocked)[:6])
    for i, card in enumerate(filler):
        PlayerHand.objects.create(game=game, player=b, card=card, order_in_hand=i + 1)
    GamePlayer.objects.filter(game=game, user=b).update(cards_remaining=len(filler))
    TableCard.objects.create(game=game, attack_card=eight, defense_card=q_cover)
    PlayerHand.objects.create(game=game, player=c, card=q_hand, order_in_hand=1)
    GamePlayer.objects.filter(game=game, user=c).update(cards_remaining=1)

    play_attack(game, c, [q_hand.id])
    assert TableCard.objects.filter(game=game).count() == 2


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
        GamePlayer.objects.create(game=game, user=u, seat_position=seat, cards_remaining=0)
    tens = list(Card.objects.filter(rank__value=10, special_card__isnull=True)[:2])
    eights = list(Card.objects.filter(rank__value=8, special_card__isnull=True)[:2])
    queens = list(Card.objects.filter(rank__value=12, special_card__isnull=True)[:1])
    blocked = {tens[0].id, tens[1].id, eights[0].id, eights[1].id, queens[0].id}
    filler = list(Card.objects.filter(special_card__isnull=True).exclude(id__in=blocked)[:6])
    for i, card in enumerate(filler):
        PlayerHand.objects.create(game=game, player=b, card=card, order_in_hand=i + 1)
    GamePlayer.objects.filter(game=game, user=b).update(cards_remaining=len(filler))
    TableCard.objects.create(game=game, attack_card=tens[0], defense_card=eights[0])
    TableCard.objects.create(game=game, attack_card=tens[1], defense_card=queens[0])
    PlayerHand.objects.create(game=game, player=c, card=eights[1], order_in_hand=1)
    GamePlayer.objects.filter(game=game, user=c).update(cards_remaining=1)

    assert 8 in _table_attack_ranks(game)
    play_attack(game, c, [eights[1].id])
    assert TableCard.objects.filter(game=game).count() == 3
