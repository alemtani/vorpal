"""vols is global. delta_starter_points is vs this roster."""

from __future__ import annotations

import pytest

from vorpal.contracts import Slot
from vorpal.valuation import ScoredPlayer, compute_vols, delta_starter_points

SLOTS = (Slot.QB, Slot.RB, Slot.RB, Slot.WR, Slot.WR, Slot.TE, Slot.FLEX)
POOL = (
    ScoredPlayer("QB1", "QB", 200.0),
    ScoredPlayer("QB2", "QB", 150.0),
    ScoredPlayer("RB1", "RB", 180.0),
    ScoredPlayer("RB2", "RB", 160.0),
    ScoredPlayer("RB3", "RB", 140.0),
    ScoredPlayer("RB4", "RB", 120.0),
    ScoredPlayer("RB5", "RB", 100.0),
    ScoredPlayer("CAND", "RB", 170.0, bye=10),
    ScoredPlayer("WR1", "WR", 155.0),
    ScoredPlayer("WR2", "WR", 130.0),
    ScoredPlayer("WR3", "WR", 90.0),
    ScoredPlayer("TE1", "TE", 110.0),
    ScoredPlayer("TE2", "TE", 70.0),
)


def test_same_player_same_vols_different_delta_against_zero_vs_four_rbs() -> None:
    result = compute_vols(POOL, SLOTS, teams=2)
    candidate = next(player for player in POOL if player.player_id == "CAND")
    vols = result.value_by_id()["CAND"].vols
    empty: tuple[ScoredPlayer, ...] = ()
    four_rbs = tuple(
        player for player in POOL if player.player_id in {"RB1", "RB2", "RB3", "RB4"}
    )
    delta_empty = delta_starter_points(empty, candidate, SLOTS)
    delta_full = delta_starter_points(four_rbs, candidate, SLOTS)
    again = compute_vols(POOL, SLOTS, teams=2)
    assert again.value_by_id()["CAND"].vols == vols
    assert delta_empty != delta_full
    assert delta_empty > delta_full
    assert delta_empty == pytest.approx(170.0)
    assert delta_full == pytest.approx(30.0)
