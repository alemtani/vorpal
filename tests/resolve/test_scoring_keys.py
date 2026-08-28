"""pass_int is QB. Nonzero keys must hit a column. No silent zeros."""

from __future__ import annotations

from helpers import (
    COLUMNS,
    OPERATOR,
    SCORING,
    load_league,
    make_draft,
    make_league,
)

from vorpal.contracts import Host, Slot
from vorpal.resolve import classify_key, resolve


def test_pass_int_is_qb_not_dst() -> None:
    assert classify_key("pass_int") == "QB"
    assert classify_key("bonus_rush_td_qb") == "QB"
    assert classify_key("int") == "DEF"
    assert classify_key("st_td") == "DEF"
    assert classify_key("fum_rec_td") == "DEF"
    assert classify_key("rec_td") == "OFF"
    assert classify_key("rec") == "OFF"
    assert classify_key("fum") == "OFF"
    assert classify_key("fgm_50p") == "K"
    assert classify_key("idp_tkl") == "IDP"
    assert classify_key("bonus_rec_te") == "OFF"
    assert classify_key("not_a_real_key") is None


def test_unmapped_sleeper_shaped_key_is_not_classified() -> None:
    # Prefix guessing would call this QB. The map must not.
    assert classify_key("pass_invented") is None


def test_classification_is_per_host() -> None:
    assert classify_key("pass_int", Host.SLEEPER) == "QB"
    assert classify_key("pass_int", Host.ESPN) is None


def test_recorded_sleeper_scoring_keys_are_on_the_map() -> None:
    league = load_league("league_snake_redraft.json")
    missing = [key for key in league.scoring if classify_key(key, league.host) is None]
    assert missing == []


def test_missing_rec_key_is_standard_not_a_banner() -> None:
    scoring = dict(SCORING)
    del scoring["rec"]
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(scoring=scoring),
        stat_columns=COLUMNS,
    )
    codes = [banner.code for banner in result.config.banners]
    assert "rec_nonstandard" not in codes
    assert result.config.ecr_scoring == "STD"


def test_stat_columns_none_does_not_itemize_unknown_keys() -> None:
    scoring = dict(SCORING)
    scoring["bonus_weird"] = 3.0
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(scoring=scoring),
        stat_columns=None,
    )
    codes = [banner.code for banner in result.config.banners]
    assert "unknown_scoring_keys" not in codes


def test_idp_scoring_without_idp_slot_is_unstartable() -> None:
    scoring = dict(SCORING)
    scoring["idp_tkl"] = 1.0
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(scoring=scoring),
        stat_columns=COLUMNS | {"idp_tkl"},
    )
    message = next(
        banner.message
        for banner in result.config.banners
        if banner.code == "unstartable_scoring"
    )
    assert "IDP" in message


def test_qb_scoring_without_a_qb_startable_slot() -> None:
    roster = (Slot.RB, Slot.WR, Slot.TE, Slot.FLEX, Slot.BN)
    result = resolve(
        make_draft(),
        operator=OPERATOR,
        league=make_league(roster_positions=roster),
        stat_columns=COLUMNS,
    )
    message = next(
        banner.message
        for banner in result.config.banners
        if banner.code == "unstartable_scoring"
    )
    assert "QB" in message
