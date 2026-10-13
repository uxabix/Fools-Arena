"""Read-only snapshot a strategy uses to choose one move.

The snapshot does not include hidden opponent cards. A strategy must not
need the database.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CardView:
    """One card the acting bot can see."""

    id: UUID
    suit_id: UUID
    rank: int
    is_trump: bool


@dataclass(frozen=True)
class TableRow:
    """One attack on the table, beaten or still open."""

    id: UUID
    attack: CardView
    defended: bool


@dataclass(frozen=True)
class BotState:
    """Everything the current decision needs.

    Attributes:
        actor_id: Bot who should act.
        role: ``open``, ``defend``, ``throw``, or ``bito``.
        hand: That bot's cards.
        table: Current attack rows.
        transferable: Lobby allows passing the attack.
        next_can_take_transfer: The next seat has room for a passed attack.
        throw_limit: How many more cards the table can still accept.
    """

    actor_id: UUID
    role: str
    hand: tuple[CardView, ...]
    table: tuple[TableRow, ...]
    transferable: bool
    next_can_take_transfer: bool
    throw_limit: int
