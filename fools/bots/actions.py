"""Moves a bot strategy can ask the table to play.

Strategies return these values. The runner is the only code that turns
them into service calls, so a new strategy cannot bypass the rules.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class PlayCards:
    """Open an attack or throw in one or more cards of the same rank."""

    user_id: UUID
    card_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class DefendCard:
    """Beat one table row with a card from the defender's hand."""

    user_id: UUID
    table_card_id: UUID
    card_id: UUID


@dataclass(frozen=True)
class TransferAttack:
    """Pass the attack to the next player with a card of the same rank."""

    user_id: UUID
    card_id: UUID


@dataclass(frozen=True)
class TakeCards:
    """Defender picks up the table."""

    user_id: UUID


@dataclass(frozen=True)
class CallBito:
    """Attacker ends a fully defended wave."""

    user_id: UUID


@dataclass(frozen=True)
class PassThrow:
    """Thrower confirms they will not add more cards to a take."""

    user_id: UUID
