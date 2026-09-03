"""A scoring preset is a borrowed source. Slots and market come from the mock."""

from __future__ import annotations

from helpers import COLUMNS, OPERATOR, make_counts, make_draft

from vorpal.contracts import AdpVariant, Slot
from vorpal.platform.presets import preset_league
from vorpal.resolve import resolve


def _mock(**counts: int) -> object:
    return make_draft(
        league_id=None,
        draft_order=None,
        slot_counts=make_counts(**counts),
    )


def test_preset_scoring_flows_into_the_config() -> None:
    result = resolve(
        _mock(),
        operator=OPERATOR,
        scoring_league=preset_league("half", "2026"),
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    assert result.config.scoring["rec"] == 0.5
    assert result.config.adp_variant is AdpVariant.HALF_PPR


def test_superflex_comes_from_the_mock_not_the_preset() -> None:
    """The preset is plain ppr. The mock's SUPER_FLEX slot must still drive the

    2QB market and the OP ECR position.
    """
    result = resolve(
        _mock(super_flex=1),
        operator=OPERATOR,
        scoring_league=preset_league("ppr", "2026"),
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    assert Slot.SUPER_FLEX in result.config.slots
    assert result.config.adp_variant is AdpVariant.TWO_QB
    assert result.ecr_position == "OP"


def test_a_preset_source_names_itself_in_the_borrowed_banner() -> None:
    result = resolve(
        _mock(),
        operator=OPERATOR,
        scoring_league=preset_league("ppr", "2026"),
        explicit_slot=1,
        stat_columns=COLUMNS,
    )
    borrowed = next(b for b in result.config.banners if b.code == "scoring_borrowed")
    assert "sleeper-default-ppr" in borrowed.message
