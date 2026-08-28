"""Slots come from the league list, or from the mock. Bench is inferred once."""

from __future__ import annotations

from helpers import (
    COLUMNS,
    OPERATOR,
    STARTER_SLOTS,
    make_counts,
    make_draft,
    make_league,
)

from vorpal.contracts import Slot
from vorpal.resolve import resolve


def test_attached_draft_uses_league_roster_positions() -> None:
    league_slots = (
        Slot.QB,
        Slot.RB,
        Slot.WR,
        Slot.TE,
        Slot.FLEX,
        Slot.K,
        Slot.BN,
    )
    draft = make_draft(slot_counts=make_counts(flex=9, bn=1))
    result = resolve(
        draft,
        operator=OPERATOR,
        league=make_league(roster_positions=league_slots),
        stat_columns=COLUMNS,
    )
    assert result.config.slots == league_slots


def test_borrowed_scoring_league_never_overrides_slots() -> None:
    mock = make_draft(
        league_id=None,
        draft_order=None,
        slot_counts=make_counts(super_flex=0, k=1, defense=1, bn=2),
        scoring_label="2qb",
    )
    borrowed = make_league(
        league_id="sf",
        roster_positions=(
            Slot.QB,
            Slot.RB,
            Slot.WR,
            Slot.TE,
            Slot.SUPER_FLEX,
            Slot.BN,
        ),
    )
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=borrowed,
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    assert Slot.SUPER_FLEX not in result.config.slots
    assert Slot.K in result.config.slots
    assert Slot.DEF in result.config.slots
    assert result.config.slots.count(Slot.BN) == 2


def test_infer_bench_when_slots_bn_absent_and_league_list_did_not_fire() -> None:
    mock = make_draft(
        league_id=None,
        draft_order=None,
        rounds=11,
        slot_counts=make_counts(k=0, defense=0, flex=1, wr=3, bn=None),
    )
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=make_league(),
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    starters = [slot for slot in result.config.slots if slot is not Slot.BN]
    assert len(starters) == 8  # QB1 RB2 WR3 TE1 FLEX1
    assert result.config.slots.count(Slot.BN) == 3  # 11 - 8


def test_league_list_does_not_infer_bench_when_bn_is_missing() -> None:
    result = resolve(
        make_draft(slot_counts=make_counts(bn=None), rounds=15),
        operator=OPERATOR,
        league=make_league(roster_positions=STARTER_SLOTS),
        stat_columns=COLUMNS,
    )
    assert Slot.BN not in result.config.slots
    assert result.config.slots == STARTER_SLOTS


def test_infer_bench_floors_at_zero_when_rounds_are_short() -> None:
    mock = make_draft(
        league_id=None,
        draft_order=None,
        rounds=3,
        slot_counts=make_counts(bn=None),
    )
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=make_league(),
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    assert Slot.BN not in result.config.slots


def test_present_zero_bench_is_not_inferred() -> None:
    mock = make_draft(
        league_id=None,
        draft_order=None,
        rounds=16,
        slot_counts=make_counts(bn=0),
    )
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=make_league(),
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    assert Slot.BN not in result.config.slots
