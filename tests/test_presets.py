"""Preset scoring tables for standalone mocks. No live network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vorpal.contracts import Host, LeagueFormat
from vorpal.platform.presets import (
    PRESETS,
    preset_league,
    preset_scoring,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sleeper"


def _recorded_scoring() -> dict[str, float]:
    body: dict[str, Any] = json.loads(
        (FIXTURES / "league_superflex.json").read_text(encoding="utf-8")
    )
    return {str(k): float(v) for k, v in body["scoring_settings"].items()}


def test_presets_are_the_three_rec_variants() -> None:
    assert PRESETS == ("std", "half", "ppr")


@pytest.mark.parametrize("name,rec", [("std", 0.0), ("half", 0.5), ("ppr", 1.0)])
def test_only_rec_names_the_preset(name: str, rec: float) -> None:
    assert preset_scoring(name)["rec"] == rec


def test_base_table_matches_a_real_sleeper_export() -> None:
    """The preset is a captured default, not a guess. ppr must equal the

    recorded superflex table key for key, since superflex scoring is ppr.
    """
    assert preset_scoring("ppr") == _recorded_scoring()


def test_std_and_half_differ_from_ppr_only_by_rec() -> None:
    ppr = preset_scoring("ppr")
    for name in ("std", "half"):
        table = preset_scoring(name)
        differ = {k for k in ppr if ppr[k] != table[k]}
        assert differ == {"rec"}


def test_preset_league_is_a_redraft_scoring_source() -> None:
    league = preset_league("ppr", "2026")
    assert league.host is Host.SLEEPER
    assert league.format is LeagueFormat.REDRAFT
    assert league.taxi_slots == 0
    assert league.max_keepers == 0
    assert league.roster_positions == ()  # slots come from the mock
    assert league.season == "2026"
    assert "ppr" in league.league_id
    assert league.scoring["rec"] == 1.0


def test_unknown_preset_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        preset_scoring("superflex")
