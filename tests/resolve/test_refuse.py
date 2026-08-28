"""One test per SPEC.md §2 refusal. Each uses the correct class."""

from __future__ import annotations

import pytest
from helpers import (
    COLUMNS,
    OPERATOR,
    STARTER_SLOTS,
    complete_order,
    make_draft,
    make_league,
)

from vorpal.contracts import LeagueFormat, Slot
from vorpal.errors import DataRefusal, UnsupportedLeague, UserRefusal
from vorpal.resolve import resolve


def _attached(**league_overrides: object):
    draft = make_draft()
    league = make_league(**league_overrides)
    return resolve(
        draft,
        operator=OPERATOR,
        league=league,
        stat_columns=COLUMNS,
    )


def test_refuse_keeper_format() -> None:
    with pytest.raises(UnsupportedLeague, match="[Kk]eeper"):
        _attached(format=LeagueFormat.KEEPER)


def test_refuse_dynasty_format() -> None:
    with pytest.raises(UnsupportedLeague, match="[Dd]ynasty"):
        _attached(format=LeagueFormat.DYNASTY)


def test_refuse_taxi_slots() -> None:
    with pytest.raises(UnsupportedLeague, match="[Tt]axi"):
        _attached(taxi_slots=1)


def test_refuse_unknown_type_absent() -> None:
    with pytest.raises(UnsupportedLeague, match="unknown"):
        _attached(format=LeagueFormat.UNKNOWN)


def test_refuse_unknown_type_not_in_0_1_2() -> None:
    # SleeperHost maps type 9 to UNKNOWN. Resolve sees the mapped format.
    with pytest.raises(UnsupportedLeague, match="unknown"):
        _attached(format=LeagueFormat.UNKNOWN, max_keepers=0, taxi_slots=0)


def test_refuse_idp_slot_codes() -> None:
    positions = STARTER_SLOTS + (Slot.DL, Slot.BN)
    with pytest.raises(UnsupportedLeague, match="IDP"):
        _attached(roster_positions=positions)


def test_refuse_auction_draft() -> None:
    with pytest.raises(UnsupportedLeague, match="[Aa]uction"):
        resolve(
            make_draft(type="auction"),
            operator=OPERATOR,
            league=make_league(),
            stat_columns=COLUMNS,
        )


def test_refuse_linear_draft() -> None:
    with pytest.raises(UnsupportedLeague, match="[Ll]inear"):
        resolve(
            make_draft(type="linear"),
            operator=OPERATOR,
            league=make_league(),
            stat_columns=COLUMNS,
        )


def test_refuse_reversal_round() -> None:
    with pytest.raises(UnsupportedLeague, match="reversal"):
        resolve(
            make_draft(reversal_round=3),
            operator=OPERATOR,
            league=make_league(),
            stat_columns=COLUMNS,
        )


def test_refuse_complete_order_operator_missing() -> None:
    draft = make_draft(draft_order=complete_order(operator_slot=None))
    with pytest.raises(UserRefusal, match="complete"):
        resolve(
            draft,
            operator=OPERATOR,
            league=make_league(),
            explicit_slot=2,
            stat_columns=COLUMNS,
        )


def test_refuse_partial_order_operator_missing_without_slot() -> None:
    draft = make_draft(draft_order={"user_01": 1, "user_02": 2})
    with pytest.raises(UserRefusal, match="partial"):
        resolve(
            draft,
            operator=OPERATOR,
            league=make_league(),
            stat_columns=COLUMNS,
        )


def test_refuse_attached_draft_without_league() -> None:
    with pytest.raises(DataRefusal, match="league"):
        resolve(make_draft(), operator=OPERATOR, stat_columns=COLUMNS)


def test_refuse_league_id_mismatch() -> None:
    with pytest.raises(DataRefusal, match="does not match"):
        resolve(
            make_draft(league_id="league_a"),
            operator=OPERATOR,
            league=make_league(league_id="league_b"),
            stat_columns=COLUMNS,
        )


def test_refuse_mock_without_scoring_league() -> None:
    with pytest.raises(UserRefusal, match="scoring-source"):
        resolve(
            make_draft(league_id=None, draft_order=None),
            operator=OPERATOR,
            stat_columns=COLUMNS,
        )
