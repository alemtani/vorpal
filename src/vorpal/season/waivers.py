"""Waiver adds: rest-of-season lineup gain on your roster, with injuries."""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from typing import Any

from vorpal.season.context import LAST_WEEK, Season
from vorpal.season.forecast import assumed_returns
from vorpal.season.report import Report, Table, pts, signed
from vorpal.season.sim import SeasonSim

MIN_GAIN = 3.0
# A typical pickup adds about this many season points. Bid scales from it.
REF_GAIN = 20.0
BID_CAP = 0.4
DEFAULT_MEDIAN_BID = 20.0
UNAVAILABLE = frozenset({"Out", "IR", "Sus", "PUP"})
ADDS_PER_POSITION = 2
DROP_CANDIDATES = 3


def median_winning_bid(transactions: Iterable[Mapping[str, Any]]) -> float:
    bids = [
        t["settings"]["waiver_bid"]
        for t in transactions
        if t.get("type") == "waiver"
        and t.get("status") == "complete"
        and (t.get("settings") or {}).get("waiver_bid")
    ]
    return float(statistics.median(bids)) if bids else DEFAULT_MEDIAN_BID


def faab_bid(gain: float, median_bid: float, remaining: int) -> int:
    if gain <= 0 or remaining <= 0:
        return 0
    return max(1, min(round(median_bid * gain / REF_GAIN), int(BID_CAP * remaining)))


def _rate(s: Season, pid: str) -> float:
    rates = [f.rate for f in (s.now.get(pid), s.nxt.get(pid)) if f is not None]
    return max(rates, default=0.0)


def waiver_report(s: Season, sim: SeasonSim, median_bid: float) -> Report:
    roster = s.active(s.me)
    base = s.value(roster, sim)

    hold = [p for p in roster if p in s.now and s.now[p].rising]
    drop_cost = {
        p: base.total - s.value([q for q in roster if q != p], sim).total
        for p in roster
    }
    droppable = sorted((p for p in roster if p not in hold), key=drop_cost.get)

    pool = [p for p in s.free_agents() if s.now[p].status not in UNAVAILABLE]
    adds: list[str] = []
    for pos in ("QB", "RB", "WR", "TE"):
        ranked = sorted(
            (p for p in pool if s.now[p].position == pos), key=lambda p: -_rate(s, p)
        )
        adds.extend(ranked[:ADDS_PER_POSITION])

    settings = s.league.get("settings", {})
    used = int((s.me.get("settings") or {}).get("waiver_budget_used") or 0)
    remaining = int(settings.get("waiver_budget") or 0) - used

    results = []
    for add in adds:
        best = None
        for drop in droppable[:DROP_CANDIDATES]:
            new = [q for q in roster if q != drop] + [add]
            gain = s.value(new, sim).total - base.total
            if best is None or gain > best[0]:
                best = (gain, drop)
        if best is not None:
            results.append((best[0], add, best[1]))
    results.sort(reverse=True)

    lines: list[str] = []
    span = f"weeks {s.week}-{LAST_WEEK}"
    top = results[0] if results else None
    if top and top[0] >= MIN_GAIN:
        gain, add, drop = top
        bid = faab_bid(gain, median_bid, remaining)
        subject = f"Waivers: add {s.name(add)}, drop {s.name(drop)}, bid ${bid}"
        lines.append(
            f"Add {s.name(add)}, drop {s.name(drop)}. Bid ${bid}."
            f" {signed(gain)} lineup points over {span} (playoffs count 1.5x)."
        )
    else:
        subject = "Waivers: no move this week"
        best_line = (
            f" Best: {s.name(top[1])} for {s.name(top[2])}, {signed(top[0])}."
            if top
            else ""
        )
        lines.append(f"No add beats {pts(MIN_GAIN)} points.{best_line}")
    for p in hold:
        lines.append(f"Hold: {s.name(p)} (rising: snaps and touches up 2 weeks).")
    returns = assumed_returns(s.now, roster, s.week)
    if returns:
        lines.append(f"Assumed back: {returns}.")
    lines.append(
        f"FAAB left: ${remaining}. League median winning bid: ${median_bid:.0f}."
    )
    lines.extend(s.notes)

    add_rows = [
        (
            s.name(add),
            f"{s.now[add].position} {s.now[add].team}",
            pts(_rate(s, add)),
            s.name(drop),
            signed(gain),
            f"${faab_bid(gain, median_bid, remaining)}",
        )
        for gain, add, drop in results
    ]
    drop_rows = [
        (s.name(p), pts(drop_cost[p]), "hold (rising)" if p in hold else "")
        for p in sorted(roster, key=drop_cost.get)
    ]
    return Report(
        subject=subject,
        lines=lines,
        tables=[
            Table("Adds", ("Add", "Pos", "Proj/wk", "Drop", "Gain", "Bid"), add_rows),
            Table("Cost to drop", ("Player", "Season points lost", ""), drop_rows),
        ],
        key=f"{top[1]}|{top[2]}" if top else "",
    )
