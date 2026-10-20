"""Trade review from your side only: rest-of-season lineup points, with injuries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vorpal.season.context import Season
from vorpal.season.forecast import assumed_returns
from vorpal.season.report import Report, Table, signed
from vorpal.season.sim import SeasonSim

ACCEPT_GAIN = 5.0


def verdict(regular: float, playoffs: float) -> str:
    if regular < 0:
        return "DECLINE"
    if regular > ACCEPT_GAIN and playoffs >= 0:
        return "ACCEPT"
    return "CLOSE CALL"


def trade_report(
    s: Season,
    sim: SeasonSim,
    give: Sequence[str],
    get: Sequence[str],
    partner: str,
    market: Mapping[str, float],
) -> Report:
    roster = s.active(s.me)
    missing = [p for p in give if p not in s.me.get("players", [])]
    if missing:
        names = ", ".join(s.name(p) for p in missing)
        raise ValueError(f"not on your roster: {names}")

    base = s.value(roster, sim)
    new = [p for p in roster if p not in give] + list(get)
    dropped: list[str] = []
    while len(new) > len(roster):
        here = s.value(new, sim).total
        cut = min(
            (p for p in new if p not in get),
            key=lambda p: here - s.value([q for q in new if q != p], sim).total,
        )
        new.remove(cut)
        dropped.append(cut)
    after = s.value(new, sim)
    regular = after.regular - base.regular
    playoffs = after.playoffs - base.playoffs
    call = verdict(regular, playoffs)

    gives = " + ".join(s.name(p) for p in give)
    gets = " + ".join(s.name(p) for p in get)
    reg_span = f"weeks {s.week}-{s.playoff_start - 1}"
    lines = [
        f"{partner} offers {gets} for {gives}. {call}.",
        f"You: {signed(regular)} ({reg_span}), {signed(playoffs)} (playoffs).",
    ]
    if dropped:
        lines.append(f"You must drop {', '.join(s.name(p) for p in dropped)}.")
    returns = assumed_returns({**s.nxt, **s.now}, [*give, *get], s.week)
    if returns:
        lines.append(f"Assumed back: {returns}.")
    give_v = sum(market.get(p, 0) for p in give)
    get_v = sum(market.get(p, 0) for p in get)
    lines.append(f"Market (FantasyCalc): you give {give_v:.0f}, get {get_v:.0f}.")
    deadline = s.league.get("settings", {}).get("trade_deadline")
    if deadline:
        lines.append(f"Trade deadline: week {deadline}.")
    lines.extend(s.notes)

    def row(p: str, side: str) -> tuple[str, ...]:
        f = s.now.get(p) or s.nxt.get(p)
        rate = f"{max(f.rate, 0):.1f}" if f else "-"
        return (
            side,
            s.name(p),
            rate,
            f.status or "" if f else "",
            str(market.get(p, "")),
        )

    table = Table(
        "Players",
        ("Side", "Player", "Proj/wk", "Status", "Market"),
        [row(p, "give") for p in give] + [row(p, "get") for p in get],
    )
    return Report(
        subject=f"Trade from {partner}: {call} ({signed(regular)})",
        lines=lines,
        tables=[table],
        key="|".join(sorted(give) + ["for"] + sorted(get)),
    )
