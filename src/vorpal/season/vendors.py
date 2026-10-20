"""Vendor projections as stat lines keyed by Sleeper player id.

Sleeper lines already use Sleeper's scoring keys. ESPN lines are mapped
from ESPN stat ids. Both are scored with the league's table, never with a
vendor's own fantasy-point total.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from vorpal.season.usage import Line, score_line

# ESPN stat id -> Sleeper scoring key. Checked against ESPN's own PPR
# totals for every week 7 QB/RB/WR/TE (2026-10-19).
ESPN_STATS: dict[str, str] = {
    "3": "pass_yd",
    "4": "pass_td",
    "19": "pass_2pt",
    "20": "pass_int",
    "24": "rush_yd",
    "25": "rush_td",
    "26": "rush_2pt",
    "42": "rec_yd",
    "43": "rec_td",
    "44": "rec_2pt",
    "53": "rec",
    "72": "fum_lost",
}
ESPN_POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE"}
ESPN_PROJECTION = 1

_SUFFIX = re.compile(r"(jr|sr|ii|iii|iv|v)$")


def normalize_name(name: str) -> str:
    return _SUFFIX.sub("", re.sub(r"[^a-z]", "", name.lower()))


class PlayerIndex:
    """Find a Sleeper id from a vendor's id or (name, position)."""

    def __init__(self, players: Mapping[str, Mapping[str, Any]]) -> None:
        self._espn: dict[str, str] = {}
        self._names: dict[tuple[str, str], list[str]] = {}
        for pid, p in players.items():
            if p.get("espn_id"):
                self._espn[str(p["espn_id"])] = pid
            if p.get("full_name") and p.get("position"):
                key = (normalize_name(p["full_name"]), p["position"])
                self._names.setdefault(key, []).append(pid)
        self._players = players

    def find(self, espn_id: Any, name: str, position: str) -> str | None:
        if espn_id is not None and str(espn_id) in self._espn:
            return self._espn[str(espn_id)]
        found = self._names.get((normalize_name(name), position), [])
        if len(found) > 1:  # prefer the one on a team; refuse a real tie
            found = [pid for pid in found if self._players[pid].get("team")]
        return found[0] if len(found) == 1 else None


def sleeper_lines(rows: Iterable[Mapping[str, Any]]) -> dict[str, Line]:
    return {r["player_id"]: r["stats"] for r in rows if r.get("stats")}


def espn_lines(
    payload: Mapping[str, Any], index: PlayerIndex, *, season: int, week: int
) -> dict[str, Line]:
    lines: dict[str, Line] = {}
    for row in payload.get("players", []):
        p = row["player"]
        pos = ESPN_POSITIONS.get(p.get("defaultPositionId"))
        if pos is None:
            continue
        proj = [
            s
            for s in p.get("stats", [])
            if s.get("seasonId") == season
            and s.get("scoringPeriodId") == week
            and s.get("statSourceId") == ESPN_PROJECTION
        ]
        pid = index.find(p.get("id"), p.get("fullName", ""), pos)
        if not proj or pid is None:
            continue
        stats = proj[0].get("stats", {})
        lines[pid] = {
            key: stats[sid] for sid, key in ESPN_STATS.items() if sid in stats
        }
    return lines


def vendor_points(
    vendors: Mapping[str, Mapping[str, Line]],
    scoring: Mapping[str, float],
    positions: Mapping[str, str],
) -> dict[str, dict[str, float]]:
    """{player: {vendor: points}} for players with a known position."""
    out: dict[str, dict[str, float]] = {}
    for vendor, lines in vendors.items():
        for pid, line in lines.items():
            pos = positions.get(pid)
            if pos:
                out.setdefault(pid, {})[vendor] = score_line(line, scoring, pos)
    return out
