"""The golden set: hand-built boards with a human verdict on each.

A case is a board, a forbid set, a require set, and one sentence saying
why. The sentence is the whole point. If a verdict cannot be defended in
one sentence to somebody who has never seen this repository, it is a
taste and it does not belong here.

Two rules held every case to:

- **Forbid is for picks nobody needs a model to rule on.** A kicker in
  round two. A third tight end that cannot enter a lineup. Never "the
  player I would not have taken".
- **Require asks whether the model saw the right players**, not whether
  it ranked them our way. Naming one as an alternative passes.

Ids are invented and readable. `k-early` is a kicker. `te-third` is the
tight end you already have two of. Nothing here came off a league.

Count and coverage: `tests/golden/README.md`. It is a small set and the
spec (section 8) says plainly that this is the main limit on the eval.
"""

from __future__ import annotations

from dataclasses import dataclass

from boards import (
    SUPERFLEX_SLOTS,
    config,
    held,
    needs,
    payload,
    row,
    weekly_from_roster,
)

from vorpal.contracts import BetweenTeam, Payload, RecentPick
from vorpal.evals import GateFixtures


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One board, one verdict, one sentence of reasoning.

    `situation` names the shape of the board, so the sampler's hostile
    states can be checked off against the set. `forbid` may be empty:
    that means a human looked and forbade nobody, which is different
    from nobody having looked.
    """

    name: str
    situation: str
    payload: Payload
    forbid: frozenset[str]
    require: frozenset[str]
    why: str

    def fixtures(self) -> GateFixtures:
        """The two golden gates, and nothing else. Other gates stay unperformed."""
        return GateFixtures(forbid=self.forbid, require=self.require)


def snake_pick(teams: int, slot: int, round_no: int) -> int:
    """Pick number for a seat in a snake draft with no reversal round."""
    base = (round_no - 1) * teams
    return base + (slot if round_no % 2 else teams + 1 - slot)


# --- forbid cases ------------------------------------------------------


def _kicker_round_two() -> GoldenCase:
    board = (
        row("rb-a", "RB", vols=62.0, adp=18.0, ecr=16, bye=10),
        row("wr-a", "WR", vols=58.0, adp=20.0, ecr=19, bye=7),
        row("wr-b", "WR", vols=50.0, adp=24.0, ecr=23, bye=5),
        row("te-a", "TE", vols=31.0, adp=30.0, ecr=29, bye=12),
        row("qb-a", "QB", vols=24.0, adp=35.0, ecr=34, bye=6),
        row("k-early", "K", vols=3.0, adp=150.0, ecr=185, bye=14),
    )
    return GoldenCase(
        name="kicker_round_two",
        situation="early_round",
        payload=payload(
            board=board,
            hint="rb-a",
            pick_no=snake_pick(12, 4, 2),
            next_user_pick=snake_pick(12, 4, 3),
            roster=(held("rb-held", "RB", 8),),
            need_map=needs(
                QB=(0, 1),
                RB=(1, 2),
                WR=(0, 2),
                TE=(0, 1),
                FLEX=(0, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"k-early"}),
        require=frozenset({"rb-a", "wr-a"}),
        why=(
            "The best kicker left is worth three points over the last kicker "
            "anybody will draft, and the best receiver left is worth fifty-eight "
            "over his replacement; spending pick 21 on the three-point one is "
            "not a judgement call."
        ),
    )


def _third_te_while_wr_empty() -> GoldenCase:
    board = (
        row("te-third", "TE", vols=24.0, adp=70.0, ecr=66, bye=11, delta=0.0),
        row("wr-a", "WR", vols=22.0, adp=66.0, ecr=63, bye=7, delta=22.0),
        row("wr-b", "WR", vols=18.0, adp=72.0, ecr=70, bye=13, delta=18.0),
        row("rb-c", "RB", vols=15.0, adp=75.0, ecr=74, bye=6, delta=9.0),
    )
    return GoldenCase(
        name="third_te_while_wr_empty",
        situation="roster_fit",
        payload=payload(
            board=board,
            hint="te-third",
            pick_no=snake_pick(12, 4, 6),
            next_user_pick=snake_pick(12, 4, 7),
            roster=(
                held("qb-held", "QB", 6),
                held("rb-held-1", "RB", 8),
                held("rb-held-2", "RB", 5),
                held("te-held-1", "TE", 12),
                held("te-held-2", "TE", 9),
            ),
            need_map=needs(
                QB=(1, 1),
                RB=(2, 2),
                WR=(0, 2),
                TE=(1, 1),
                FLEX=(1, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"te-third"}),
        require=frozenset({"wr-a", "wr-b"}),
        why=(
            "The league starts one tight end and two are already rostered, so a "
            "third can never enter the lineup, while both receiver slots are "
            "empty and either receiver on this board starts in week one."
        ),
    )


def _defense_round_three() -> GoldenCase:
    board = (
        row("rb-b", "RB", vols=48.0, adp=27.0, ecr=26, bye=9),
        row("wr-b", "WR", vols=45.0, adp=29.0, ecr=28, bye=6),
        row("te-b", "TE", vols=26.0, adp=33.0, ecr=31, bye=7),
        row("def-early", "DEF", vols=4.0, adp=120.0, ecr=140, bye=11),
    )
    return GoldenCase(
        name="defense_round_three",
        situation="early_round",
        payload=payload(
            board=board,
            hint="rb-b",
            pick_no=snake_pick(10, 8, 3),
            next_user_pick=snake_pick(10, 8, 4),
            cfg=config(teams=10, slot=8),
            roster=(held("rb-held", "RB", 8), held("wr-held", "WR", 5)),
            need_map=needs(
                QB=(0, 1),
                RB=(1, 2),
                WR=(1, 2),
                TE=(0, 1),
                FLEX=(0, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"def-early"}),
        require=frozenset({"rb-b", "wr-b"}),
        why=(
            "Defenses are interchangeable enough that the first one off the board "
            "is worth four points over the last, and this board still holds "
            "starting running backs worth forty-eight."
        ),
    )


def _backup_qb_in_one_qb_league() -> GoldenCase:
    board = (
        row("rb-d", "RB", vols=38.0, adp=52.0, ecr=50, bye=7),
        row("wr-c", "WR", vols=35.0, adp=55.0, ecr=53, bye=10),
        row("qb-backup", "QB", vols=30.0, adp=58.0, ecr=57, bye=9, delta=0.0),
        row("te-c", "TE", vols=20.0, adp=61.0, ecr=60, bye=5),
    )
    return GoldenCase(
        name="backup_qb_in_one_qb_league",
        situation="roster_fit",
        payload=payload(
            board=board,
            hint="rb-d",
            pick_no=snake_pick(12, 4, 5),
            next_user_pick=snake_pick(12, 4, 6),
            roster=(
                held("qb-held", "QB", 6),
                held("rb-held", "RB", 8),
                held("wr-held", "WR", 5),
                held("te-held", "TE", 12),
            ),
            need_map=needs(
                QB=(1, 1),
                RB=(1, 2),
                WR=(1, 2),
                TE=(1, 1),
                FLEX=(0, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"qb-backup"}),
        require=frozenset({"rb-d", "wr-c"}),
        why=(
            "One quarterback slot, one quarterback rostered, and no superflex: a "
            "second quarterback has no week in which he can start, while a "
            "running back and a receiver slot are both still open."
        ),
    )


def _bye_stack() -> GoldenCase:
    roster = (
        held("qb-held", "QB", 9),
        held("rb-held-1", "RB", 9),
        held("rb-held-2", "RB", 4),
        held("wr-held", "WR", 9),
        held("te-held", "TE", 7),
    )
    board = (
        row("wr-bye-clash", "WR", vols=30.0, adp=80.0, ecr=78, bye=9, delta=12.0),
        row("wr-bye-clear", "WR", vols=29.0, adp=82.0, ecr=80, bye=5, delta=29.0),
        row("rb-e", "RB", vols=21.0, adp=85.0, ecr=84, bye=11),
    )
    return GoldenCase(
        name="bye_stack",
        situation="bye_stack",
        payload=payload(
            board=board,
            hint="wr-bye-clash",
            pick_no=snake_pick(12, 4, 7),
            next_user_pick=snake_pick(12, 4, 8),
            roster=roster,
            weekly=weekly_from_roster(roster, config().slots),
            need_map=needs(
                QB=(1, 1),
                RB=(2, 2),
                WR=(1, 2),
                TE=(1, 1),
                FLEX=(0, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"wr-bye-clash"}),
        require=frozenset({"wr-bye-clear"}),
        why=(
            "The quarterback, a running back and the only rostered receiver are "
            "all off in week 9 already; a fourth week-9 player books a receiver "
            "slot that stays empty that week when an equal receiver on bye 5 is "
            "one row down."
        ),
    )


# --- require cases -----------------------------------------------------


def _superflex_qb_run() -> GoldenCase:
    board = (
        row("qb-sf-a", "QB", vols=71.0, adp=50.0, ecr=44, bye=10),
        row("qb-sf-b", "QB", vols=68.0, adp=53.0, ecr=47, bye=6),
        row("rb-f", "RB", vols=45.0, adp=51.0, ecr=45, bye=9),
        row("wr-f", "WR", vols=44.0, adp=54.0, ecr=48, bye=7),
        row("te-f", "TE", vols=30.0, adp=60.0, ecr=58, bye=12),
    )
    between = tuple(
        BetweenTeam(
            slot=other,
            roster={"QB": 1 if other in (2, 5) else 0, "RB": 2, "WR": 2},
            needs=needs(
                QB=(1, 1),
                SUPER_FLEX=(1, 1) if other in (2, 5) else (0, 1),
            ),
        )
        for other in (8, 9, 10, 11, 12, 1, 2, 3, 4, 5)
    )
    return GoldenCase(
        name="superflex_qb_run",
        situation="superflex_scarcity",
        payload=payload(
            board=board,
            hint="qb-sf-a",
            pick_no=snake_pick(12, 7, 5),
            next_user_pick=snake_pick(12, 7, 6),
            cfg=config(teams=12, rounds=18, slots=SUPERFLEX_SLOTS, slot=7),
            roster=(
                held("qb-held", "QB", 8),
                held("rb-held", "RB", 5),
                held("wr-held-1", "WR", 7),
                held("wr-held-2", "WR", 11),
            ),
            need_map=needs(
                QB=(1, 1),
                RB=(1, 2),
                WR=(2, 2),
                TE=(0, 1),
                FLEX=(0, 1),
                SUPER_FLEX=(0, 1),
                K=(0, 1),
            ),
            between=between,
        ),
        forbid=frozenset(),
        require=frozenset({"qb-sf-a", "qb-sf-b"}),
        why=(
            "Two startable quarterbacks are left, eight of the ten teams picking "
            "before our next turn still have an empty superflex, so both are gone "
            "by then and the superflex slot is empty for the season."
        ),
    )


def _empty_starter_late() -> GoldenCase:
    board = (
        row("wr-depth", "WR", vols=12.0, adp=170.0, ecr=168, bye=8, delta=0.0),
        row("rb-depth", "RB", vols=10.0, adp=172.0, ecr=171, bye=13, delta=0.0),
        row("k-a", "K", vols=5.0, adp=166.0, ecr=175, bye=14, delta=118.0),
        row("k-b", "K", vols=4.0, adp=175.0, ecr=180, bye=6, delta=115.0),
        row("def-a", "DEF", vols=4.0, adp=168.0, ecr=178, bye=10, delta=110.0),
    )
    return GoldenCase(
        name="empty_starter_late",
        situation="empty_starter_late",
        payload=payload(
            board=board,
            hint="wr-depth",
            pick_no=snake_pick(12, 4, 14),
            next_user_pick=snake_pick(12, 4, 15),
            roster=(
                held("qb-held", "QB", 6),
                held("rb-held-1", "RB", 8),
                held("rb-held-2", "RB", 5),
                held("wr-held-1", "WR", 7),
                held("wr-held-2", "WR", 11),
                held("te-held", "TE", 12),
                held("flex-held", "WR", 9),
            ),
            need_map=needs(
                QB=(1, 1),
                RB=(2, 2),
                WR=(2, 2),
                TE=(1, 1),
                FLEX=(1, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"wr-depth", "rb-depth"}),
        require=frozenset({"k-a", "k-b", "def-a"}),
        why=(
            "Two starting slots are empty and exactly two picks remain, so any "
            "pick that is not a kicker or a defense leaves a slot scoring zero "
            "every week of the season."
        ),
    )


def _second_kicker_last_rounds() -> GoldenCase:
    board = (
        row("wr-depth", "WR", vols=12.0, adp=170.0, ecr=168, bye=8, delta=6.0),
        row("rb-depth", "RB", vols=10.0, adp=172.0, ecr=171, bye=13, delta=5.0),
        row("k-b", "K", vols=4.0, adp=175.0, ecr=180, bye=6, delta=0.0),
    )
    return GoldenCase(
        name="second_kicker_last_rounds",
        situation="empty_starter_late",
        payload=payload(
            board=board,
            hint="wr-depth",
            pick_no=snake_pick(12, 4, 14),
            next_user_pick=snake_pick(12, 4, 15),
            roster=(
                held("qb-held", "QB", 6),
                held("rb-held-1", "RB", 8),
                held("rb-held-2", "RB", 5),
                held("wr-held-1", "WR", 7),
                held("wr-held-2", "WR", 11),
                held("te-held", "TE", 12),
                held("flex-held", "WR", 9),
                held("k-held", "K", 10),
                held("def-held", "DEF", 14),
            ),
            need_map=needs(
                QB=(1, 1),
                RB=(2, 2),
                WR=(2, 2),
                TE=(1, 1),
                FLEX=(1, 1),
                K=(1, 1),
                DEF=(1, 1),
            ),
        ),
        forbid=frozenset({"k-b"}),
        require=frozenset({"wr-depth", "rb-depth"}),
        why=(
            "Same two rounds and the same board as the case above, with the "
            "kicker slot filled: a second kicker cannot enter a lineup in any "
            "week, and the receiver can the first time somebody ahead of him is "
            "on bye."
        ),
    )


def _te_cliff() -> GoldenCase:
    board = (
        row("te-elite", "TE", vols=55.0, adp=28.0, ecr=26, bye=10, delta=55.0),
        row("rb-g", "RB", vols=50.0, adp=27.0, ecr=25, bye=6, delta=30.0),
        row("wr-g", "WR", vols=48.0, adp=30.0, ecr=29, bye=9, delta=28.0),
        row("te-next", "TE", vols=18.0, adp=44.0, ecr=42, bye=7, delta=18.0),
    )
    return GoldenCase(
        name="te_cliff",
        situation="tier_cliff",
        payload=payload(
            board=board,
            hint="te-elite",
            pick_no=snake_pick(12, 4, 3),
            next_user_pick=snake_pick(12, 4, 4),
            roster=(held("rb-held", "RB", 8), held("wr-held", "WR", 5)),
            need_map=needs(
                QB=(0, 1),
                RB=(1, 2),
                WR=(1, 2),
                TE=(0, 1),
                FLEX=(0, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"te-next"}),
        require=frozenset({"te-elite"}),
        why=(
            "The gap from the first tight end to the second is thirty-seven "
            "points and the gap at every other position on this board is two, so "
            "the tight end slot is where the pick buys the most and the second "
            "tight end is a third-round price for a replacement."
        ),
    )


def _position_run() -> GoldenCase:
    recent = tuple(
        RecentPick(player_id=f"wr-gone-{index}", position="WR", pick_no=pick)
        for index, pick in enumerate((40, 41, 42, 43, 44))
    )
    board = (
        row("wr-run-a", "WR", vols=41.0, adp=46.0, ecr=44, bye=6, delta=41.0),
        row("wr-run-b", "WR", vols=39.0, adp=48.0, ecr=47, bye=11, delta=39.0),
        row("rb-h", "RB", vols=36.0, adp=47.0, ecr=45, bye=9, delta=20.0),
        row("wr-after-cliff", "WR", vols=14.0, adp=58.0, ecr=56, bye=7, delta=14.0),
        row("te-h", "TE", vols=22.0, adp=52.0, ecr=51, bye=13, delta=22.0),
    )
    return GoldenCase(
        name="position_run",
        situation="position_run",
        payload=payload(
            board=board,
            hint="wr-run-a",
            pick_no=snake_pick(12, 4, 4),
            next_user_pick=snake_pick(12, 4, 5),
            roster=(held("rb-held", "RB", 8), held("qb-held", "QB", 6)),
            need_map=needs(
                QB=(1, 1),
                RB=(1, 2),
                WR=(0, 2),
                TE=(0, 1),
                FLEX=(0, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
            recent=recent,
        ),
        forbid=frozenset(),
        require=frozenset({"wr-run-a", "wr-run-b"}),
        why=(
            "Five of the last six picks were receivers, both of our receiver "
            "slots are empty, and the drop from the second receiver left to the "
            "third is twenty-five points, so the run ends this tier before our "
            "next turn."
        ),
    )


def _vols_compressed() -> GoldenCase:
    board = (
        row("flat-a", "RB", vols=1.4, adp=176.0, ecr=170, bye=9, ecr_std=1.5),
        row(
            "wide-b",
            "WR",
            vols=1.1,
            adp=180.0,
            ecr=174,
            bye=6,
            ecr_min=96,
            ecr_max=205,
            ecr_std=32.0,
        ),
        row("flat-c", "TE", vols=0.8, adp=182.0, ecr=176, bye=11, ecr_std=2.0),
        row(
            "wide-d",
            "RB",
            vols=0.3,
            adp=184.0,
            ecr=179,
            bye=13,
            ecr_min=101,
            ecr_max=210,
            ecr_std=29.0,
        ),
    )
    return GoldenCase(
        name="vols_compressed",
        situation="vols_compressed",
        payload=payload(
            board=board,
            hint="flat-a",
            pick_no=snake_pick(14, 9, 13),
            next_user_pick=snake_pick(14, 9, 14),
            cfg=config(teams=14, slot=9),
            roster=(
                held("qb-held", "QB", 6),
                held("rb-held-1", "RB", 8),
                held("rb-held-2", "RB", 5),
                held("wr-held-1", "WR", 7),
                held("wr-held-2", "WR", 11),
                held("te-held", "TE", 12),
                held("flex-held", "WR", 9),
                held("k-held", "K", 10),
                held("def-held", "DEF", 14),
            ),
            need_map=needs(
                QB=(1, 1),
                RB=(2, 2),
                WR=(2, 2),
                TE=(1, 1),
                FLEX=(1, 1),
                K=(1, 1),
                DEF=(1, 1),
            ),
        ),
        forbid=frozenset(),
        require=frozenset({"wide-b", "wide-d"}),
        why=(
            "Every player left is within one and a half points of replacement, so "
            "VOLS has stopped separating them, and the only rows with an expert "
            "who ranks them a hundred places higher are the only rows that can "
            "still win a week."
        ),
    )


def _seat_unknown() -> GoldenCase:
    board = (
        row("rb-i", "RB", vols=44.0, adp=25.0, ecr=24, bye=9),
        row("wr-i", "WR", vols=42.0, adp=26.0, ecr=25, bye=6),
        row("te-i", "TE", vols=27.0, adp=32.0, ecr=30, bye=12),
        row("def-unknown-seat", "DEF", vols=4.0, adp=118.0, ecr=138, bye=11),
    )
    return GoldenCase(
        name="seat_unknown",
        situation="seat_unknown",
        payload=payload(
            board=board,
            hint="rb-i",
            pick_no=24,
            next_user_pick=None,
            cfg=config(slot=None),
            roster=(held("rb-held", "RB", 8), held("wr-held", "WR", 5)),
            need_map=needs(
                QB=(0, 1),
                RB=(1, 2),
                WR=(1, 2),
                TE=(0, 1),
                FLEX=(0, 1),
                K=(0, 1),
                DEF=(0, 1),
            ),
        ),
        forbid=frozenset({"def-unknown-seat"}),
        require=frozenset({"rb-i", "wr-i"}),
        why=(
            "With no seat there is no next pick number, so wait-or-take cannot be "
            "reasoned about at all and the pick has to be the best starter on the "
            "board; a defense is still not that."
        ),
    )


CASES: tuple[GoldenCase, ...] = (
    _kicker_round_two(),
    _third_te_while_wr_empty(),
    _defense_round_three(),
    _backup_qb_in_one_qb_league(),
    _bye_stack(),
    _superflex_qb_run(),
    _empty_starter_late(),
    _second_kicker_last_rounds(),
    _te_cliff(),
    _position_run(),
    _vols_compressed(),
    _seat_unknown(),
)

CASES_BY_NAME: dict[str, GoldenCase] = {case.name: case for case in CASES}

# Every hostile board shape the sampler names, plus the ones only a
# hand-written case can reach. Checked in `test_golden.py`.
SITUATIONS: frozenset[str] = frozenset(
    {
        "early_round",
        "roster_fit",
        "bye_stack",
        "superflex_scarcity",
        "empty_starter_late",
        "tier_cliff",
        "position_run",
        "vols_compressed",
        "seat_unknown",
    }
)
