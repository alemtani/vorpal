"""Everything one email needs: the league, this week's forecasts, the season sim."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vorpal.errors import PlatformError, UserRefusal
from vorpal.season.fetch import Source
from vorpal.season.forecast import Forecast, forecast_week, season_points
from vorpal.season.sim import SeasonSim, Value, lineup_slots
from vorpal.season.usage import Games, position_rates
from vorpal.season.vendors import PlayerIndex, espn_lines, sleeper_lines, vendor_points

LAST_WEEK = 17
SKILL = ("QB", "RB", "WR", "TE")


@dataclass
class Season:
    season: int
    week: int
    league: dict[str, Any]
    rosters: list[dict[str, Any]]
    owners: dict[int, str]
    players: dict[str, Any]
    me: dict[str, Any]
    scoring: dict[str, float]
    slots: list[str]
    plays: dict[int, set[str]]
    dates: dict[tuple[str, int], str]
    games: dict[str, Games]
    now: dict[str, Forecast]
    nxt: dict[str, Forecast]
    notes: list[str] = field(default_factory=list)

    @property
    def playoff_start(self) -> int:
        return int(self.league.get("settings", {}).get("playoff_week_start") or 15)

    @property
    def positions(self) -> dict[str, str]:
        return {pid: f.position for pid, f in {**self.nxt, **self.now}.items()}

    def active(self, roster: Mapping[str, Any]) -> list[str]:
        reserve = set(roster.get("reserve") or [])
        return [p for p in roster.get("players") or [] if p not in reserve]

    def roster(self, roster_id: int) -> dict[str, Any]:
        return next(r for r in self.rosters if r["roster_id"] == roster_id)

    def owner_of(self, pid: str) -> dict[str, Any] | None:
        return next((r for r in self.rosters if pid in (r.get("players") or [])), None)

    def free_agents(self) -> list[str]:
        taken = {p for r in self.rosters for p in r.get("players") or []}
        return [
            pid
            for pid, f in self.now.items()
            if pid not in taken and f.team and f.rate > 0
        ]

    def sim(self, n: int = 2000) -> SeasonSim:
        return SeasonSim(
            weeks=range(self.week, LAST_WEEK + 1),
            playoff_start=self.playoff_start,
            n=n,
        )

    def value(self, roster: Sequence[str], sim: SeasonSim) -> Value:
        pts = season_points(self.now, self.nxt, self.week, self.plays)
        return sim.value(roster, pts, self.positions, self.slots)

    def name(self, pid: str) -> str:
        return self.players.get(pid, {}).get("full_name", pid)


def _my_roster(rosters: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    for r in rosters:
        if r.get("owner_id") == user_id or user_id in (r.get("co_owners") or []):
            return r
    raise UserRefusal(f"user {user_id} has no roster in this league")


def _vendors(
    source: Source,
    season: int,
    week: int,
    index: PlayerIndex,
    scoring: Mapping[str, float],
    positions: Mapping[str, str],
    notes: list[str],
) -> dict[str, dict[str, float]]:
    lines: dict[str, Any] = {"sleeper": sleeper_lines(source.projections(season, week))}
    try:
        lines["espn"] = espn_lines(
            source.espn(season, week), index, season=season, week=week
        )
    except PlatformError as e:
        notes.append(f"ESPN projections missing for week {week}: {e}")
    return vendor_points(lines, scoring, positions)


def build_season(
    source: Source, league_id: str, user_id: str, week: int | None = None
) -> Season:
    state = source.state()
    season = int(state["season"])
    week = week or int(state["week"])
    league = source.league(league_id)
    rosters = source.rosters(league_id)
    users = {
        u["user_id"]: u.get("display_name", u["user_id"])
        for u in source.users(league_id)
    }
    players = source.players()
    me = _my_roster(rosters, user_id)
    scoring = {k: float(v) for k, v in league["scoring_settings"].items()}

    plays: dict[int, set[str]] = {}
    dates: dict[tuple[str, int], str] = {}
    for g in source.schedule(season):
        for team in (g["home"], g["away"]):
            plays.setdefault(g["week"], set()).add(team)
            dates[team, g["week"]] = g.get("date", "")

    games: dict[str, dict[int, Any]] = {}
    lines = []
    for w in range(1, week):
        for row in source.stats(season, w):
            st = row.get("stats") or {}
            if st.get("off_snp", 0) > 0:
                games.setdefault(row["player_id"], {})[w] = st
                pos = players.get(row["player_id"], {}).get("position", "")
                lines.append((pos, st))
    rates = position_rates(lines)

    positions = {
        pid: p["position"] for pid, p in players.items() if p.get("position") in SKILL
    }
    index = PlayerIndex({pid: players[pid] for pid in positions})
    notes: list[str] = []
    v_now = _vendors(source, season, week, index, scoring, positions, notes)
    v_next = (
        _vendors(source, season, week + 1, index, scoring, positions, notes)
        if week < LAST_WEEK
        else {}
    )
    rostered = {p for r in rosters for p in r.get("players") or []}
    pids = sorted((rostered | set(v_now) | set(v_next)) & set(positions))

    def fc(w: int, v: Mapping[str, Mapping[str, float]]) -> dict[str, Forecast]:
        return forecast_week(
            pids, w, players, games, rates, v, plays.get(w, set()), scoring
        )

    return Season(
        season=season,
        week=week,
        league=league,
        rosters=rosters,
        owners={r["roster_id"]: users.get(r.get("owner_id"), "?") for r in rosters},
        players=players,
        me=me,
        scoring=scoring,
        slots=lineup_slots(league["roster_positions"]),
        plays=plays,
        dates=dates,
        games=games,
        now=fc(week, v_now),
        nxt=fc(week + 1, v_next) if v_next else {},
        notes=notes,
    )
