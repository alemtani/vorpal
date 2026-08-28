"""Eligibility table from SPEC.md section 2."""

from __future__ import annotations

from vorpal.contracts import Slot
from vorpal.resolve import eligible_positions, legal_slots


def test_qb_slot_is_qb_only() -> None:
    assert eligible_positions(Slot.QB) == frozenset({"QB"})


def test_dedicated_skill_and_k_and_def() -> None:
    assert eligible_positions(Slot.RB) == frozenset({"RB"})
    assert eligible_positions(Slot.WR) == frozenset({"WR"})
    assert eligible_positions(Slot.TE) == frozenset({"TE"})
    assert eligible_positions(Slot.K) == frozenset({"K"})
    assert eligible_positions(Slot.DEF) == frozenset({"DEF"})


def test_flex_is_rb_wr_te() -> None:
    assert eligible_positions(Slot.FLEX) == frozenset({"RB", "WR", "TE"})


def test_super_flex_and_op_include_qb() -> None:
    offense = frozenset({"QB", "RB", "WR", "TE"})
    assert eligible_positions(Slot.SUPER_FLEX) == offense
    assert eligible_positions(Slot.OP) == offense


def test_bn_is_any() -> None:
    assert eligible_positions(Slot.BN) is None


def test_idp_slot_eligibility() -> None:
    assert eligible_positions(Slot.DL) == frozenset({"DL"})
    assert eligible_positions(Slot.LB) == frozenset({"LB"})
    assert eligible_positions(Slot.DB) == frozenset({"DB"})
    assert eligible_positions(Slot.IDP_FLEX) == frozenset({"DL", "LB", "DB"})


def test_wrrb_and_rec_flex() -> None:
    assert eligible_positions(Slot.WRRB_FLEX) == frozenset({"WR", "RB"})
    assert eligible_positions(Slot.REC_FLEX) == frozenset({"WR", "TE"})
    roster = (Slot.WRRB_FLEX, Slot.REC_FLEX, Slot.BN)
    assert legal_slots("WR", roster) == (Slot.WRRB_FLEX, Slot.REC_FLEX, Slot.BN)
    assert legal_slots("RB", roster) == (Slot.WRRB_FLEX, Slot.BN)
    assert legal_slots("TE", roster) == (Slot.REC_FLEX, Slot.BN)


def test_legal_slots_for_rb_on_a_typical_roster() -> None:
    roster = (
        Slot.QB,
        Slot.RB,
        Slot.RB,
        Slot.WR,
        Slot.TE,
        Slot.FLEX,
        Slot.SUPER_FLEX,
        Slot.K,
        Slot.DEF,
        Slot.BN,
    )
    assert legal_slots("RB", roster) == (Slot.RB, Slot.FLEX, Slot.SUPER_FLEX, Slot.BN)
    assert legal_slots("QB", roster) == (Slot.QB, Slot.SUPER_FLEX, Slot.BN)
    assert legal_slots("K", roster) == (Slot.K, Slot.BN)
    assert legal_slots("DEF", roster) == (Slot.DEF, Slot.BN)
