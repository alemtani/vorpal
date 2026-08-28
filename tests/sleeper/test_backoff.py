"""Error backoff is a pure schedule. Tests never sleep."""

from vorpal.sleeper import backoff_seconds


def test_backoff_is_zero_when_there_are_no_failures() -> None:
    assert backoff_seconds(0) == 0.0
    assert backoff_seconds(-1) == 0.0


def test_backoff_schedule_is_five_fifteen_forty_five_then_hold() -> None:
    assert backoff_seconds(1) == 5.0
    assert backoff_seconds(2) == 15.0
    assert backoff_seconds(3) == 45.0
    assert backoff_seconds(4) == 45.0
    assert backoff_seconds(99) == 45.0
