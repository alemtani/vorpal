"""The transport side of a league host. ``LeagueHost`` is the parse side."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vorpal.contracts import Draft, League, Pick, Player, User


@runtime_checkable
class LeagueClient(Protocol):
    """Reads the CLI needs from a host, in generic types only.

    One implementation per platform: ``SleeperClient`` is v1's. Callers
    depend on this, never on a concrete client, so a second host is a new
    class and no edit to the wiring.
    """

    def get_draft(self, draft_id: str) -> Draft:
        """The draft. ``status`` drives the poll rate."""

    def get_picks(self, draft_id: str) -> tuple[Pick, ...]:
        """Picks made so far, in pick order."""

    def get_league(self, league_id: str) -> League:
        """The league. Scoring and roster settings come from here."""

    def get_user(self, name_or_id: str) -> User:
        """The operator, by username or id."""

    def get_players(self) -> dict[str, Player]:
        """The host player directory, keyed by host player id."""

    def close(self) -> None:
        """Release transport resources. Safe to call on an injected client."""
