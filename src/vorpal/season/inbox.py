"""Pending trade offers. Sleeper's public API does not list them.

The request shape comes from the Sleeper web app and needs the operator's
login token. Until that is captured, this returns no offers.
"""

from __future__ import annotations

from dataclasses import dataclass

from vorpal.season.fetch import Source


@dataclass(frozen=True)
class Offer:
    id: str
    partner_roster: int
    give: list[str]
    get: list[str]


def pending_offers(
    source: Source, token: str, league_id: str, roster_id: int
) -> list[Offer]:
    return []
