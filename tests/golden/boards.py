"""Builders for hand-written golden boards.

Every id here is invented. No host id, no league id, no manager. A golden
case is a board a human can read in ten seconds and rule on without a
model, so the ids say what the player is for: `k-early`, `te-third`,
`wr-bye-clash`.

Numbers are plausible, not recorded. The point of a case is the ordering
and the gaps between rows, so the reasoning in `cases.py` holds whatever
season the real numbers come from.
"""

from __future__ import annotations

from vorpal.contracts import (
    Banner,
    BetweenTeam,
    BoardRow,
    DraftState,
    LeagueConfig,
    Need,
    Payload,
    RecentPick,
    Replacement,
    RosterPlayer,
    Slot,
    WeeklyCell,
)

# One start-one-flex league, the shape most of these cases run in.
STANDARD_SLOTS: tuple[Slot, ...] = (
    Slot.QB,
    Slot.RB,
    Slot.RB,
    Slot.WR,
    Slot.WR,
    Slot.TE,
    Slot.FLEX,
    Slot.K,
    Slot.DEF,
    Slot.BN,
    Slot.BN,
    Slot.BN,
    Slot.BN,
    Slot.BN,
    Slot.BN,
)

SUPERFLEX_SLOTS: tuple[Slot, ...] = (
    Slot.QB,
    Slot.RB,
    Slot.RB,
    Slot.WR,
    Slot.WR,
    Slot.TE,
    Slot.FLEX,
    Slot.SUPER_FLEX,
    Slot.K,
    Slot.BN,
    Slot.BN,
    Slot.BN,
    Slot.BN,
    Slot.BN,
)

LEGAL_SLOTS: dict[str, tuple[Slot, ...]] = {
    "QB": (Slot.QB, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
    "RB": (Slot.RB, Slot.FLEX, Slot.WRRB_FLEX, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
    "WR": (
        Slot.WR,
        Slot.FLEX,
        Slot.WRRB_FLEX,
        Slot.REC_FLEX,
        Slot.SUPER_FLEX,
        Slot.OP,
        Slot.BN,
    ),
    "TE": (Slot.TE, Slot.FLEX, Slot.REC_FLEX, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
    "K": (Slot.K, Slot.BN),
    "DEF": (Slot.DEF, Slot.BN),
}


def row(
    player_id: str,
    position: str,
    *,
    vols: float,
    adp: float,
    ecr: int | None,
    bye: int | None = 9,
    delta: float | None = None,
    points: float | None = None,
    gp: float | None = 17.0,
    ecr_min: int | None = None,
    ecr_max: int | None = None,
    ecr_std: float | None = 2.0,
) -> BoardRow:
    """One board row. `delta` defaults to half of `vols` — a roster-neutral pick.

    Cases that turn on roster fit set `delta` themselves: that is the
    number that knows how many tight ends you already hold, and `vols`
    is the one that does not.
    """
    return BoardRow(
        player_id=player_id,
        name=player_id,
        position=position,
        points=points if points is not None else 120.0 + vols,
        vols=vols,
        delta_starter_points=delta if delta is not None else vols / 2.0,
        adp=adp,
        legal_slots=LEGAL_SLOTS.get(position, (Slot.BN,)),
        bye=bye,
        gp=gp,
        ecr=ecr,
        ecr_min=ecr if ecr_min is None else ecr_min,
        ecr_max=ecr if ecr_max is None else ecr_max,
        ecr_std=ecr_std,
    )


def held(player_id: str, position: str, bye: int | None) -> RosterPlayer:
    return RosterPlayer(player_id=player_id, name=player_id, position=position, bye=bye)


def needs(**counts: tuple[int, int]) -> dict[str, Need]:
    """`needs(QB=(1, 1), WR=(0, 2))` -> filled / required per slot."""
    return {
        slot: Need(filled=filled, required=required)
        for slot, (filled, required) in counts.items()
    }


def config(
    *,
    teams: int = 12,
    rounds: int = 15,
    slots: tuple[Slot, ...] = STANDARD_SLOTS,
    slot: int | None = 4,
    scoring_summary: str = "PPR, 4pt pass TD",
    banners: tuple[Banner, ...] = (),
) -> LeagueConfig:
    return LeagueConfig(
        teams=teams,
        rounds=rounds,
        slots=slots,
        scoring={"rec": 1.0, "pass_td": 4.0, "rush_yd": 0.1, "rec_yd": 0.1},
        scoring_summary=scoring_summary,
        banners=banners or (Banner(code="board_capped", message="board is capped"),),
        slot=slot,
        draft_id="draft_golden",
        league_id=None,
        season="2025",
        draft_type="snake",
        status="drafting",
        pick_timer=60,
        reversal_round=0,
    )


def weekly_from_roster(
    roster: tuple[RosterPlayer, ...],
    slots: tuple[Slot, ...],
    per_week: float = 18.0,
) -> tuple[WeeklyCell, ...]:
    """An 18-week vector where a rostered player's bye zeroes his slot.

    Crude on purpose. The cases that read this one only need the bye
    weeks to look different from the other weeks.
    """
    from vorpal.evals._lineup import empty_startable_slots, legal_slots_for_position

    filled = tuple(
        (legal_slots_for_position(player.position), player.bye) for player in roster
    )
    cells: list[WeeklyCell] = []
    for week in range(1, 19):
        empty = empty_startable_slots(slots, filled, week)
        seated = len([s for s in slots if s is not Slot.BN]) - len(empty)
        cells.append(
            WeeklyCell(
                week=week,
                starter_points=round(seated * per_week, 1),
                empty=empty,
            )
        )
    return tuple(cells)


def payload(
    *,
    board: tuple[BoardRow, ...],
    hint: str,
    pick_no: int,
    roster: tuple[RosterPlayer, ...] = (),
    need_map: dict[str, Need] | None = None,
    cfg: LeagueConfig | None = None,
    recent: tuple[RecentPick, ...] = (),
    between: tuple[BetweenTeam, ...] | None = None,
    next_user_pick: int | None = None,
    weekly: tuple[WeeklyCell, ...] = (),
    replacement: dict[str, Replacement] | None = None,
) -> Payload:
    cfg = cfg if cfg is not None else config()
    if need_map is None:
        need_map = needs()
    picks_until_next = (
        None if next_user_pick is None else max(next_user_pick - pick_no, 0)
    )
    state = DraftState(
        pick_no=pick_no,
        user_roster=roster,
        needs=need_map,
        weekly=weekly,
        recent=recent,
        next_user_pick=next_user_pick,
        picks_until_next=picks_until_next,
        between=between,
    )
    if replacement is None:
        replacement = {
            position: Replacement(player_id=f"repl-{position.lower()}", points=100.0)
            for position in sorted({r.position for r in board})
        }
    return Payload(
        config=cfg,
        state=state,
        replacement=replacement,
        hint_argmax_vols=hint,
        board=board,
    )
