"""A small fake league shaped like HAGS week 7. Names are real; ids are not."""

from __future__ import annotations

from typing import Any

import pytest

from vorpal.errors import PlatformError
from vorpal.season.context import build_season

SCORING = {"rec": 1.0, "rec_yd": 0.1, "rush_yd": 0.1, "rec_td": 6.0, "rush_td": 6.0}
SCORING_FULL = dict(SCORING, pass_yd=0.04, pass_td=4.0)

# pid: (name, pos, team, status, week-7 projection)
PLAYERS: dict[str, tuple[str, str, str | None, str | None, float]] = {
    "maye": ("Drake Maye", "QB", "NE", None, 21.0),
    "rodgers": ("Aaron Rodgers", "QB", "PIT", None, 18.0),
    "mckee": ("Tanner McKee", "QB", "PHI", None, 14.5),
    "gibbs": ("Jahmyr Gibbs", "RB", "DET", None, 26.0),
    "pierce": ("Dameon Pierce", "RB", "PHI", None, 6.3),
    "tuten": ("Bhayshul Tuten", "RB", "JAX", None, 0.0),
    "hall": ("Breece Hall", "RB", "NYJ", "Out", 14.0),
    "london": ("Drake London", "WR", "ATL", None, 17.0),
    "jwill": ("Jameson Williams", "WR", "DET", None, 11.5),
    "vele": ("Devaughn Vele", "WR", "NO", None, 10.0),
    "boston": ("Denzel Boston", "WR", "CLE", None, 11.0),
    "evans": ("Mike Evans", "WR", "SF", "Out", 16.0),
    "pat": ("Pat Freiermuth", "TE", "PIT", None, 9.7),
    "pitts": ("Kyle Pitts", "TE", "ATL", None, 7.7),
    "hock": ("T.J. Hockenson", "TE", "MIN", "Out", 10.5),
    # Nuyen
    "swift": ("D'Andre Swift", "RB", "CHI", None, 15.9),
    "hubbard": ("Chuba Hubbard", "RB", "CAR", None, 16.3),
    "nabers": ("Malik Nabers", "WR", "NYG", None, 13.8),
    "olave": ("Chris Olave", "WR", "NO", None, 17.0),
    "warren": ("Tyler Warren", "TE", "IND", "Out", 10.4),
    "shough": ("Tyler Shough", "QB", "NO", None, 15.9),
    "winston": ("Jameis Winston", "QB", "NYG", None, 12.1),
    # Rohan312
    "jacobs": ("Josh Jacobs", "RB", "GB", None, 12.8),
    "barkley": ("Saquon Barkley", "RB", "PHI", "Out", 13.8),
    "allen": ("Josh Allen", "QB", "BUF", None, 22.0),
    # free agents
    "harvey": ("RJ Harvey", "RB", "DEN", None, 11.5),
    "geno": ("Geno Smith", "QB", "NYJ", None, 16.1),
    "tucker": ("Tre Tucker", "WR", "LV", None, 10.0),
    "nobody": ("Practice Squad", "WR", None, None, 0.0),
}
BYES = {7: {"JAX", "BUF"}, 9: {"PIT"}, 11: {"NE", "ATL"}, 13: {"NYJ"}}
TEAMS = sorted({p[2] for p in PLAYERS.values() if p[2]} | {"KC"})

MY_PLAYERS = [
    "maye",
    "rodgers",
    "mckee",
    "gibbs",
    "pierce",
    "tuten",
    "hall",
    "london",
    "jwill",
    "vele",
    "boston",
    "evans",
    "pat",
    "pitts",
    "hock",
]
MY_STARTERS = [
    "maye",
    "pierce",
    "tuten",
    "london",
    "boston",
    "pat",
    "evans",
    "vele",
    "rodgers",
]


def _games(pid: str) -> dict[int, dict[str, float]]:
    """Season lines. Pitts rises; Pierce only played with Barkley out."""
    name, pos, team, status, proj = PLAYERS[pid]
    if pid == "pitts":
        tgts, snaps = [1, 3, 2, 3, 6, 7], [38, 23, 35, 30, 43, 47]
        return {
            w: {
                "rec_tgt": t,
                "rec": t * 0.7,
                "rec_yd": t * 7,
                "off_snp": s,
                "tm_off_snp": 60,
            }
            for w, (t, s) in enumerate(zip(tgts, snaps, strict=True), start=1)
        }
    if pid == "pierce":
        weeks = [5, 6]
    elif pid == "barkley":
        weeks = [1, 2, 3, 4]
    elif pos == "QB" or not team:
        weeks = []
    else:
        weeks = [1, 2, 3, 4, 5, 6]
    per = max(proj, 8.0)
    if pos == "RB":
        line = {"rush_att": per, "rush_yd": per * 4, "rec_tgt": 3, "rec": 2}
    else:
        line = {"rec_tgt": per / 2, "rec": per / 3, "rec_yd": per * 4}
    return {w: dict(line, off_snp=40, tm_off_snp=60) for w in weeks}


class FakeSource:
    def __init__(self, week: int = 7, espn_fails: bool = False) -> None:
        self.week = week
        self.espn_fails = espn_fails
        self.rosters_data = [
            {
                "roster_id": 7,
                "owner_id": "me",
                "players": list(MY_PLAYERS),
                "starters": list(MY_STARTERS),
                "reserve": ["hock"],
                "settings": {"waiver_budget_used": 89},
            },
            {
                "roster_id": 8,
                "owner_id": "nuyen",
                "players": [
                    "swift",
                    "hubbard",
                    "nabers",
                    "olave",
                    "warren",
                    "shough",
                    "winston",
                ],
                "starters": [],
                "reserve": None,
                "settings": {},
            },
            {
                "roster_id": 10,
                "owner_id": "rohan",
                "co_owners": None,
                "players": ["jacobs", "barkley", "allen"],
                "starters": [],
                "settings": {},
            },
        ]

    def state(self) -> dict[str, Any]:
        return {"season": "2026", "week": self.week}

    def league(self, league_id: str) -> dict[str, Any]:
        return {
            "league_id": league_id,
            "total_rosters": 3,
            "scoring_settings": SCORING_FULL,
            "roster_positions": [
                "QB",
                "RB",
                "RB",
                "WR",
                "WR",
                "TE",
                "FLEX",
                "FLEX",
                "SUPER_FLEX",
                "BN",
                "BN",
                "BN",
                "BN",
                "BN",
            ],
            "settings": {
                "playoff_week_start": 15,
                "waiver_budget": 240,
                "trade_deadline": 9,
                "reserve_slots": 2,
                "reserve_allow_out": 1,
            },
        }

    def rosters(self, league_id: str) -> list[dict[str, Any]]:
        return self.rosters_data

    def users(self, league_id: str) -> list[dict[str, Any]]:
        return [
            {"user_id": "me", "display_name": "alemtani"},
            {"user_id": "nuyen", "display_name": "Nuyen"},
            {"user_id": "rohan", "display_name": "Rohan312"},
        ]

    def players(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            pid: {
                "full_name": n,
                "position": pos,
                "team": team,
                "injury_status": status,
            }
            for pid, (n, pos, team, status, _) in PLAYERS.items()
        }
        out["kicker"] = {"full_name": "A Kicker", "position": "K", "team": "KC"}
        return out

    def schedule(self, season: int) -> list[dict[str, Any]]:
        """SF hosts KC on Monday of week 7. Everyone else plays Sunday."""
        games = []
        for w in range(1, 18):
            teams = [
                t
                for t in TEAMS
                if t not in BYES.get(w, set()) and t not in ("SF", "KC")
            ]
            if len(teams) % 2:
                teams.append("XX")
            sunday = "2026-10-25" if w == 7 else ""
            for i in range(0, len(teams), 2):
                games.append(
                    {"week": w, "home": teams[i], "away": teams[i + 1], "date": sunday}
                )
            day = "2026-10-26" if w == 7 else sunday
            games.append({"week": w, "home": "SF", "away": "KC", "date": day})
        return games

    def stats(self, season: int, week: int) -> list[dict[str, Any]]:
        rows = [
            {"player_id": pid, "stats": g[week]}
            for pid in PLAYERS
            if week in (g := _games(pid))
        ]
        rows.append({"player_id": "kicker", "stats": {"off_snp": 0}})
        rows.append({"player_id": "maye", "stats": None})
        return rows

    def projections(self, season: int, week: int) -> list[dict[str, Any]]:
        rows = []
        for pid, (_, _, team, _, proj) in PLAYERS.items():
            pts = proj
            if week != 7:
                pts = 0.0 if team in BYES.get(week, set()) else max(proj, 10.0)
            rows.append({"player_id": pid, "stats": {"rec_yd": pts * 10}})
        return rows

    def espn(self, season: int, week: int) -> dict[str, Any]:
        if self.espn_fails:
            raise PlatformError("ESPN down")
        return {"players": []}

    def matchups(self, league_id: str, week: int) -> list[dict[str, Any]]:
        return [
            {"roster_id": 7, "matchup_id": 1},
            {"roster_id": 8, "matchup_id": 1},
            {"roster_id": 10, "matchup_id": 2},
        ]

    def transactions(self, league_id: str, week: int) -> list[dict[str, Any]]:
        if week != 3:
            return []
        return [
            {"type": "waiver", "status": "complete", "settings": {"waiver_bid": b}}
            for b in (10, 20, 30)
        ] + [{"type": "free_agent", "status": "complete", "settings": None}]

    def fantasycalc(self, teams: int, qbs: int, ppr: float) -> list[dict[str, Any]]:
        values = {
            "swift": 3357,
            "jwill": 1350,
            "pitts": 680,
            "jacobs": 2733,
            "hall": 2834,
            "pierce": 313,
        }
        return [{"player": {"sleeperId": pid}, "value": v} for pid, v in values.items()]


@pytest.fixture(scope="session")
def season7():
    return build_season(FakeSource(), "L", "me")


@pytest.fixture
def make_source():
    return FakeSource
