"""Play the cheapest legal card, and follow the lobby's rules plainly.

Opening and throwing prefer a non-trump. Defense uses the lowest card
that beats the cheapest open attack. When transfer is allowed and a
non-trump of the attack's rank is in hand, that card is passed on
instead of beating. A wave that is fully beaten is closed with bito.
"""

from fools.bots.actions import CallBito, DefendCard, PlayCards, TakeCards, TransferAttack
from fools.bots.state import BotState, CardView
from fools.bots.strategy import BotStrategy


def card_key(card: CardView):
    """Sort key: non-trumps before trumps, then the lowest rank.

    Args:
        card: Card to order.

    Returns:
        Tuple suitable for ``min``.
    """
    return (card.is_trump, card.rank, str(card.id))


def beats(card: CardView, other: CardView) -> bool:
    """Return whether ``card`` beats ``other`` under Durak rules.

    Args:
        card: Candidate defense.
        other: Attack card.

    Returns:
        True when the defense is legal.
    """
    if card.is_trump and not other.is_trump:
        return True
    if not card.is_trump and other.is_trump:
        return False
    if card.suit_id != other.suit_id:
        return False
    return card.rank > other.rank


class LowestCardStrategy(BotStrategy):
    """Always spend the smallest card that the current rule allows."""

    key = "lowest_card"

    def choose(self, state: BotState):
        """Pick one lowest-card action for ``state.role``.

        Args:
            state: Situation prepared by the runner.

        Returns:
            The action, or ``None`` when this role has no legal card.
        """
        if state.role == "open":
            return PlayCards(state.actor_id, (min(state.hand, key=card_key).id,))
        if state.role == "bito":
            return CallBito(state.actor_id)
        if state.role == "throw":
            return self._throw(state)
        if state.role == "defend":
            return self._defend(state)
        return None

    def _throw(self, state: BotState):
        ranks = {row.attack.rank for row in state.table}
        matches = [
            card for card in state.hand if card.rank in ranks and not card.is_trump
        ]
        if not matches or state.throw_limit < 1:
            return None
        return PlayCards(state.actor_id, (min(matches, key=card_key).id,))

    def _defend(self, state: BotState):
        transfer = self._transfer_card(state)
        if transfer is not None:
            return TransferAttack(state.actor_id, transfer.id)
        open_rows = [row for row in state.table if not row.defended]
        target = min(open_rows, key=lambda row: card_key(row.attack))
        beaters = [card for card in state.hand if beats(card, target.attack)]
        if beaters:
            return DefendCard(
                state.actor_id, target.id, min(beaters, key=card_key).id
            )
        return TakeCards(state.actor_id)

    def _transfer_card(self, state: BotState):
        if not state.transferable or not state.next_can_take_transfer:
            return None
        if any(row.defended for row in state.table):
            return None
        ranks = {row.attack.rank for row in state.table}
        matches = [
            card for card in state.hand if card.rank in ranks and not card.is_trump
        ]
        if not matches:
            return None
        return min(matches, key=card_key)
