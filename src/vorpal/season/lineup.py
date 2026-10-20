"""This week's lineup: starts, sits, IR moves, win chance, late-game risk."""

from __future__ import annotations

import math
from collections.abc import Sequence

from vorpal.season.blend import FULL_ROLE_GAMES
from vorpal.season.context import Season
from vorpal.season.forecast import Forecast, return_label
from vorpal.season.report import Report, Table, pts
from vorpal.season.sim import SLOT_POSITIONS, best_lineup

# Weekly points spread: sigma = 0.45 x projection (fit on 2025 game logs).
SIGMA_RATIO = 0.45

_IR_SETTING = {
    "Out": "reserve_allow_out",
    "Doubtful": "reserve_allow_doubtful",
    "Sus": "reserve_allow_sus",
    "NA": "reserve_allow_na",
}


def win_chance(mine: Sequence[float], theirs: Sequence[float]) -> float:
    """P(my total > theirs), normal model, independent players."""
    var = sum((SIGMA_RATIO * x) ** 2 for x in (*mine, *theirs))
    if var == 0:
        return 0.5
    z = (sum(mine) - sum(theirs)) / math.sqrt(var)
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _ir_eligible(status: str | None, settings: dict) -> bool:
    if status == "IR":
        return True
    key = _IR_SETTING.get(status or "")
    return bool(key and settings.get(key))


def _model_cell(f: Forecast) -> str:
    """Model points, marked when the role check leaves them out of the blend."""
    if f.model is None:
        return "-"
    if f.role_games == 0:
        return f"{pts(f.model)} (unused: fill-in role)"
    if f.role_games < FULL_ROLE_GAMES:
        return f"{pts(f.model)} (part: {f.role_games} role games)"
    return pts(f.model)


def _why_sit(s: Season, pid: str) -> str:
    f = s.now[pid]
    if not f.plays:
        return f"{f.team} bye" if f.team else "no team"
    if f.points == 0:
        return f.status or "out"
    return f"{pts(f.points)} projected"


def lineup_report(
    s: Season, opponent: Sequence[str] = (), opponent_name: str = ""
) -> Report:
    me = s.me
    active = s.active(me)
    points = {p: s.now[p].points if p in s.now else 0.0 for p in active}
    positions = s.positions
    best_total, best = best_lineup(points, positions, s.slots)
    best_ids = [p for _, p in best]
    current = [p for p in me.get("starters") or [] if p in points]
    current_total = sum(points[p] for p in current)

    starts = [p for p in best_ids if p not in current]
    sits = [p for p in current if p not in best_ids]
    lines: list[str] = []
    for p in sorted(starts, key=lambda p: -points[p]):
        lines.append(f"START {s.name(p)} ({pts(points[p])})")
    for p in sits:
        lines.append(f"SIT {s.name(p)} ({_why_sit(s, p)})")

    settings = s.league.get("settings", {})
    free_ir = int(settings.get("reserve_slots") or 0) - len(me.get("reserve") or [])
    to_ir = [
        p
        for p in active
        if p in s.now and _ir_eligible(s.now[p].status, settings) and p not in best_ids
    ]
    if free_ir > 0 and to_ir:
        names = ", ".join(f"{s.name(p)} ({s.now[p].status})" for p in to_ir)
        lines.append(f"Move to IR ({free_ir} open): {names}. Frees a bench spot.")
    for p in me.get("reserve") or []:
        f = s.now.get(p)
        if f is not None and not _ir_eligible(f.status, settings):
            lines.append(
                f"Activate {s.name(p)} from IR (status now {f.status or 'healthy'})."
            )

    # Late game: a starter on the week's last day with no bench player that late.
    days = {
        p: s.dates.get((s.now[p].team or "", s.week), "") for p in active if p in s.now
    }
    last_day = max((d for d in days.values() if d), default="")
    bench = [p for p in active if p not in best_ids and points[p] > 0]
    for slot, p in best:
        if days.get(p) != last_day or not last_day:
            continue
        late_backup = [
            b
            for b in bench
            if days.get(b) == last_day and positions.get(b) in SLOT_POSITIONS[slot]
        ]
        if not late_backup:
            early = max(
                (b for b in bench if positions.get(b) in SLOT_POSITIONS[slot]),
                key=lambda b: points[b],
                default=None,
            )
            alt = ""
            if early:
                cost = pts(points[p] - points[early])
                alt = f" Benching him for {s.name(early)} costs {cost}."
            lines.append(
                f"Late game: {s.name(p)} ({slot}) plays {last_day} with no backup"
                f" that day. If he is ruled out late, that slot scores 0.{alt}"
            )

    if opponent:
        opp_points = {p: s.now[p].points for p in opponent if p in s.now}
        opp_total, opp_best = best_lineup(opp_points, positions, s.slots)
        chance = win_chance(
            [points[p] for p in best_ids], [opp_points[p] for _, p in opp_best]
        )
        lines.append(
            f"Win chance vs {opponent_name}: {chance:.0%}"
            f" ({pts(best_total)} vs {pts(opp_total)})."
        )
    lines.extend(s.notes)

    n = len(starts)
    subject = (
        f"Week {s.week} lineup: {n} change{'s' if n != 1 else ''}"
        f" ({pts(current_total)} -> {pts(best_total)})"
        if n
        else f"Week {s.week} lineup: no changes ({pts(best_total)})"
    )
    rows = [
        (
            slot,
            s.name(p),
            s.now[p].team or "",
            pts(points[p]),
            _model_cell(s.now[p]),
            " / ".join(f"{k} {pts(v)}" for k, v in sorted(s.now[p].vendors.items())),
            s.now[p].status or "",
        )
        for slot, p in best
    ]
    table = Table(
        "Best lineup",
        ("Slot", "Player", "Team", "Proj", "Model", "Vendors", "Status"),
        rows,
    )
    sat = sorted((p for p in active if p not in best_ids), key=lambda p: -points[p])
    bench_rows = [
        (s.name(p), pts(points[p]), "" if points[p] else _why_sit(s, p)) for p in sat
    ]
    ir_rows = [
        (
            s.name(p),
            " ".join(x for x in (f.status, f.injury and f"({f.injury})") if x)
            or "healthy",
            pts(f.rate),
            return_label(f, s.week),
        )
        for p in me.get("reserve") or []
        if (f := s.now.get(p)) is not None
    ]
    moves = [ln for ln in lines if ln.startswith(("Move", "Activate"))]
    return Report(
        subject=subject,
        lines=lines,
        tables=[
            table,
            Table("Bench", ("Player", "Proj", "Why"), bench_rows),
            Table("IR", ("Player", "Status", "Proj if active", "Back"), ir_rows),
        ],
        key="|".join([*sorted(best_ids), *moves]),
    )
