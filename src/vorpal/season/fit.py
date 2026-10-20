"""Backtest the opportunity model on a finished season.

Each player-week is predicted from earlier weeks only. Errors are mean
absolute error in league points per player-week.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vorpal.season.report import Report, Table
from vorpal.season.usage import (
    DEFAULT_RATES,
    Params,
    expected_line,
    position_rates,
    score_line,
)

MIN_TOUCHES = 40
FIRST_WEEK = 4
HALF_LIVES = (1.0, 2.0, 3.0, 4.0, 6.0, 10.0)
TD_WEIGHTS = (0.0, 0.25, 0.5, 1.0)
MODEL_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)

Rows = Mapping[int, Sequence[Mapping[str, Any]]]


def _mae(errors: list[float]) -> float:
    return sum(errors) / len(errors) if errors else float("nan")


def backtest(
    stats: Rows,
    projections: Rows,
    players: Mapping[str, Mapping[str, Any]],
    scoring: Mapping[str, float],
) -> Report:
    games: dict[str, dict[int, Mapping[str, float]]] = {}
    for w, rows in stats.items():
        for r in rows:
            st = r.get("stats") or {}
            if st.get("off_snp", 0) > 0:
                games.setdefault(r["player_id"], {})[w] = st
    pos_of = {pid: players.get(pid, {}).get("position", "") for pid in games}
    rates = position_rates(
        (pos_of[pid], line) for pid, g in games.items() for line in g.values()
    )
    proj = {
        w: {r["player_id"]: r.get("stats") or {} for r in rows}
        for w, rows in projections.items()
    }

    cases = []
    for pid, g in games.items():
        pos = pos_of[pid]
        touches = sum(x.get("rec_tgt", 0) + x.get("rush_att", 0) for x in g.values())
        if pos not in DEFAULT_RATES or touches < MIN_TOUCHES:
            continue
        for w in sorted(g):
            if w >= FIRST_WEEK:
                cases.append((pid, pos, w, score_line(g[w], scoring, pos)))

    def model(params: Params, pid: str, pos: str, w: int) -> float | None:
        line = expected_line(games[pid], w, rates[pos], params)
        return score_line(line.stats, scoring, pos) if line else None

    def errors(params: Params) -> list[float]:
        out = []
        for pid, pos, w, actual in cases:
            m = model(params, pid, pos, w)
            if m is not None:
                out.append(abs(m - actual))
        return out

    base = Params()
    hl_rows = [
        (f"{h:g}", f"{_mae(errors(replace(base, half_life=h))):.3f}")
        for h in HALF_LIVES
    ]
    td_rows = [
        (f"{a:g}", f"{_mae(errors(replace(base, actual_td_weight=a))):.3f}")
        for a in TD_WEIGHTS
    ]

    paired = []
    for pid, pos, w, actual in cases:
        line = proj.get(w, {}).get(pid)
        m = model(base, pid, pos, w)
        if line and m is not None:
            paired.append((m, score_line(line, scoring, pos), actual))
    mw_rows = [
        (
            f"{k:g}",
            f"{_mae([abs(k * m + (1 - k) * v - a) for m, v, a in paired]):.3f}",
        )
        for k in MODEL_WEIGHTS
    ]
    return Report(
        subject=f"Backtest: {len(cases)} player-weeks",
        lines=["Mean absolute error, league points per player-week."],
        tables=[
            Table("Half-life (weeks)", ("Half-life", "Error"), hl_rows),
            Table("Weight on actual TDs", ("Weight", "Error"), td_rows),
            Table(
                f"Model weight vs Sleeper ({len(paired)} pairs)",
                ("Model weight", "Error"),
                mw_rows,
            ),
        ],
    )
