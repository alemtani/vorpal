"""Two-pass VOLS. Bench is not absorbed. Market-only rows are out."""

from __future__ import annotations

from vorpal.contracts import Slot
from vorpal.valuation import ScoredPlayer, compute_vols
from vorpal.valuation.slots import greedy_fill


def _p(
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


def test_vols_is_points_minus_replacement_points() -> None:
    players = (
        _p("RB1", "RB", 100.0),
        _p("RB2", "RB", 80.0),
        _p("RB3", "RB", 50.0),
        _p("RB4", "RB", 20.0),
        _p("QB1", "QB", 90.0),
        _p("QB2", "QB", 40.0),
        _p("WR1", "WR", 70.0),
        _p("WR2", "WR", 30.0),
        _p("TE1", "TE", 25.0),
        _p("TE2", "TE", 5.0),
    )
    result = compute_vols(players, (Slot.QB, Slot.RB, Slot.WR, Slot.TE), teams=2)
    assert result.replacement["RB"].player_id == "RB3"
    assert result.replacement["RB"].points == 50.0
    by_id = result.value_by_id()
    assert by_id["RB1"].vols == 50.0
    assert by_id["RB2"].vols == 30.0
    assert by_id["RB3"].vols == 0.0
    assert by_id["RB4"].vols == -30.0


def test_bench_is_not_absorbed() -> None:
    players = tuple(_p(f"RB{i}", "RB", float(100 - 10 * i)) for i in range(1, 6))
    players += (_p("QB1", "QB", 10.0), _p("QB2", "QB", 9.0))
    players += (_p("WR1", "WR", 8.0), _p("WR2", "WR", 7.0))
    players += (_p("TE1", "TE", 6.0), _p("TE2", "TE", 5.0))
    slots = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.BN, Slot.BN, Slot.BN)
    result = compute_vols(players, slots, teams=2)
    assert result.replacement["RB"].player_id == "RB3"
    assert result.replacement_ranks["RB"] == 3


def test_flex_then_superflex_most_restrictive_first() -> None:
    players = (
        _p("QB1", "QB", 100.0),
        _p("QB2", "QB", 40.0),
        _p("QB3", "QB", 30.0),
        _p("RB1", "RB", 90.0),
        _p("RB2", "RB", 80.0),
        _p("RB3", "RB", 70.0),
        _p("WR1", "WR", 85.0),
        _p("WR2", "WR", 20.0),
        _p("TE1", "TE", 15.0),
        _p("TE2", "TE", 5.0),
    )
    slots = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.FLEX, Slot.SUPER_FLEX)
    result = compute_vols(players, slots, teams=1)
    assert result.replacement["QB"].player_id == "QB2"
    assert "RB" not in result.replacement


def test_market_only_rows_are_excluded_from_vols() -> None:
    players = (
        _p("RB1", "RB", 100.0),
        _p("RB2", "RB", 80.0),
        _p("MKT", "RB", 0.0, market_only=True),
        _p("RB3", "RB", 50.0),
        _p("QB1", "QB", 10.0),
        _p("QB2", "QB", 9.0),
        _p("WR1", "WR", 8.0),
        _p("WR2", "WR", 7.0),
        _p("TE1", "TE", 6.0),
        _p("TE2", "TE", 5.0),
    )
    result = compute_vols(players, (Slot.QB, Slot.RB, Slot.WR, Slot.TE), teams=2)
    by_id = result.value_by_id()
    assert "MKT" not in by_id
    assert result.replacement["RB"].player_id == "RB3"


def test_superflex_pass1_absorbs_extra_qbs(
    sf_table: tuple[ScoredPlayer, ...],
    sf_slots: tuple[Slot, ...],
) -> None:
    result = compute_vols(sf_table, sf_slots, teams=2)
    assert result.replacement_ranks["QB"] > 3
    assert result.replacement["QB"].player_id == "QB5"
    assert result.pass1_replacement_ranks["QB"] > 3


def test_superflex_pass2_reorders_players_vs_points(
    sf_cliff_table: tuple[ScoredPlayer, ...],
    sf_slots: tuple[Slot, ...],
) -> None:
    result = compute_vols(sf_cliff_table, sf_slots, teams=2)
    by_id = result.value_by_id()
    points_order = tuple(
        row.player_id
        for row in sorted(
            sf_cliff_table, key=lambda item: (-item.points, item.player_id)
        )
        if not row.market_only
    )
    vols_order = tuple(value.player_id for value in result.values)
    assert vols_order != points_order
    assert by_id["QB1"].points > by_id["RB1"].points
    assert by_id["RB1"].vols > by_id["QB1"].vols


def test_one_qb_does_not_absorb_qb_into_flex(
    sf_table: tuple[ScoredPlayer, ...],
    one_qb_slots: tuple[Slot, ...],
) -> None:
    result = compute_vols(sf_table, one_qb_slots, teams=2)
    assert result.replacement_ranks["QB"] == 3
    assert result.replacement["QB"].player_id == "QB3"


def test_op_matches_superflex_eligibility(
    sf_table: tuple[ScoredPlayer, ...],
    sf_slots: tuple[Slot, ...],
) -> None:
    sf = compute_vols(sf_table, sf_slots, teams=2)
    op_slots = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.OP, Slot.BN, Slot.BN)
    op = compute_vols(sf_table, op_slots, teams=2)
    assert op.replacement_ranks == sf.replacement_ranks
    assert op.replacement == sf.replacement


def test_wrrb_flex_fills_before_flex() -> None:
    players = (
        _p("QB1", "QB", 10.0),
        _p("RB1", "RB", 90.0),
        _p("RB2", "RB", 40.0),
        _p("WR1", "WR", 80.0),
        _p("WR2", "WR", 70.0),
        _p("TE1", "TE", 60.0),
        _p("TE2", "TE", 50.0),
        _p("TE3", "TE", 5.0),
    )
    slots = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.WRRB_FLEX, Slot.FLEX)
    result = compute_vols(players, slots, teams=1)
    assert result.replacement["RB"].player_id == "RB2"
    assert result.replacement["TE"].player_id == "TE3"


def test_rec_flex_takes_te_not_rb() -> None:
    players = (
        _p("QB1", "QB", 10.0),
        _p("RB1", "RB", 90.0),
        _p("RB2", "RB", 80.0),
        _p("WR1", "WR", 70.0),
        _p("TE1", "TE", 60.0),
        _p("TE2", "TE", 50.0),
        _p("TE3", "TE", 5.0),
    )
    slots = (Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.REC_FLEX)
    result = compute_vols(players, slots, teams=1)
    assert result.replacement["TE"].player_id == "TE3"
    assert result.replacement["RB"].player_id == "RB2"


def test_greedy_fill_seats_dedicated_slots_before_flex() -> None:
    """The one fill rule: a FLEX seat goes to the best player left, not best overall."""
    ranked = [
        ScoredPlayer("rb1", "RB", 300.0),
        ScoredPlayer("rb2", "RB", 290.0),
        ScoredPlayer("wr1", "WR", 280.0),
        ScoredPlayer("wr2", "WR", 270.0),
        ScoredPlayer("te1", "TE", 100.0),
    ]
    counts = {Slot.RB: 1, Slot.WR: 1, Slot.FLEX: 1}
    seated, leftover = greedy_fill(ranked, counts)
    assert [player.player_id for player in seated[Slot.RB]] == ["rb1"]
    assert [player.player_id for player in seated[Slot.WR]] == ["wr1"]
    assert [player.player_id for player in seated[Slot.FLEX]] == ["rb2"]
    assert [player.player_id for player in leftover] == ["wr2", "te1"]


def test_greedy_fill_scales_by_teams_and_reports_short_slots() -> None:
    ranked = [ScoredPlayer(f"rb{i}", "RB", 100.0 - i) for i in range(3)]
    seated, leftover = greedy_fill(ranked, {Slot.RB: 1, Slot.QB: 1}, teams=2)
    assert len(seated[Slot.RB]) == 2
    assert seated[Slot.QB] == []
    assert [player.player_id for player in leftover] == ["rb2"]
