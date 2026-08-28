"""Board cap is a union of two VOLS arms. No ADP arm. See SPEC.md section 4."""

from __future__ import annotations

from vorpal.contracts import BoardRow, Need, Slot
from vorpal.payload import cap_board, position_depth, remaining_need

FULL = {"QB": Need(filled=1, required=1), "RB": Need(filled=2, required=2)}
OPEN_RB = {"RB": Need(filled=0, required=2), "FLEX": Need(filled=0, required=1)}


def _row(
    player_id: str,
    *,
    position: str = "RB",
    vols: float,
    adp: float,
) -> BoardRow:
    return BoardRow(
        player_id=player_id,
        name=player_id,
        position=position,
        points=vols + 100.0,
        vols=vols,
        delta_starter_points=1.0,
        adp=adp,
        legal_slots=(Slot.RB,) if position == "RB" else (Slot[position],),
    )


def _cap(rows, *, pick_no=50, teams=12, rounds=15, needs=None):
    return cap_board(
        rows,
        pick_no=pick_no,
        teams=teams,
        rounds=rounds,
        needs=OPEN_RB if needs is None else needs,
    )


def _ranked_board() -> list[BoardRow]:
    """60 RBs (vols 200..141) plus 15 TEs (vols 20..6)."""
    rbs = [_row(f"rb{i}", vols=200.0 - i, adp=200.0) for i in range(60)]
    tes = [_row(f"te{i}", position="TE", vols=20.0 - i, adp=200.0) for i in range(15)]
    return [*rbs, *tes]


def test_top_50_overall_are_kept() -> None:
    rows = _ranked_board()
    ids = {row.player_id for row in _cap(rows)}
    assert "rb0" in ids
    assert "rb49" in ids
    assert "rb50" not in ids


def test_cap_is_a_union_not_an_intersection() -> None:
    """te0 is nowhere near the top 50; the position arm is what keeps him."""
    rows = _ranked_board()
    ids = {row.player_id for row in _cap(rows)}
    assert "rb0" in ids
    assert "te0" in ids


def test_adp_never_puts_a_player_on_the_board() -> None:
    """ADP is an input the model reads, not a route onto the board."""
    rbs = [_row(f"rb{i}", vols=200.0 - i, adp=200.0) for i in range(60)]
    # Ten better TEs exhaust the position arm, so only ADP could let these two in.
    tes = [_row(f"te{i}", position="TE", vols=20.0 - i, adp=200.0) for i in range(10)]
    imminent = _row("imminent", position="TE", vols=0.0, adp=51.0)
    faller = _row("faller", position="TE", vols=0.0, adp=2.0)
    ids = {row.player_id for row in _cap([*rbs, *tes, imminent, faller], pick_no=50)}
    assert "imminent" not in ids
    assert "faller" not in ids


def test_the_board_shrinks_as_starter_slots_fill() -> None:
    rows = _ranked_board()
    early = len(_cap(rows, needs=OPEN_RB))
    late = len(_cap(rows, needs=FULL))
    assert late < early


def test_capped_board_is_ordered_by_vols_descending() -> None:
    rows = _ranked_board()
    vols = [row.vols for row in _cap(rows)]
    assert vols == sorted(vols, reverse=True)


def test_kickers_and_defenses_are_off_the_early_board() -> None:
    rbs = [_row(f"rb{i}", vols=100.0 - i, adp=200.0) for i in range(60)]
    ks = [_row(f"k{i}", position="K", vols=5.0 - i * 0.1, adp=190.0) for i in range(15)]
    defs = [
        _row(f"d{i}", position="DEF", vols=4.0 - i * 0.1, adp=195.0) for i in range(15)
    ]
    ids = {row.player_id for row in _cap([*rbs, *ks, *defs], pick_no=10)}
    assert not [i for i in ids if i.startswith(("k", "d")) and i != "rb0"]


def test_kickers_return_late_when_a_starter_slot_is_still_empty() -> None:
    rbs = [_row(f"rb{i}", vols=100.0 - i, adp=200.0) for i in range(60)]
    ks = [_row(f"k{i}", position="K", vols=5.0 - i * 0.1, adp=999.0) for i in range(15)]
    needs = {"K": Need(filled=0, required=1)}
    late = {row.player_id for row in _cap([*rbs, *ks], pick_no=165, needs=needs)}
    assert "k0" in late
    assert "k1" not in late  # depth is the remaining need, not ten


def test_kickers_stay_off_the_late_board_when_the_slot_is_filled() -> None:
    rbs = [_row(f"rb{i}", vols=100.0 - i, adp=200.0) for i in range(60)]
    ks = [_row(f"k{i}", position="K", vols=5.0 - i * 0.1, adp=999.0) for i in range(15)]
    needs = {"K": Need(filled=1, required=1)}
    ids = {row.player_id for row in _cap([*rbs, *ks], pick_no=165, needs=needs)}
    assert not [i for i in ids if i.startswith("k")]


def test_position_depth_scales_down_as_slots_fill() -> None:
    kw = {"picks_left": 100, "teams": 12}
    assert position_depth("RB", needs={"RB": Need(0, 4)}, **kw) == 10
    assert position_depth("RB", needs={"RB": Need(0, 3)}, **kw) == 8
    assert position_depth("RB", needs={"RB": Need(1, 3)}, **kw) == 6
    assert position_depth("RB", needs={"RB": Need(2, 3)}, **kw) == 4
    assert position_depth("RB", needs={"RB": Need(3, 3)}, **kw) == 2


def test_a_filled_position_keeps_a_floor_of_two() -> None:
    rbs = [_row(f"rb{i}", vols=100.0 - i, adp=200.0) for i in range(60)]
    tes = [
        _row(f"te{i}", position="TE", vols=1.0 - i * 0.01, adp=999.0) for i in range(15)
    ]
    ids = {row.player_id for row in _cap([*rbs, *tes], needs=FULL)}
    assert "te0" in ids
    assert "te1" in ids
    assert "te2" not in ids


def test_a_flex_need_counts_for_every_position_that_can_fill_it() -> None:
    needs = {"FLEX": Need(filled=0, required=1)}
    kw = {"needs": needs, "picks_left": 100, "teams": 12}
    assert position_depth("RB", **kw) == 4
    assert position_depth("WR", **kw) == 4
    assert position_depth("TE", **kw) == 4
    assert position_depth("QB", **kw) == 2


def test_bench_is_not_a_starter_need() -> None:
    assert remaining_need({"BN": Need(filled=0, required=6)}, "RB") == 0


def test_an_unknown_slot_name_is_ignored() -> None:
    assert remaining_need({"NOT_A_SLOT": Need(filled=0, required=9)}, "RB") == 0


def test_dst_is_deferred_under_either_spelling() -> None:
    kw = {"needs": {"DEF": Need(filled=0, required=1)}, "teams": 12}
    assert position_depth("DST", picks_left=100, **kw) == 0
    assert position_depth("DEF", picks_left=100, **kw) == 0
    assert position_depth("DEF", picks_left=10, **kw) == 1


def test_picks_left_never_goes_negative() -> None:
    rows = [_row("rb0", vols=1.0, adp=999.0)]
    assert [row.player_id for row in _cap(rows, pick_no=999)] == ["rb0"]
