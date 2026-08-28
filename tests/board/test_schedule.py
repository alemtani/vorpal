"""Poll cadence, backoff, degrade, grey-out. Pure functions; no clock."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("drafting", 3),
        ("pre_draft", 15),
        ("complete", 15),
        ("paused", 15),
        ("mystery", 15),
        ("", 15),
    ],
)
def test_poll_interval_is_3s_only_while_drafting(status: str, expected: int) -> None:
    from vorpal.board import poll_interval

    assert poll_interval(status) == expected


@pytest.mark.parametrize(
    ("failures", "expected"),
    [
        (1, 5),
        (2, 15),
        (3, 45),
        (4, 45),
        (99, 45),
    ],
)
def test_backoff_is_5_15_45_then_hold(failures: int, expected: int) -> None:
    from vorpal.board import next_backoff

    assert next_backoff(failures) == expected


def test_degrade_starts_at_15s_of_age() -> None:
    from vorpal.board import is_degraded

    assert is_degraded(0) is False
    assert is_degraded(14.9) is False
    assert is_degraded(15) is True
    assert is_degraded(15.0) is True
    assert is_degraded(60) is True


def test_grey_out_at_pick_timer_skips_zero_and_null() -> None:
    from vorpal.board import is_greyed_out

    assert is_greyed_out(100.0, None) is False
    assert is_greyed_out(100.0, 0) is False
    assert is_greyed_out(59.0, 60) is False
    assert is_greyed_out(60.0, 60) is True
    assert is_greyed_out(120.0, 60) is True
    assert is_greyed_out(119.0, 120) is False
    assert is_greyed_out(120.0, 120) is True
