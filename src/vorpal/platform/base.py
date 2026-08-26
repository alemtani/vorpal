"""Abstract league host. Valuation and resolve depend on this, not on Sleeper."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from vorpal.contracts import Draft, League, Pick, Player, User


class LeagueHost(ABC):
    """One adapter per fantasy platform.

    Parse functions take already-fetched JSON. Transport (HTTP, cache, backoff)
    lives in the host package that owns the network (S1 for Sleeper).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable host id, e.g. ``sleeper`` or ``espn``."""

    @abstractmethod
    def parse_draft(self, payload: Any) -> Draft:
        """Map a host draft object to the generic ``Draft``."""

    @abstractmethod
    def parse_league(self, payload: Any) -> League:
        """Map a host league object to the generic ``League``."""

    @abstractmethod
    def parse_picks(self, payload: Any) -> tuple[Pick, ...]:
        """Map a host picks list to generic ``Pick`` rows."""

    @abstractmethod
    def parse_players(self, payload: Any) -> dict[str, Player]:
        """Map a host player file to generic ``Player`` rows, keyed by host id."""

    @abstractmethod
    def parse_user(self, payload: Any) -> User:
        """Map a host user object to the generic ``User``."""
