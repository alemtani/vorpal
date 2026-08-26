"""Board cap is a union. Scarcity is not read off the truncated list."""

from __future__ import annotations

from vorpal.contracts import BoardRow, Slot
from vorpal.payload import cap_board


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


def _ranked_board() -> tuple[list[BoardRow], BoardRow, BoardRow]:
    """60 RBs (vols 200..141) plus 15 Ks (vols 20..6), then two extra Ks."""
    rbs = [_row(f"rb{i}", vols=200.0 - i, adp=200.0) for i in range(60)]
    kickers = [_row(f"k{i}", position="K", vols=20.0 - i, adp=200.0) for i in range(15)]
    window_k = _row("window_k", position="K", vols=1.0, adp=60.0)
    far_k = _row("far_k", position="K", vols=0.5, adp=200.0)
    return [*rbs, *kickers, window_k, far_k], window_k, far_k


def test_adp_window_player_is_kept_even_outside_top_50_and_top_10_at_position() -> None:
    rows, window_k, far_k = _ranked_board()
    capped = cap_board(rows, pick_no=50, teams=12)
    ids = {row.player_id for row in capped}
    assert "window_k" in ids
    assert "far_k" not in ids
    assert window_k.vols < 50
    assert far_k.player_id == "far_k"


def test_top_50_overall_are_kept() -> None:
    rows, _, _ = _ranked_board()
    capped = cap_board(rows, pick_no=50, teams=12)
    ids = {row.player_id for row in capped}
    assert "rb0" in ids
    assert "rb49" in ids
    assert "rb50" not in ids


def test_top_10_at_a_position_are_kept_even_outside_top_50_overall() -> None:
    rows, _, _ = _ranked_board()
    capped = cap_board(rows, pick_no=50, teams=12)
    ids = {row.player_id for row in capped}
    assert "k0" in ids
    assert "k9" in ids
    assert "k10" not in ids


def test_cap_is_a_union_not_an_intersection() -> None:
    rows, _, _ = _ranked_board()
    capped = cap_board(rows, pick_no=50, teams=12)
    ids = {row.player_id for row in capped}
    assert "rb0" in ids
    assert "k0" in ids
    assert "window_k" in ids


def test_capped_board_is_ordered_by_vols_descending() -> None:
    rows, _, _ = _ranked_board()
    capped = cap_board(rows, pick_no=50, teams=12)
    vols = [row.vols for row in capped]
    assert vols == sorted(vols, reverse=True)


def test_adp_window_is_the_next_two_rounds_from_pick_no() -> None:
    just_inside = _row("in", position="TE", vols=0.1, adp=74.0)
    just_outside = _row("out", position="TE", vols=0.2, adp=74.1)
    rbs = [_row(f"rb{i}", vols=100.0 - i, adp=200.0) for i in range(60)]
    tes = [_row(f"te{i}", position="TE", vols=50.0 - i, adp=200.0) for i in range(15)]
    capped = cap_board([*rbs, *tes, just_inside, just_outside], pick_no=50, teams=12)
    ids = {row.player_id for row in capped}
    assert "in" in ids
    assert "out" not in ids
