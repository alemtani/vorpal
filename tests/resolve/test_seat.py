"""Seat comes from draft_order user_id, never from picked_by."""

from __future__ import annotations

from helpers import (
    COLUMNS,
    OPERATOR,
    complete_order,
    make_draft,
    make_league,
)

from vorpal.resolve import resolve


def test_match_operator_user_id_in_draft_order() -> None:
    draft = make_draft(
        draft_order=complete_order(operator_slot=7),
        slot_to_roster_id={i: 100 + i for i in range(1, 13)},
    )
    result = resolve(
        draft,
        operator=OPERATOR,
        league=make_league(),
        stat_columns=COLUMNS,
    )
    assert result.seat is not None
    assert result.seat.user_id == OPERATOR.user_id
    assert result.seat.slot == 7
    assert result.seat.roster_id == 107
    assert result.config.slot == 7


def test_unset_order_proceeds_and_omits_seat() -> None:
    result = resolve(
        make_draft(draft_order=None),
        operator=OPERATOR,
        league=make_league(),
        stat_columns=COLUMNS,
    )
    assert result.seat is None
    assert result.config.slot is None


def test_empty_order_is_unset() -> None:
    result = resolve(
        make_draft(draft_order={}),
        operator=OPERATOR,
        league=make_league(),
        stat_columns=COLUMNS,
    )
    assert result.seat is None
    assert result.config.slot is None


def test_partial_order_with_explicit_slot_proceeds() -> None:
    draft = make_draft(
        draft_order={"user_01": 1, "user_02": 2},
        slot_to_roster_id={4: 44},
    )
    result = resolve(
        draft,
        operator=OPERATOR,
        league=make_league(),
        explicit_slot=4,
        stat_columns=COLUMNS,
    )
    assert result.seat is not None
    assert result.seat.slot == 4
    assert result.seat.roster_id == 44
    assert result.config.slot == 4


def test_partial_order_uses_operator_when_present() -> None:
    draft = make_draft(draft_order={"user_01": 1, OPERATOR.user_id: 9})
    result = resolve(
        draft,
        operator=OPERATOR,
        league=make_league(),
        explicit_slot=3,
        stat_columns=COLUMNS,
    )
    assert result.seat is not None
    assert result.seat.slot == 9
    assert result.config.slot == 9


def test_unset_order_with_explicit_slot_sets_seat() -> None:
    result = resolve(
        make_draft(draft_order=None, slot_to_roster_id={5: 50}),
        operator=OPERATOR,
        league=make_league(),
        explicit_slot=5,
        stat_columns=COLUMNS,
    )
    assert result.seat is not None
    assert result.seat.slot == 5
    assert result.seat.roster_id == 50
