"""Weekly rates, byes, known-out weeks, and starter fill."""

from __future__ import annotations

from vorpal.contracts import Slot
from vorpal.valuation import (
    DEFAULT_GAMES,
    SEASON_WEEKS,
    ScoredPlayer,
    fill_starters,
    week_vector,
)


def test_week_vector_has_weeks_1_to_18() -> None:
    vector = week_vector(170.0)
    assert len(vector) == SEASON_WEEKS == 18
    assert vector[0] == 170.0 / DEFAULT_GAMES
    assert all(week == 10.0 for week in vector)


def test_bye_week_is_zero() -> None:
    vector = week_vector(170.0, bye=14)
    assert vector[13] == 0.0
    assert vector[0] == 10.0
    assert vector[17] == 10.0
    assert sum(vector) == 170.0


def test_rate_divides_by_gp_when_present() -> None:
    vector = week_vector(140.0, gp=14.0, bye=7)
    assert vector[6] == 0.0
    assert vector[0] == 10.0
    assert sum(1 for week in vector if week == 0.0) == 1


def test_served_suspension_zeros_weeks_1_through_n() -> None:
    vector = week_vector(110.0, gp=11.0, bye=14, out_weeks=frozenset(range(1, 7)))
    for week in range(1, 7):
        assert vector[week - 1] == 0.0
    assert vector[13] == 0.0
    assert vector[6] == 10.0
    assert vector[17] == 10.0
    zeros = [i + 1 for i, week in enumerate(vector) if week == 0.0]
    assert zeros == [1, 2, 3, 4, 5, 6, 14]


def test_gp_below_17_does_not_rebuild_a_full_season() -> None:
    """Do not zero unknown misses. Ship gp on the row instead."""
    vector = week_vector(80.0, gp=10.0)
    assert vector[0] == 8.0
    assert all(week == 8.0 for week in vector)
    assert sum(vector) != 80.0


def test_zero_gp_is_zero_rate() -> None:
    vector = week_vector(80.0, gp=0.0, bye=4)
    assert vector[3] == 0.0
    assert all(week == 0.0 for week in vector)


def test_fill_starters_emits_points_and_empty_slots() -> None:
    rb = ScoredPlayer("RB1", "RB", 170.0, bye=5)
    wr = ScoredPlayer("WR1", "WR", 85.0, bye=5)
    slots = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.FLEX, Slot.BN)
    weekly = fill_starters((rb, wr), slots)
    assert len(weekly) == 18
    bye = weekly[4]
    assert bye.week == 5
    assert bye.starter_points == 0.0
    assert Slot.RB in bye.empty
    assert Slot.WR in bye.empty
    assert Slot.QB in bye.empty
    assert Slot.TE in bye.empty
    assert Slot.FLEX in bye.empty
    assert Slot.BN not in bye.empty
    week1 = weekly[0]
    assert week1.week == 1
    assert week1.starter_points == 10.0 + 5.0
    assert Slot.RB not in week1.empty
    assert Slot.WR not in week1.empty
    assert Slot.FLEX in week1.empty
    assert Slot.QB in week1.empty


def test_flex_takes_the_third_rb_when_dedicated_rb_is_full() -> None:
    rbs = tuple(
        ScoredPlayer(f"RB{i}", "RB", 170.0 - 17 * i, bye=None) for i in (1, 2, 3)
    )
    slots = (Slot.RB, Slot.RB, Slot.FLEX)
    week1 = fill_starters(rbs, slots)[0]
    assert week1.empty == ()
    assert (
        week1.starter_points
        == (170.0 - 17) / 17 + (170.0 - 34) / 17 + (170.0 - 51) / 17
    )


def test_zero_rate_player_does_not_fill_a_startable_slot() -> None:
    out = ScoredPlayer(
        "RB1",
        "RB",
        100.0,
        gp=11.0,
        out_weeks=frozenset({1}),
    )
    week1 = fill_starters((out,), (Slot.RB,))[0]
    assert week1.starter_points == 0.0
    assert week1.empty == (Slot.RB,)
