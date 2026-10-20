"""One number per player per week, and the weekly points used for the season."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vorpal.season.blend import blend, status_factor
from vorpal.season.usage import (
    DEFAULT_RATES,
    Games,
    Params,
    Rates,
    expected_line,
    rising,
    role_games,
    score_line,
)

# A teammate who projects above this is expected to play this week.
ACTIVE_TEAMMATE_POINTS = 5.0
# Weeks until a player with this status is assumed back.
RETURN_WEEKS: dict[str, int] = {
    "Questionable": 0,
    "Doubtful": 1,
    "Out": 1,
    "Sus": 1,
    "IR": 4,
    "PUP": 4,
}


@dataclass(frozen=True)
class Forecast:
    pid: str
    name: str
    position: str
    team: str | None
    status: str | None
    model: float | None
    vendors: dict[str, float]
    role_games: int
    rate: float
    points: float
    plays: bool
    rising: bool


def _vendor_mean(v: Mapping[str, float] | None) -> float:
    return sum(v.values()) / len(v) if v else 0.0


def forecast_week(
    pids: Sequence[str],
    week: int,
    players: Mapping[str, Mapping[str, Any]],
    games: Mapping[str, Games],
    rates: Mapping[str, Rates],
    vendors: Mapping[str, Mapping[str, float]],
    teams_playing: set[str],
    scoring: Mapping[str, float],
    params: Params | None = None,
) -> dict[str, Forecast]:
    """Forecast for each pid. ``rate`` ignores status and bye; ``points`` does not."""
    params = params or Params()
    by_team: dict[tuple[str, str], list[str]] = {}
    for pid, p in players.items():
        if p.get("team") and p.get("position"):
            by_team.setdefault((p["team"], p["position"]), []).append(pid)

    out: dict[str, Forecast] = {}
    for pid in pids:
        p = players.get(pid, {})
        pos, team = p.get("position", ""), p.get("team")
        mine = games.get(pid, {})
        model = None
        role = 0
        if pos in DEFAULT_RATES:
            line = expected_line(mine, week, rates.get(pos, DEFAULT_RATES[pos]), params)
            if line is not None:
                model = score_line(line.stats, scoring, pos)
                mates = [
                    games.get(m, {})
                    for m in by_team.get((team or "", pos), [])
                    if m != pid
                    and _vendor_mean(vendors.get(m)) > ACTIVE_TEAMMATE_POINTS
                ]
                role = role_games(mine, week, mates)
        v = dict(vendors.get(pid, {}))
        rate = blend(model, v, role) or 0.0
        plays = bool(team) and team in teams_playing
        status = p.get("injury_status")
        out[pid] = Forecast(
            pid=pid,
            name=p.get("full_name", pid),
            position=pos,
            team=team,
            status=status,
            model=model,
            vendors=v,
            role_games=role,
            rate=rate,
            points=rate * status_factor(status) if plays else 0.0,
            plays=plays,
            rising=rising(mine, week),
        )
    return out


def back_week(f: Forecast, week: int) -> int:
    """First week a player with an injury status is assumed to play again."""
    return week + RETURN_WEEKS.get(f.status or "", 0)


def assumed_returns(
    forecasts: Mapping[str, Forecast], pids: Sequence[str], week: int
) -> str:
    """'Mike Evans (Out) week 8, ...' for hurt players among ``pids``."""
    hurt = [
        f"{f.name} ({f.status}) week {back_week(f, week)}"
        for p in pids
        if (f := forecasts.get(p)) is not None and back_week(f, week) > week
    ]
    return ", ".join(hurt)


def season_points(
    this_week: Mapping[str, Forecast],
    next_week: Mapping[str, Forecast],
    week: int,
    plays: Mapping[int, set[str]],
):
    """Weekly points for the simulation.

    The rate is this week's, or next week's for a player on bye now. A player
    with an injury status is out until ``RETURN_WEEKS`` have passed.
    """

    def rate(pid: str) -> float:
        now = this_week.get(pid)
        if now is not None and now.plays:
            return now.rate
        later = next_week.get(pid)
        return later.rate if later is not None else (now.rate if now else 0.0)

    rates = {pid: rate(pid) for pid in set(this_week) | set(next_week)}

    def points(pid: str, w: int) -> float:
        f = this_week.get(pid) or next_week.get(pid)
        if f is None or f.team is None or f.team not in plays.get(w, set()):
            return 0.0
        if w < back_week(f, week):
            return 0.0
        if w == week:
            return f.points
        return rates[pid]

    return points
