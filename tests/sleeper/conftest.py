"""Shared fakes for Sleeper transport tests. No wall-clock sleep."""

from __future__ import annotations

from pathlib import Path

import pytest


class FakeClock:
    """Monotonic seconds. Tests advance this instead of sleeping."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def slept() -> list[float]:
    return []


@pytest.fixture
def sleep(clock: FakeClock, slept: list[float]):
    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        clock.advance(seconds)

    return _sleep


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "cache" / "sleeper_players.json"
