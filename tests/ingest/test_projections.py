"""Projections parse to StatRow. Counting keys only. respx for transport."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from vorpal.contracts import AdpVariant, StatRow
from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest import fetch_projections, parse_projections
from vorpal.ingest.projections import identities_from_projections

SEASON = "2026"
PROJECTIONS_URL = "https://api.sleeper.com/projections/nfl/2026"


def _row(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "player_id": "1",
        "season": SEASON,
        "week": None,
        "company": "rotowire",
        "player": {
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "WR",
            "team": "KC",
        },
        "stats": {
            "rec": 80.0,
            "rec_yd": 1000.0,
            "pts_ppr": 250.0,
            "pts_std": 170.0,
            "pts_half_ppr": 210.0,
            "adp_ppr": 12.0,
            "adp_2qb": 20.0,
            "adp_half_ppr": 14.0,
            "adp_std": 10.0,
            "gp": 17.0,
        },
    }
    payload.update(overrides)
    return payload


def _stat_keys(rows: tuple[StatRow, ...]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        keys.update(row.stats)
    return keys


def test_no_pts_star_key_survives_into_statrow(
    projections_payload: list[dict[str, Any]],
) -> None:
    """HARD RULE: fantasy-point columns must not reach StatRow.stats."""
    rows = parse_projections(projections_payload, AdpVariant.PPR)
    assert rows
    leaked = [
        key
        for row in rows
        for key in row.stats
        if key.startswith("pts_") and not key.startswith("pts_allow")
    ]
    assert leaked == []
    for row in rows:
        assert "pts_ppr" not in row.stats
        assert "pts_std" not in row.stats
        assert "pts_half_ppr" not in row.stats


def test_synthetic_pts_star_columns_are_stripped() -> None:
    rows = parse_projections([_row()], AdpVariant.PPR)
    assert len(rows) == 1
    assert "pts_ppr" not in rows[0].stats
    assert "pts_std" not in rows[0].stats
    assert "pts_half_ppr" not in rows[0].stats
    assert rows[0].stats["rec"] == 80.0
    assert rows[0].stats["rec_yd"] == 1000.0


def test_pts_allow_dst_buckets_stay_as_counting_keys() -> None:
    payload = _row(
        player_id="KC",
        player={
            "first_name": "Kansas City",
            "last_name": "Chiefs",
            "position": "DEF",
            "team": "KC",
        },
        stats={
            "sack": 40.0,
            "int": 12.0,
            "pts_allow_0": 2.0,
            "pts_allow_1_6": 3.0,
            "pts_ppr": 99.0,
            "adp_ppr": 80.0,
            "gp": 17.0,
        },
    )
    rows = parse_projections([payload], AdpVariant.PPR)
    assert rows[0].stats["pts_allow_0"] == 2.0
    assert rows[0].stats["pts_allow_1_6"] == 3.0
    assert "pts_ppr" not in rows[0].stats


def test_fixture_def_rows_keep_pts_allow(
    projections_payload: list[dict[str, Any]],
) -> None:
    rows = parse_projections(projections_payload, AdpVariant.PPR)
    def_rows = [row for row in rows if row.player_id == "ARI"]
    assert def_rows
    assert any(key.startswith("pts_allow") for key in def_rows[0].stats)


def test_market_only_rows_are_kept_and_marked(
    projections_payload: list[dict[str, Any]],
) -> None:
    rows = parse_projections(projections_payload, AdpVariant.PPR)
    market = [row for row in rows if row.market_only]
    counted = [row for row in rows if not row.market_only]
    assert market
    assert counted
    for row in market:
        assert row.adp is not None
        assert row.stats == {}
    assert all(row.stats for row in counted)


def test_adp_variant_is_an_argument_not_computed() -> None:
    payload = [_row()]
    assert parse_projections(payload, AdpVariant.PPR)[0].adp == 12.0
    assert parse_projections(payload, AdpVariant.TWO_QB)[0].adp == 20.0
    assert parse_projections(payload, AdpVariant.HALF_PPR)[0].adp == 14.0
    assert parse_projections(payload, AdpVariant.STD)[0].adp == 10.0
    keys = _stat_keys(parse_projections(payload, AdpVariant.PPR))
    assert "adp_ppr" not in keys
    assert "adp_2qb" not in keys


def test_gp_is_lifted_onto_the_row() -> None:
    row = parse_projections([_row()], AdpVariant.PPR)[0]
    assert row.gp == 17.0
    assert "gp" not in row.stats


def test_source_is_the_company() -> None:
    row = parse_projections([_row()], AdpVariant.PPR)[0]
    assert row.source == "rotowire"
    assert row.week is None
    assert row.season == SEASON


def test_weekly_rows_are_dropped() -> None:
    weekly = _row(player_id="2", week=3)
    rows = parse_projections([_row(), weekly, "junk"], AdpVariant.PPR)
    assert [row.player_id for row in rows] == ["1"]


def test_blank_player_id_is_dropped() -> None:
    rows = parse_projections([_row(player_id=""), _row()], AdpVariant.PPR)
    assert [row.player_id for row in rows] == ["1"]


def test_mixed_companies_raise_data_refusal() -> None:
    other = _row(player_id="2", company="espn")
    with pytest.raises(DataRefusal, match="mix companies"):
        parse_projections([_row(), other], AdpVariant.PPR)


def test_non_rotowire_company_raises_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="rotowire"):
        parse_projections([_row(company="espn")], AdpVariant.PPR)


def test_payload_that_is_not_a_list_raises_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="list"):
        parse_projections({"player_id": "1"}, AdpVariant.PPR)


def test_empty_season_totals_raise_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="No season"):
        parse_projections([_row(week=1)], AdpVariant.PPR)


def test_non_numeric_stat_values_are_skipped() -> None:
    payload = _row(stats={"rec": "nope", "rec_yd": 10, "adp_ppr": 1, "pts_ppr": 9})
    row = parse_projections([payload], AdpVariant.PPR)[0]
    assert "rec" not in row.stats
    assert row.stats["rec_yd"] == 10.0


def test_missing_adp_key_leaves_adp_none() -> None:
    payload = _row(stats={"rec": 5.0, "gp": 16.0})
    row = parse_projections([payload], AdpVariant.PPR)[0]
    assert row.adp is None
    assert row.market_only is False


def test_non_object_stats_are_empty() -> None:
    payload = _row()
    payload["stats"] = "nope"
    row = parse_projections([payload], AdpVariant.PPR)[0]
    assert row.stats == {}
    assert row.market_only is True


def test_identities_skip_non_list_weekly_and_blank_ids() -> None:
    assert identities_from_projections({"no": True}, AdpVariant.PPR) == []
    payload = [
        "junk",
        _row(player_id="", week=None),
        _row(player_id="2", week=3),
        _row(player_id="1"),
    ]
    rows = identities_from_projections(payload, AdpVariant.PPR)
    ids = [row.player_id for row in rows]
    assert ids == ["1"]


def test_duplicate_player_id_keeps_the_last_season_row() -> None:
    first = _row(stats={"rec": 1.0, "adp_ppr": 1.0})
    second = _row(stats={"rec": 9.0, "adp_ppr": 2.0})
    row = parse_projections([first, second], AdpVariant.PPR)[0]
    assert row.stats["rec"] == 9.0
    assert row.adp == 2.0


@respx.mock
def test_fetch_projections_hits_sleeper_com_once() -> None:
    route = respx.get(PROJECTIONS_URL).mock(
        return_value=httpx.Response(200, json=[_row()])
    )
    first = fetch_projections(SEASON)
    second = fetch_projections(SEASON)
    assert first == second
    assert route.call_count == 1
    url = str(route.calls[0].request.url)
    assert "season_type=regular" in url
    assert "position" in url


@respx.mock
def test_fetch_projections_without_injected_client() -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(200, json=[_row()]))
    payload = fetch_projections(SEASON)
    assert payload[0]["player_id"] == "1"


@respx.mock
def test_fetch_http_error_is_platform_error() -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(500, json={"e": 1}))
    with pytest.raises(PlatformError, match="projections"):
        fetch_projections(SEASON)


@respx.mock
def test_fetch_invalid_json_is_platform_error() -> None:
    respx.get(PROJECTIONS_URL).mock(
        return_value=httpx.Response(
            200, text="not-json", headers={"content-type": "text/plain"}
        )
    )
    with pytest.raises(PlatformError):
        fetch_projections(SEASON)


@respx.mock
def test_fetch_timeout_is_platform_error() -> None:
    respx.get(PROJECTIONS_URL).mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(PlatformError, match="projections"):
        fetch_projections(SEASON)
