"""Shared tables and fixture loaders. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vorpal.contracts import Slot
from vorpal.valuation import ScoredPlayer

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

SF_SLOTS = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.SUPER_FLEX, Slot.BN, Slot.BN)
ONE_QB_SLOTS = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.FLEX, Slot.BN)


def _load_json(relative: str) -> object:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def _league_scoring(filename: str) -> dict[str, float]:
    league = _load_json(f"sleeper/{filename}")
    assert isinstance(league, dict)
    raw = league["scoring_settings"]
    assert isinstance(raw, dict)
    return {str(key): float(value) for key, value in raw.items()}


def _player(
    player_id: str,
    position: str,
    points: float,
    *,
    market_only: bool = False,
) -> ScoredPlayer:
    return ScoredPlayer(
        player_id=player_id,
        position=position,
        points=points,
        market_only=market_only,
    )


@pytest.fixture
def snake_scoring() -> dict[str, float]:
    return _league_scoring("league_snake_redraft.json")


@pytest.fixture
def superflex_scoring() -> dict[str, float]:
    return _league_scoring("league_superflex.json")


@pytest.fixture
def projection_rows() -> list[dict[str, object]]:
    rows = _load_json("projections/season_regular.json")
    assert isinstance(rows, list)
    return [row for row in rows if isinstance(row, dict)]


@pytest.fixture
def snake_slots() -> tuple[Slot, ...]:
    league = _load_json("sleeper/league_snake_redraft.json")
    assert isinstance(league, dict)
    return tuple(Slot(code) for code in league["roster_positions"])


@pytest.fixture
def superflex_slots() -> tuple[Slot, ...]:
    league = _load_json("sleeper/league_superflex.json")
    assert isinstance(league, dict)
    return tuple(Slot(code) for code in league["roster_positions"])


@pytest.fixture
def sf_slots() -> tuple[Slot, ...]:
    return SF_SLOTS


@pytest.fixture
def one_qb_slots() -> tuple[Slot, ...]:
    return ONE_QB_SLOTS


@pytest.fixture
def sf_table() -> tuple[ScoredPlayer, ...]:
    """Backup QBs still score. SUPER_FLEX absorbs them in pass 1."""
    return (
        _player("QB1", "QB", 100.0),
        _player("QB2", "QB", 90.0),
        _player("QB3", "QB", 80.0),
        _player("QB4", "QB", 55.0),
        _player("QB5", "QB", 20.0),
        _player("RB1", "RB", 70.0),
        _player("RB2", "RB", 60.0),
        _player("RB3", "RB", 50.0),
        _player("RB4", "RB", 15.0),
        _player("WR1", "WR", 65.0),
        _player("WR2", "WR", 58.0),
        _player("WR3", "WR", 40.0),
        _player("WR4", "WR", 12.0),
        _player("TE1", "TE", 45.0),
        _player("TE2", "TE", 35.0),
        _player("TE3", "TE", 10.0),
    )


@pytest.fixture
def sf_cliff_table() -> tuple[ScoredPlayer, ...]:
    """QB cliff after two starters. Skill leftover fills SUPER_FLEX."""
    return (
        _player("QB1", "QB", 100.0),
        _player("QB2", "QB", 90.0),
        _player("QB3", "QB", 50.0),
        _player("QB4", "QB", 45.0),
        _player("RB1", "RB", 70.0),
        _player("RB2", "RB", 65.0),
        _player("RB3", "RB", 60.0),
        _player("RB4", "RB", 15.0),
        _player("WR1", "WR", 68.0),
        _player("WR2", "WR", 64.0),
        _player("WR3", "WR", 55.0),
        _player("WR4", "WR", 12.0),
        _player("TE1", "TE", 45.0),
        _player("TE2", "TE", 40.0),
        _player("TE3", "TE", 10.0),
    )
