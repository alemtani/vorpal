"""Opportunity model: volume decides role, efficiency and TDs regress.

Pure. A player's games are ``{week: Sleeper stat line}``. Constants come
from the 2025 backtest in ``season.fit`` (see docs/specs/season.md).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

Line = Mapping[str, float]
Games = Mapping[int, Line]


@dataclass(frozen=True)
class Params:
    half_life: float = 4.0
    k_targets: float = 60.0
    k_carries: float = 120.0
    td_rz_target: float = 0.30
    td_target: float = 0.012
    td_rz_carry: float = 0.19
    td_carry: float = 0.005
    actual_td_weight: float = 0.25


@dataclass(frozen=True)
class Rates:
    """Position averages: catch rate, yards per target, yards per carry."""

    catch: float
    ypt: float
    ypc: float


# 2026 weeks 1-6. Used when a season has too little volume to measure.
DEFAULT_RATES: dict[str, Rates] = {
    "RB": Rates(catch=0.775, ypt=5.47, ypc=4.10),
    "WR": Rates(catch=0.621, ypt=8.05, ypc=5.08),
    "TE": Rates(catch=0.716, ypt=6.95, ypc=4.00),
}


@dataclass(frozen=True)
class ExpectedLine:
    stats: dict[str, float]
    targets: float
    carries: float
    rz_targets: float
    rz_carries: float
    expected_td: float
    games: int


def position_rates(lines: Iterable[tuple[str, Line]]) -> dict[str, Rates]:
    """Season averages per skill position, from (position, game line) pairs."""
    sums: dict[str, dict[str, float]] = {pos: {} for pos in DEFAULT_RATES}
    for pos, line in lines:
        if pos not in sums:
            continue
        acc = sums[pos]
        for key in ("rec_tgt", "rec", "rec_yd", "rush_att", "rush_yd"):
            acc[key] = acc.get(key, 0.0) + line.get(key, 0.0)
    rates: dict[str, Rates] = {}
    for pos, acc in sums.items():
        base = DEFAULT_RATES[pos]
        tgt, car = acc.get("rec_tgt", 0.0), acc.get("rush_att", 0.0)
        rates[pos] = Rates(
            catch=acc["rec"] / tgt if tgt else base.catch,
            ypt=acc["rec_yd"] / tgt if tgt else base.ypt,
            ypc=acc["rush_yd"] / car if car else base.ypc,
        )
    return rates


def _shrink(total: float, n: float, k: float, avg: float) -> float:
    return (total + avg * k) / (n + k)


def expected_line(
    games: Games, week: int, rates: Rates, params: Params
) -> ExpectedLine | None:
    """Expected stat line for ``week`` from games before it. None if no games."""
    past = [w for w in games if w < week]
    if not past:
        return None
    weight = {w: 0.5 ** ((week - 1 - w) / params.half_life) for w in past}
    total_w = sum(weight.values())

    def avg(key: str) -> float:
        return sum(weight[w] * games[w].get(key, 0.0) for w in past) / total_w

    def total(key: str) -> float:
        return sum(games[w].get(key, 0.0) for w in past)

    n_tgt, n_car = total("rec_tgt"), total("rush_att")
    catch = _shrink(total("rec"), n_tgt, params.k_targets, rates.catch)
    ypt = _shrink(total("rec_yd"), n_tgt, params.k_targets, rates.ypt)
    ypc = _shrink(total("rush_yd"), n_car, params.k_carries, rates.ypc)

    tgt, car = avg("rec_tgt"), avg("rush_att")
    rz_tgt, rz_car = avg("rec_rz_tgt"), avg("rush_rz_att")
    rec_xtd = params.td_rz_target * rz_tgt + params.td_target * (tgt - rz_tgt)
    rush_xtd = params.td_rz_carry * rz_car + params.td_carry * (car - rz_car)
    a = params.actual_td_weight
    stats = {
        "rec": tgt * catch,
        "rec_yd": tgt * ypt,
        "rush_yd": car * ypc,
        "rec_td": (1 - a) * rec_xtd + a * avg("rec_td"),
        "rush_td": (1 - a) * rush_xtd + a * avg("rush_td"),
        "fum_lost": avg("fum_lost"),
    }
    return ExpectedLine(
        stats=stats,
        targets=tgt,
        carries=car,
        rz_targets=rz_tgt,
        rz_carries=rz_car,
        expected_td=rec_xtd + rush_xtd,
        games=len(past),
    )


def score_line(line: Line, scoring: Mapping[str, float], position: str) -> float:
    """League points for a stat line. Adds the per-catch bonus for the position."""
    points = sum(line.get(key, 0.0) * w for key, w in scoring.items())
    bonus = scoring.get(f"bonus_rec_{position.lower()}", 0.0)
    return points + bonus * line.get("rec", 0.0)


def _share(line: Line) -> float:
    team = line.get("tm_off_snp", 0.0)
    return line.get("off_snp", 0.0) / team if team else 0.0


def _volume(line: Line) -> float:
    return line.get("rec_tgt", 0.0) + line.get("rush_att", 0.0)


def rising(games: Games, week: int) -> bool:
    """Snap share and targets + carries both rose in each of the last 2 games."""
    past = sorted(w for w in games if w < week)[-3:]
    if len(past) < 3:
        return False
    a, b, c = (games[w] for w in past)
    return _share(a) < _share(b) < _share(c) and _volume(a) < _volume(b) < _volume(c)


def role_games(games: Games, week: int, teammates_now: Iterable[Games]) -> int:
    """Games before ``week`` in which every listed teammate was also active.

    ``teammates_now`` are same-position teammates expected to play this week.
    A game played while one of them sat is a fill-in game and does not count.
    """
    mates = list(teammates_now)
    return sum(
        1
        for w in games
        if w < week and all(m.get(w, {}).get("off_snp", 0.0) > 0 for m in mates)
    )
