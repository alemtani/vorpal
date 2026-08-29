"""Board rows join VOLS, ADP, and ECR, and pay for the delta only once capped."""

from __future__ import annotations

import pytest

from vorpal.contracts import EcrRow, Need, Slot
from vorpal.payload import build_rows
from vorpal.valuation import ScoredPlayer, compute_vols

SLOTS = (Slot.QB, Slot.RB, Slot.RB, Slot.WR, Slot.FLEX, Slot.BN)
NEEDS = {
    "QB": Need(filled=0, required=1),
    "RB": Need(filled=0, required=2),
    "WR": Need(filled=0, required=1),
    "FLEX": Need(filled=0, required=1),
}


def _pool() -> dict[str, ScoredPlayer]:
    players = [
        ScoredPlayer(
            player_id=f"rb{n}",
            position="RB",
            points=300.0 - n,
            bye=7,
            gp=17.0,
            name=f"RB {n}",
        )
        for n in range(1, 40)
    ]
    players += [
        ScoredPlayer(
            player_id=f"qb{n}",
            position="QB",
            points=280.0 - n,
            bye=9,
            name=f"QB {n}",
        )
        for n in range(1, 20)
    ]
    return {player.player_id: player for player in players}


def _build(**kwargs):
    pool = kwargs.pop("pool", None) or _pool()
    values = compute_vols(list(pool.values()), SLOTS, 12)
    return build_rows(
        values,
        pool=pool,
        available=kwargs.pop("available", set(pool)),
        adp=kwargs.pop("adp", {"rb1": 1.5}),
        ecr=kwargs.pop("ecr", {}),
        roster=kwargs.pop("roster", ()),
        slots=SLOTS,
        teams=12,
        rounds=15,
        pick_no=kwargs.pop("pick_no", 1),
        needs=kwargs.pop("needs", NEEDS),
    )


def test_rows_are_vols_descending_and_carry_legal_slots() -> None:
    rows = _build()
    assert rows[0].player_id == "rb1"
    assert [row.vols for row in rows] == sorted(
        (row.vols for row in rows), reverse=True
    )
    assert rows[0].legal_slots == (Slot.RB, Slot.FLEX, Slot.BN)


def test_rows_drop_drafted_players() -> None:
    pool = _pool()
    taken = set(pool) - {"rb1"}
    rows = _build(pool=pool, available=taken)
    assert all(row.player_id != "rb1" for row in rows)


def test_rows_carry_adp_and_default_to_zero() -> None:
    rows = {row.player_id: row for row in _build()}
    assert rows["rb1"].adp == pytest.approx(1.5)
    assert rows["rb2"].adp == 0.0


def test_rows_carry_ecr_when_the_join_hit_and_omit_it_otherwise() -> None:
    ecr = {
        "rb1": EcrRow(
            player_id="rb1",
            name="RB 1",
            team="SF",
            position="RB",
            bye=7,
            rank_ecr=1,
            rank_min=1,
            rank_max=4,
            rank_std=1.2,
        )
    }
    rows = {row.player_id: row for row in _build(ecr=ecr)}
    assert rows["rb1"].ecr == 1
    assert rows["rb1"].ecr_min == 1
    assert rows["rb1"].ecr_max == 4
    assert rows["rb1"].ecr_std == pytest.approx(1.2)
    assert rows["rb2"].ecr is None


def test_delta_is_computed_against_the_operator_roster() -> None:
    pool = _pool()
    rows = {row.player_id: row for row in _build(pool=pool, roster=())}
    # An empty roster seats the candidate every week except its bye.
    assert rows["rb1"].delta_starter_points == pytest.approx(
        pool["rb1"].points / 17 * 17
    )


def test_delta_shrinks_once_the_slot_is_already_held() -> None:
    pool = _pool()
    held = [pool["rb2"], pool["rb3"], pool["rb4"]]
    alone = {row.player_id: row for row in _build(pool=pool, roster=())}
    crowded = {row.player_id: row for row in _build(pool=pool, roster=held)}
    assert crowded["rb1"].delta_starter_points < alone["rb1"].delta_starter_points
    assert crowded["rb1"].vols == alone["rb1"].vols


def test_rows_skip_players_missing_from_the_pool() -> None:
    pool = _pool()
    values = compute_vols(list(pool.values()), SLOTS, 12)
    thin = {key: value for key, value in pool.items() if key != "rb1"}
    rows = build_rows(
        values,
        pool=thin,
        available=set(pool),
        adp={},
        ecr={},
        roster=(),
        slots=SLOTS,
        teams=12,
        rounds=15,
        pick_no=1,
        needs=NEEDS,
    )
    assert all(row.player_id != "rb1" for row in rows)
