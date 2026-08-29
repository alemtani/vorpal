"""One synthetic league that maps cleanly onto itself. No live network.

The recorded `players.json` is a redacted subset, so joining it to a real
projection file trips the 98% mapping gate. These fixtures build a host player
map and a FantasyPros file from the same list, one yahoo id apart, so the join
is exact and the test measures wiring rather than matching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SLEEPER = "https://api.sleeper.app/v1"
FANTASYPROS = "https://api.fantasypros.com/public/v2/json"
SEASON = "2025"

# Enough depth that every starting slot fills twice over in a 12-team league.
ROSTER: tuple[tuple[str, int], ...] = (
    ("QB", 24),
    ("RB", 60),
    ("WR", 60),
    ("TE", 24),
    ("K", 16),
    ("DST", 16),
)

_STATS: dict[str, dict[str, float]] = {
    "QB": {"pass_yds": 4200.0, "pass_tds": 30.0, "pass_ints": 10.0},
    "RB": {"rush_yds": 1100.0, "rush_tds": 9.0, "rec_rec": 40.0, "rec_yds": 300.0},
    "WR": {"rec_rec": 95.0, "rec_yds": 1250.0, "rec_tds": 8.0},
    "TE": {"rec_rec": 70.0, "rec_yds": 800.0, "rec_tds": 6.0},
    "K": {"xpt": 35.0},
    "DST": {"def_sack": 40.0, "def_int": 14.0, "def_td": 3.0},
}


def load(*parts: str) -> Any:
    return json.loads(FIXTURES.joinpath(*parts).read_text(encoding="utf-8"))


def _people() -> list[dict[str, Any]]:
    people: list[dict[str, Any]] = []
    yahoo = 1000
    for position, count in ROSTER:
        for index in range(1, count + 1):
            yahoo += 1
            people.append(
                {
                    "position": position,
                    "index": index,
                    "yahoo": str(yahoo),
                    "player_id": f"{position.lower()}{index}",
                    "first": position.title(),
                    "last": f"Number{index}",
                    "team": "KC",
                    "bye": 6 + (index % 6),
                }
            )
    return people


PEOPLE = _people()


def host_players() -> dict[str, Any]:
    """A `GET /players/nfl` body. `yahoo_id` is an int on the wire."""
    return {
        person["player_id"]: {
            "player_id": person["player_id"],
            "first_name": person["first"],
            "last_name": person["last"],
            "full_name": f"{person['first']} {person['last']}",
            # Sleeper's defense position is DEF; FantasyPros calls it DST.
            "position": "DEF" if person["position"] == "DST" else person["position"],
            "team": person["team"],
            "yahoo_id": int(person["yahoo"]),
            "fantasy_positions": [
                "DEF" if person["position"] == "DST" else person["position"]
            ],
        }
        for person in PEOPLE
    }


def _rank(person: dict[str, Any]) -> int:
    """Overall order: the better an index, the earlier the player goes."""
    order = {name: slot for slot, (name, _count) in enumerate(ROSTER)}
    return order[person["position"]] * 100 + person["index"]


def projections(position: str) -> dict[str, Any]:
    """One position's `week=0` season totals. Points columns are on the wire."""
    players = []
    for person in PEOPLE:
        if person["position"] != position:
            continue
        stats = dict(_STATS[position])
        # A decaying multiplier gives every position a real VOLS curve.
        scale = 1.0 - 0.01 * (person["index"] - 1)
        stats = {key: round(value * scale, 2) for key, value in stats.items()}
        stats["games"] = 17.0
        stats["points_ppr"] = 999.0
        players.append(
            {
                "fpid": person["yahoo"],
                "name": f"{person['first']} {person['last']}",
                "position_id": position,
                "team_id": person["team"],
                "player_yahoo_id": person["yahoo"],
                "player_bye_week": str(person["bye"]),
                "stats": stats,
            }
        )
    return {"season": SEASON, "week": "0", "players": players}


def consensus(*, kind: str) -> dict[str, Any]:
    """`type=ADP` and `type=draft` share one shape; only the key we read differs."""
    players = []
    for person in PEOPLE:
        rank = _rank(person)
        row: dict[str, Any] = {
            "player_id": person["yahoo"],
            "player_yahoo_id": person["yahoo"],
            "player_name": f"{person['first']} {person['last']}",
            "player_position_id": person["position"],
            "player_team_id": person["team"],
            "player_bye_week": str(person["bye"]),
            "rank_ecr": rank,
            "rank_min": max(1, rank - 3),
            "rank_max": rank + 3,
            "rank_std": 2.5,
        }
        if kind == "ADP":
            row["rank_ave"] = float(rank)
        players.append(row)
    return {"players": players}
