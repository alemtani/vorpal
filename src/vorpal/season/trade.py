"""Trade review from your side only: rest-of-season lineup points, with injuries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vorpal.season.context import LAST_WEEK, Season
from vorpal.season.forecast import assumed_returns
from vorpal.season.report import DAMPED_NOTE, Report, Table, pts, signed
from vorpal.season.sim import SeasonSim

ACCEPT_GAIN = 5.0
# Healthy-lineup vs simulated playoff gain gap worth explaining.
DEPTH_GAP = 2.0
# Free agents tried for each roster spot a trade opens.
FILL_CANDIDATES = 6
UNAVAILABLE = frozenset({"Out", "IR", "Sus", "PUP"})


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
    base_roster = list(roster)
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
    added: list[str] = []
    pool = sorted(
        (p for p in s.free_agents() if s.now[p].status not in UNAVAILABLE),
        key=lambda p: -s.now[p].rate,
    )[:FILL_CANDIDATES]
    while len(new) < len(roster) and pool:
        pick = max(pool, key=lambda p: s.value([*new, p], sim).total)
        pool.remove(pick)
        new.append(pick)
        added.append(pick)
    if added:
        # Without the trade you could still add them by cutting your weakest
        # players. Compare against that, not against standing pat.
        here = base.total
        cuts = sorted(
            roster,
            key=lambda p: here - s.value([q for q in roster if q != p], sim).total,
        )[: len(added)]
        alt_roster = [*(p for p in roster if p not in cuts), *added]
        alt = s.value(alt_roster, sim)
        if alt.total > base.total:
            base, base_roster = alt, alt_roster
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
    if added:
        names = ", ".join(s.name(p) for p in added)
        lines.append(f"Counts adding {names} from free agency to the open spot.")
        swapped = [p for p in roster if p not in base_roster]
        if swapped:
            out = ", ".join(s.name(p) for p in swapped)
            lines.append(
                f"'Now' also adds {names} (dropping {out}): you can make that"
                " move without the trade."
            )
    returns = assumed_returns({**s.nxt, **s.now}, [*give, *get], s.week)
    if returns:
        lines.append(f"Assumed back: {returns}.")
    give_v = sum(market.get(p, 0) for p in give)
    get_v = sum(market.get(p, 0) for p in get)
    lines.append(f"Market (FantasyCalc): you give {give_v:.0f}, get {get_v:.0f}.")
    deadline = s.league.get("settings", {}).get("trade_deadline")
    if deadline:
        lines.append(f"Trade deadline: week {deadline}.")

    # Deterministic lineups, damped projections: what changes slot by slot.
    weekly = []
    for w in range(s.week, LAST_WEEK + 1):
        b_total, b_start = s.lineup_for(base_roster, w)
        a_total, a_start = s.lineup_for(new, w)
        weekly.append((w, b_total, b_start, a_total, a_start))
    w0, b0, b_start0, a0, a_start0 = weekly[0]
    regular_weeks = [x for x in weekly if x[0] < s.playoff_start]
    avg = sum(a - b for _, b, _, a, _ in regular_weeks) / max(len(regular_weeks), 1)
    lines.insert(
        2,
        f"Your lineup: week {w0} {pts(b0)} -> {pts(a0)} ({signed(a0 - b0)});"
        f" {signed(avg)} a week through week {s.playoff_start - 1}.",
    )
    # The trade as like-for-like swaps (same position first), each measured on
    # the roster left by the step before. The steps add up to the total.
    reg = [w for w, *_ in regular_weeks]

    def avg_lineup(ids: Sequence[str]) -> float:
        return sum(s.lineup_for(ids, w)[0] for w in reg) / max(len(reg), 1)

    def rate(p: str) -> float:
        f = s.now.get(p) or s.nxt.get(p)
        return f.rate if f else 0.0

    outs = sorted(give, key=rate, reverse=True)
    ins = sorted(get, key=rate, reverse=True)
    plan: list[tuple[list[str], list[str]]] = []
    for g in list(ins):
        same = next((o for o in outs if s.positions.get(o) == s.positions.get(g)), None)
        if same is not None:
            plan.append(([same], [g]))
            outs.remove(same)
            ins.remove(g)
    if outs or ins:
        plan.append((outs, ins))
    running = list(base_roster)
    steps = []
    for out, inn in plan:
        nxt_roster = [p for p in running if p not in out] + inn
        steps.append((out, inn, avg_lineup(nxt_roster) - avg_lineup(running)))
        running = nxt_roster
    fill_in = [p for p in new if p not in running]
    fill_out = [p for p in running if p not in new]
    if fill_in or fill_out:
        steps.append((fill_out, fill_in, avg_lineup(new) - avg_lineup(running)))

    def step_name(out: list[str], inn: list[str]) -> str:
        i = " + ".join(s.name(p) for p in inn)
        if not out:
            kept = all(p in roster for p in inn)
            return f"Open roster spot: {'keep' if kept else 'add'} {i}"
        o = " + ".join(s.name(p) for p in out)
        return f"{o} -> {i}" if inn else f"Drop {o}"

    def flip_at(p: str) -> str:
        """Weekly average above which losing him turns the verdict to DECLINE."""
        f = s.now.get(p) or s.nxt.get(p)
        lineup_weeks = sum(
            1 for w in reg if p in {q for _, q in s.lineup_for(base_roster, w)[1]}
        )
        if f is None or regular <= 0 or not lineup_weeks:
            return ""
        return pts(f.rate + regular / lineup_weeks)

    flips = {p: flip_at(p) for p in give}
    closest = min(
        (p for p in give if flips[p]),
        key=lambda p: float(flips[p]) - (s.now.get(p) or s.nxt[p]).rate,
        default=None,
    )
    if closest is not None:
        f = s.now.get(closest) or s.nxt[closest]
        lines.insert(
            3,
            f"Closest call: {s.name(closest)}. DECLINE if he averages more than"
            f" {flips[closest]} a week (damped: {pts(f.rate)}).",
        )
    healthy = sum(a - b for w, b, _, a, _ in weekly if w >= s.playoff_start)
    if healthy - playoffs > DEPTH_GAP:
        lines.append(
            f"Playoffs: {signed(healthy)} if nobody gets hurt, {signed(playoffs)}"
            " with injuries simulated. The difference is bench depth."
        )
    lines.extend(s.notes)
    lines.append(DAMPED_NOTE)

    def by_slot(start: list[tuple[str, str]]) -> list[str | None]:
        """Starters lined up with the league's slots; None for an empty slot."""
        left = list(start)
        out: list[str | None] = []
        for slot in s.slots:
            hit = next((x for x in left if x[0] == slot), None)
            if hit:
                left.remove(hit)
            out.append(hit[1] if hit else None)
        return out

    def cell(p: str | None) -> tuple[str, str]:
        return (s.name(p), pts(s.lineup_points(p, w0))) if p else ("-", "")

    slot_rows = [
        (slot, *cell(b), *cell(a), "" if b == a else "changed")
        for slot, b, a in zip(
            s.slots, by_slot(b_start0), by_slot(a_start0), strict=True
        )
    ]

    def names(ids: set[str]) -> str:
        return ", ".join(sorted(s.name(p) for p in ids)) or "-"

    week_rows = []
    for w, b, b_start, a, a_start in weekly:
        b_ids, a_ids = {p for _, p in b_start}, {p for _, p in a_start}
        week_rows.append(
            (
                f"{w}{' (playoffs)' if w >= s.playoff_start else ''}",
                pts(b),
                pts(a),
                signed(a - b),
                names(a_ids - b_ids),
                names(b_ids - a_ids),
            )
        )

    def row(p: str, side: str) -> tuple[str, ...]:
        f = s.now.get(p) or s.nxt.get(p)
        rate = pts(max(f.rate, 0)) if f else "-"
        return (
            side,
            s.name(p),
            rate,
            f.status or "" if f else "",
            str(market.get(p, "")),
        )

    table = Table(
        "Players",
        ("Side", "Player", "Damped/wk", "Status", "Market"),
        [row(p, "give") for p in give] + [row(p, "get") for p in get],
    )
    return Report(
        subject=f"Trade from {partner}: {call} ({signed(regular)})",
        lines=lines,
        tables=[
            Table(
                f"Week {w0} lineup: now vs after the trade",
                ("Slot", "Now", "Pts", "After", "Pts", ""),
                slot_rows,
            ),
            Table(
                "Week by week (damped projections, no new injuries)",
                ("Week", "Now", "After", "Change", "Starts", "Leaves lineup"),
                week_rows,
            ),
            Table(
                f"The trade in steps (lineup points a week, weeks {s.week}"
                f"-{s.playoff_start - 1}, damped, nobody newly hurt)",
                ("Swap", "Per week"),
                [(step_name(o, i), signed(v)) for o, i, v in steps]
                + [("Total", signed(sum(v for *_, v in steps)))],
            ),
            Table(
                "If a player you give beats his projection",
                ("Player", "Damped", "DECLINE if he averages over"),
                [(s.name(p), pts(rate(p)), flips[p]) for p in give if flips[p]],
            ),
            table,
        ],
        key="|".join(sorted(give) + ["for"] + sorted(get)),
    )
