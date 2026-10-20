"""Pending trade offers. Sleeper's public API does not list them.

The Sleeper web app asks ``sleeper.com/graphql`` with the operator's login
token (``league_transactions_filtered``, captured 2026-10-20). Read-only.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from vorpal.season.fetch import Source

GRAPHQL = "https://sleeper.com/graphql"
OP = "league_transactions_filtered"
# Not seen live yet: anything not finished counts as pending, so a new status
# name still reaches the operator instead of vanishing.
DONE = frozenset({"complete", "failed", "rejected", "cancelled", "expired", "vetoed"})
QUERY = """query league_transactions_filtered {
  league_transactions_filtered(league_id: "%s", roster_id_filters: [%d],
    type_filters: ["trade"], leg_filters: [], status_filters: []) {
    adds consenter_ids created creator drops roster_ids status transaction_id
  }
}"""


@dataclass(frozen=True)
class Offer:
    id: str
    partner_roster: int
    give: list[str]
    get: list[str]


def parse_offers(
    rows: list[Mapping[str, Any]], roster_id: int, user_id: str
) -> list[Offer]:
    """Proposed trades someone else sent to this roster."""
    offers = []
    for t in rows:
        if t.get("status") in DONE or t.get("creator") == user_id:
            continue
        adds, drops = t.get("adds") or {}, t.get("drops") or {}
        partners = [r for r in t.get("roster_ids") or [] if r != roster_id]
        offers.append(
            Offer(
                id=str(t["transaction_id"]),
                partner_roster=partners[0] if partners else 0,
                give=[p for p, r in drops.items() if r == roster_id],
                get=[p for p, r in adds.items() if r == roster_id],
            )
        )
    return offers


def pending_offers(
    source: Source, token: str, league_id: str, roster_id: int, user_id: str
) -> list[Offer]:
    query = QUERY % (league_id, roster_id)
    body = {"operationName": OP, "variables": {}, "query": query}
    data = source.post(
        GRAPHQL,
        body,
        headers={"authorization": token, "x-sleeper-graphql-op": OP},
    )
    return parse_offers(data["data"][OP], roster_id, user_id)


def token_expiry(token: str) -> datetime | None:
    """Expiry from a JWT's ``exp`` claim. None if the token is not a JWT."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        pad = "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
        return datetime.fromtimestamp(int(claims["exp"]), UTC)
    except (ValueError, KeyError, TypeError):
        return None
