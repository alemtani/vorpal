"""One test per banner. Never silent-zero a scoring key."""

from __future__ import annotations

from helpers import (
    COLUMNS,
    OPERATOR,
    SCORING,
    make_draft,
    make_league,
    make_pick,
)

from vorpal.contracts import Slot
from vorpal.resolve import resolve


def _codes(result) -> list[str]:
    return [banner.code for banner in result.config.banners]


def _message(result, code: str) -> str:
    matches = [
        banner.message for banner in result.config.banners if banner.code == code
    ]
    assert matches, f"missing banner {code}: {_codes(result)}"
    return matches[0]


def test_banner_keepers_possible_on_redraft() -> None:
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(max_keepers=1),
        stat_columns=COLUMNS,
    )
    assert "keepers_possible" in _codes(result)
    assert "keepers possible" in _message(result, "keepers_possible").lower()


def test_banner_slots_from_mock() -> None:
    mock = make_draft(league_id=None, draft_order=None, scoring_label="half_ppr")
    borrowed = make_league(league_id="league_borrowed")
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=borrowed,
        explicit_slot=4,
        stat_columns=COLUMNS,
    )
    assert "slots_from_mock" in _codes(result)
    assert "mock" in _message(result, "slots_from_mock").lower()


def test_banner_scoring_borrowed_says_they_may_disagree() -> None:
    mock = make_draft(league_id=None, draft_order=None, scoring_label="half_ppr")
    borrowed = make_league(league_id="league_borrowed")
    result = resolve(
        mock,
        operator=OPERATOR,
        scoring_league=borrowed,
        explicit_slot=4,
        stat_columns=COLUMNS,
    )
    message = _message(result, "scoring_borrowed")
    assert "league_borrowed" in message
    assert "disagree" in message.lower()
    assert result.config.scoring_league_id == "league_borrowed"
    assert result.config.league_id is None


def test_banner_rec_not_exactly_1_half_or_0() -> None:
    scoring = dict(SCORING)
    scoring["rec"] = 0.3
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(scoring=scoring),
        stat_columns=COLUMNS,
    )
    assert "rec_nonstandard" in _codes(result)
    assert "0.3" in _message(result, "rec_nonstandard")


def test_banner_unknown_scoring_keys_are_itemised() -> None:
    scoring = dict(SCORING)
    scoring["bonus_weird"] = 3.0
    scoring["other_weird"] = -1.0
    scoring["silent_zero_me"] = 0.0
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(scoring=scoring),
        stat_columns=COLUMNS,
    )
    message = _message(result, "unknown_scoring_keys")
    assert "bonus_weird" in message
    assert "other_weird" in message
    assert "silent_zero_me" not in message
    assert _codes(result).count("unknown_scoring_keys") == 1


def test_banner_classified_keys_with_no_startable_slot_one_line() -> None:
    roster = (
        Slot.QB,
        Slot.RB,
        Slot.WR,
        Slot.TE,
        Slot.FLEX,
        Slot.BN,
    )
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(roster_positions=roster),
        stat_columns=COLUMNS,
    )
    codes = _codes(result)
    assert codes.count("unstartable_scoring") == 1
    message = _message(result, "unstartable_scoring")
    assert "K" in message
    assert "DEF" in message


def test_zero_weight_unknown_key_is_not_a_banner() -> None:
    scoring = dict(SCORING)
    scoring["totally_unknown"] = 0.0
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(scoring=scoring),
        stat_columns=COLUMNS,
    )
    assert "unknown_scoring_keys" not in _codes(result)


def test_drop_truthy_is_keeper_from_the_pool() -> None:
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(max_keepers=1),
        picks=(
            make_pick(player_id="keep_me", is_keeper=True),
            make_pick(player_id="open", is_keeper=False, pick_no=2),
            make_pick(player_id="null_keeper", is_keeper=None, pick_no=3),
        ),
        stat_columns=COLUMNS,
    )
    assert result.keeper_ids == frozenset({"keep_me"})
    assert "open" not in result.keeper_ids
