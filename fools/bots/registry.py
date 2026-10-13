"""Lookup of bot strategies by key.

Register a new algorithm by adding it to ``STRATEGIES``. Callers ask for
a key and receive a strategy instance; they do not construct classes.
"""

from fools.bots.lowest import LowestCardStrategy
from fools.bots.strategy import BotStrategy

STRATEGIES: dict[str, type[BotStrategy]] = {
    LowestCardStrategy.key: LowestCardStrategy,
}

DEFAULT_STRATEGY = LowestCardStrategy.key


def get_strategy(key: str | None = None) -> BotStrategy:
    """Return the strategy registered under ``key``.

    Args:
        key: Registry name. ``None`` uses :data:`DEFAULT_STRATEGY`.

    Returns:
        A new strategy instance.

    Raises:
        KeyError: When ``key`` was never registered.
    """
    name = key or DEFAULT_STRATEGY
    return STRATEGIES[name]()
