"""Strategy interface for bot play.

A strategy looks at a :class:`~fools.bots.state.BotState` and returns one
action, or ``None`` when it should not move. New algorithms subclass
:class:`BotStrategy` and register a ``key``; they do not call the table
services themselves.
"""

from abc import ABC, abstractmethod

from fools.bots.actions import CallBito, DefendCard, PlayCards, TakeCards, TransferAttack
from fools.bots.state import BotState

BotAction = PlayCards | DefendCard | TransferAttack | TakeCards | CallBito


class BotStrategy(ABC):
    """One replaceable way to choose a bot's next card."""

    key = "base"

    @abstractmethod
    def choose(self, state: BotState) -> BotAction | None:
        """Return the next move, or ``None`` to leave the table alone.

        Args:
            state: Public situation for the acting bot.

        Returns:
            A single action, or ``None``.
        """
