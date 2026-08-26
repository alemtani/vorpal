"""ADP variant and ECR scoring come from slots and rec, never from the label."""

from __future__ import annotations

from helpers import (
    COLUMNS,
    OPERATOR,
    SCORING,
    STARTER_SLOTS,
    make_counts,
    make_draft,
    make_league,
)

from vorpal.contracts import AdpVariant, Slot
from vorpal.resolve import resolve


def _resolve(
    *,
    rec: float,
    positions=STARTER_SLOTS + (Slot.BN,) * 5,
    label: str = "ppr",
):
    scoring = dict(SCORING)
    scoring["rec"] = rec
    return resolve(
        make_draft(scoring_label=label),
        operator=OPERATOR,
        league=make_league(scoring=scoring, roster_positions=positions),
        stat_columns=COLUMNS,
    )


def test_super_flex_gives_adp_2qb_and_position_op() -> None:
    positions = (
        Slot.QB,
        Slot.RB,
        Slot.WR,
        Slot.TE,
        Slot.FLEX,
        Slot.SUPER_FLEX,
        Slot.K,
        Slot.BN,
    )
    result = _resolve(rec=1.0, positions=positions, label="ppr")
    assert result.config.adp_variant is AdpVariant.TWO_QB
    assert result.ecr_position == "OP"
    assert result.config.ecr_scoring == "PPR"


def test_op_slot_gives_adp_2qb() -> None:
    positions = STARTER_SLOTS[:6] + (Slot.OP,) + STARTER_SLOTS[6:]
    result = _resolve(rec=0.0, positions=positions, label="std")
    assert result.config.adp_variant is AdpVariant.TWO_QB
    assert result.ecr_position == "OP"


def test_two_qb_slots_give_adp_2qb() -> None:
    positions = (Slot.QB, Slot.QB) + STARTER_SLOTS[1:]
    result = _resolve(rec=1.0, positions=positions, label="ppr")
    assert result.config.adp_variant is AdpVariant.TWO_QB
    assert result.ecr_position == "OP"


def test_rec_at_least_0_75_gives_ppr() -> None:
    result = _resolve(rec=0.75)
    assert result.config.adp_variant is AdpVariant.PPR
    assert result.config.ecr_scoring == "PPR"
    assert result.ecr_position is None


def test_rec_between_0_25_and_0_75_gives_half_ppr() -> None:
    result = _resolve(rec=0.25)
    assert result.config.adp_variant is AdpVariant.HALF_PPR
    assert result.config.ecr_scoring == "HALF"


def test_rec_below_0_25_gives_std() -> None:
    result = _resolve(rec=0.0)
    assert result.config.adp_variant is AdpVariant.STD
    assert result.config.ecr_scoring == "STD"


def test_two_qb_with_nonstandard_rec_summary() -> None:
    positions = (
        Slot.QB,
        Slot.RB,
        Slot.WR,
        Slot.TE,
        Slot.SUPER_FLEX,
        Slot.BN,
    )
    result = _resolve(rec=0.3, positions=positions)
    assert result.config.adp_variant is AdpVariant.TWO_QB
    assert "2QB" in result.config.scoring_summary
    assert "0.3" in result.config.scoring_summary


def test_scoring_label_is_not_a_table() -> None:
    mock = make_draft(
        league_id=None,
        draft_order=None,
        scoring_label="2qb",
        slot_counts=make_counts(super_flex=0, qb=1),
    )
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=make_league(),
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    assert result.config.adp_variant is AdpVariant.PPR
    assert result.ecr_position is None
