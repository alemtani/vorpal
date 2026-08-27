"""Recorded fixtures: snake, standalone mock, superflex."""

from __future__ import annotations

import pytest
from helpers import (
    COLUMNS,
    OPERATOR,
    load_draft,
    load_league,
    load_picks,
    projection_columns,
)

from vorpal.contracts import AdpVariant, Slot
from vorpal.errors import UserRefusal
from vorpal.resolve import resolve


def test_snake_redraft_fixture_slots_scoring_and_seat() -> None:
    draft = load_draft("draft_snake_redraft.json")
    league = load_league("league_snake_redraft.json")
    result = resolve(
        draft,
        operator=OPERATOR,
        league=league,
        picks=load_picks("picks_snake_redraft.json"),
        stat_columns=projection_columns(),
    )
    assert result.config.slots == league.roster_positions
    assert result.config.scoring == league.scoring
    assert result.config.adp_variant is AdpVariant.PPR
    assert result.ecr_position is None
    assert result.seat is not None
    assert result.seat.slot == 2
    assert result.config.slot == 2
    codes = [banner.code for banner in result.config.banners]
    assert "keepers_possible" in codes
    assert "slots_from_mock" not in codes
    assert "unknown_scoring_keys" in codes


def test_superflex_fixture_yields_adp_2qb_and_position_op() -> None:
    draft = load_draft("draft_superflex.json")
    league = load_league("league_superflex.json")
    assert draft.scoring_label == "2qb"
    result = resolve(
        draft,
        operator=OPERATOR,
        league=league,
        stat_columns=projection_columns(),
    )
    assert Slot.SUPER_FLEX in result.config.slots
    assert Slot.DEF not in result.config.slots
    assert result.config.adp_variant is AdpVariant.TWO_QB
    assert result.ecr_position == "OP"
    assert result.config.ecr_scoring == "PPR"
    assert result.seat is not None
    assert result.seat.slot == 7
    codes = [banner.code for banner in result.config.banners]
    assert "unstartable_scoring" in codes


def test_standalone_mock_slots_from_mock_scoring_from_borrowed() -> None:
    mock = load_draft("draft_mock_standalone.json")
    borrowed = load_league("league_snake_redraft.json")
    assert mock.league_id is None
    with pytest.raises(UserRefusal, match="partial"):
        resolve(
            mock,
            operator=OPERATOR,
            scoring_league=borrowed,
            stat_columns=COLUMNS,
        )
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=borrowed,
        explicit_slot=6,
        stat_columns=COLUMNS,
    )
    assert result.config.league_id is None
    assert result.config.scoring_league_id == borrowed.league_id
    assert result.config.scoring == borrowed.scoring
    assert result.config.slots.count(Slot.BN) == 1
    assert Slot.K in result.config.slots
    assert Slot.DEF in result.config.slots
    # Mock label is half_ppr; borrowed rec is 1. The label is not a table.
    assert result.config.adp_variant is AdpVariant.PPR
    codes = [banner.code for banner in result.config.banners]
    assert "slots_from_mock" in codes
    assert "scoring_borrowed" in codes
    borrowed_msg = next(
        banner.message
        for banner in result.config.banners
        if banner.code == "scoring_borrowed"
    )
    assert "disagree" in borrowed_msg.lower()


def test_mid_draft_infers_bench_from_rounds() -> None:
    mock = load_draft("draft_mid_draft.json")
    assert mock.league_id is None
    assert mock.slot_counts.bn is None
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=load_league("league_snake_redraft.json"),
        explicit_slot=2,
        stat_columns=COLUMNS,
    )
    assert result.config.slots.count(Slot.BN) == 3
    assert Slot.K not in result.config.slots
    assert Slot.DEF not in result.config.slots
