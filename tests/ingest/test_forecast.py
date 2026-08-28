"""load_stat_rows / load_forecast: override fallback, mapping, ECR never blocks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vorpal.contracts import AdpVariant
from vorpal.errors import DataRefusal
from vorpal.ingest import load_forecast, load_stat_rows
from vorpal.ingest.client import FantasyProsClient

SEASON = "2026"


def _proj(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "fpid": 1,
        "name": "Jane Doe",
        "position_id": "WR",
        "team_id": "KC",
        "player_yahoo_id": "111",
        "stats": {"rec_rec": 80.0, "points_ppr": 200.0, "games": 17.0},
    }
    body.update(overrides)
    return body


def _envelope(*players: dict[str, Any]) -> dict[str, Any]:
    return {"season": SEASON, "week": "0", "players": list(players)}


def _adp(*players: dict[str, Any]) -> dict[str, Any]:
    return {"type": "ADP", "position_id": "ALL", "players": list(players)}


def _host(player_id: str = "1") -> dict[str, Any]:
    return {
        player_id: {
            "player_id": player_id,
            "first_name": "Jane",
            "last_name": "Doe",
            "full_name": "Jane Doe",
            "position": "WR",
            "team": "KC",
            "yahoo_id": 111,
        }
    }


def _csv() -> str:
    return "player_id,adp,rec,rec_yd\n1,12.4,80,1000\n"


def _fp_client() -> FantasyProsClient:
    return FantasyProsClient(api_key="test-key", http=httpx.Client())


def _jane_adp() -> dict[str, Any]:
    return {
        "player_id": 1,
        "player_yahoo_id": "111",
        "rank_ave": "12",
        "rank_ecr": 12,
    }


def _route_fp(projections: Any, adp: Any, ecr: Any | None = None) -> None:
    def _reply(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/projections" in url:
            return httpx.Response(200, json=projections)
        if request.url.params.get("type") == "ADP":
            return httpx.Response(200, json=adp)
        return httpx.Response(200, json=ecr if ecr is not None else {"players": []})

    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(side_effect=_reply)


@respx.mock
def test_projections_down_without_override_is_data_refusal() -> None:
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(DataRefusal, match="override"):
        load_stat_rows(
            SEASON, AdpVariant.PPR, host_players=_host(), client=_fp_client()
        )


@respx.mock
def test_projections_down_with_override_replaces_stats_wholesale(
    tmp_path: Path,
) -> None:
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(503)
    )
    path = tmp_path / "override.csv"
    path.write_text(_csv(), encoding="utf-8")
    rows, banners = load_stat_rows(
        SEASON,
        AdpVariant.PPR,
        host_players=_host(),
        override_path=path,
        client=_fp_client(),
    )
    assert len(rows) == 1
    assert rows[0].source == "override"
    assert rows[0].adp == 12.4
    assert rows[0].stats == {"rec": 80.0, "rec_yd": 1000.0}
    assert "pts_ppr" not in rows[0].stats
    assert any(banner.code == "projections_override" for banner in banners)


@respx.mock
def test_load_stat_rows_from_fantasypros() -> None:
    _route_fp(
        _envelope(_proj()),
        _adp(
            {
                "player_id": 1,
                "player_yahoo_id": "111",
                "rank_ave": "12.0",
                "rank_ecr": 12,
            }
        ),
    )
    rows, banners = load_stat_rows(
        SEASON, AdpVariant.PPR, host_players=_host(), client=_fp_client()
    )
    assert rows[0].source == "fantasypros"
    assert rows[0].player_id == "1"
    assert rows[0].stats["rec"] == 80.0
    assert "points_ppr" not in rows[0].stats
    assert rows[0].adp == 12.0
    assert not any(banner.code == "ecr_missing" for banner in banners)


@respx.mock
def test_load_stat_rows_mapping_under_98_is_data_refusal() -> None:
    other = _proj(
        fpid=2,
        name="Other Person",
        position_id="RB",
        team_id="SF",
        player_yahoo_id="999",
    )
    _route_fp(
        _envelope(_proj(), other),
        _adp(
            {"player_id": 1, "rank_ave": "1", "rank_ecr": 1},
            {"player_id": 2, "rank_ave": "2", "rank_ecr": 2},
        ),
    )
    with pytest.raises(DataRefusal, match="98%"):
        load_stat_rows(
            SEASON,
            AdpVariant.PPR,
            host_players=_host("1"),
            client=_fp_client(),
        )


@respx.mock
def test_bad_projection_shape_falls_back_to_override(tmp_path: Path) -> None:
    respx.get(url__regex=r".*/projections.*").mock(
        return_value=httpx.Response(200, json={"nope": True})
    )
    path = tmp_path / "override.csv"
    path.write_text(_csv(), encoding="utf-8")
    rows, banners = load_stat_rows(
        SEASON,
        AdpVariant.PPR,
        host_players=_host(),
        override_path=path,
        client=_fp_client(),
    )
    assert rows[0].source == "override"
    assert any(banner.code == "projections_override" for banner in banners)


@respx.mock
def test_bad_projection_shape_without_override_is_data_refusal() -> None:
    respx.get(url__regex=r".*/projections.*").mock(
        return_value=httpx.Response(200, json={"nope": True})
    )
    with pytest.raises(DataRefusal, match="season-total"):
        load_stat_rows(
            SEASON, AdpVariant.PPR, host_players=_host(), client=_fp_client()
        )


@respx.mock
def test_override_does_not_name_match_when_ids_differ(tmp_path: Path) -> None:
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(503)
    )
    path = tmp_path / "override.csv"
    path.write_text(
        "player_id,adp,rec,name,team,pos\ncsv-1,1,10,Jane Doe,KC,WR\n",
        encoding="utf-8",
    )
    with pytest.raises(DataRefusal, match="98%|ADP|map"):
        load_stat_rows(
            SEASON,
            AdpVariant.PPR,
            host_players=_host("1"),
            override_path=path,
            client=_fp_client(),
        )


@respx.mock
def test_unmapped_scoring_keys_banner() -> None:
    _route_fp(
        _envelope(_proj()),
        _adp(_jane_adp()),
    )
    _rows, banners = load_stat_rows(
        SEASON,
        AdpVariant.PPR,
        host_players=_host(),
        client=_fp_client(),
        scoring={"rec": 1.0, "pts_allow_0": 10.0},
    )
    assert any(banner.code == "unmapped_scoring_keys" for banner in banners)
    assert "pts_allow_0" in next(
        banner.message for banner in banners if banner.code == "unmapped_scoring_keys"
    )


@respx.mock
def test_load_forecast_returns_stats_and_ecr() -> None:
    ecr = {
        "players": [
            {
                "player_name": "Jane Doe",
                "player_team_id": "KC",
                "player_position_id": "WR",
                "player_yahoo_id": "111",
                "player_bye_week": "10",
                "rank_ecr": 5,
                "rank_min": "3",
                "rank_max": "9",
                "rank_std": "1.2",
            }
        ]
    }
    _route_fp(
        _envelope(_proj()),
        _adp(_jane_adp()),
        ecr,
    )
    stats, ecr_rows, banners = load_forecast(
        SEASON,
        AdpVariant.PPR,
        ecr_scoring="PPR",
        superflex=False,
        host_players=_host(),
        fp_api_key="test-key",
    )
    assert stats[0].player_id == "1"
    assert ecr_rows[0].player_id == "1"
    assert ecr_rows[0].rank_ecr == 5
    assert ecr_rows[0].bye == 10
    assert not any(banner.code == "ecr_missing" for banner in banners)


@respx.mock
def test_load_forecast_does_not_block_when_ecr_is_down() -> None:
    def _reply(request: httpx.Request) -> httpx.Response:
        if "/projections" in str(request.url):
            return httpx.Response(200, json=_envelope(_proj()))
        if request.url.params.get("type") == "ADP":
            return httpx.Response(
                200,
                json=_adp(
                    {
                        "player_id": 1,
                        "player_yahoo_id": "111",
                        "rank_ave": "12",
                        "rank_ecr": 12,
                    }
                ),
            )
        return httpx.Response(500)

    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(side_effect=_reply)
    stats, ecr_rows, banners = load_forecast(
        SEASON,
        AdpVariant.PPR,
        ecr_scoring="PPR",
        superflex=False,
        host_players=_host(),
        fp_api_key="test-key",
    )
    assert stats
    assert ecr_rows == ()
    assert any(banner.code == "ecr_missing" for banner in banners)


@respx.mock
def test_missing_api_key_without_override_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="API key"):
        load_stat_rows(SEASON, AdpVariant.PPR, host_players=_host(), client=None)


@respx.mock
def test_scoring_all_present_has_no_unmapped_banner() -> None:
    _route_fp(
        _envelope(_proj()),
        _adp(_jane_adp()),
    )
    _rows, banners = load_stat_rows(
        SEASON,
        AdpVariant.PPR,
        host_players=_host(),
        client=_fp_client(),
        scoring={"rec": 1.0, "pts_allow_0": 0.0},
    )
    assert not any(banner.code == "unmapped_scoring_keys" for banner in banners)


@respx.mock
def test_load_forecast_accepts_a_fantasypros_client() -> None:
    _route_fp(
        _envelope(_proj()),
        _adp(_jane_adp()),
    )
    stats, _ecr, _banners = load_forecast(
        SEASON,
        AdpVariant.PPR,
        ecr_scoring="PPR",
        superflex=False,
        host_players=_host(),
        client=_fp_client(),
    )
    assert stats[0].player_id == "1"


@respx.mock
def test_two_qb_empty_op_adp_falls_back_and_banners() -> None:
    def _reply(request: httpx.Request) -> httpx.Response:
        if "/projections" in str(request.url):
            return httpx.Response(200, json=_envelope(_proj()))
        if request.url.params.get("type") == "ADP":
            if request.url.params.get("position") == "OP":
                return httpx.Response(200, json=_adp())
            return httpx.Response(
                200,
                json=_adp(
                    {
                        "player_id": 1,
                        "player_yahoo_id": "111",
                        "rank_ave": "12",
                        "rank_ecr": 12,
                    }
                ),
            )
        return httpx.Response(200, json={"players": []})

    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(side_effect=_reply)
    rows, banners = load_stat_rows(
        SEASON, AdpVariant.TWO_QB, host_players=_host(), client=_fp_client()
    )
    assert rows[0].adp == 12.0
    assert any(banner.code == "adp_1qb_market" for banner in banners)


@respx.mock
def test_adp_http_failure_banners_adp_missing() -> None:
    def _reply(request: httpx.Request) -> httpx.Response:
        if "/projections" in str(request.url):
            return httpx.Response(200, json=_envelope(_proj()))
        if request.url.params.get("type") == "ADP":
            return httpx.Response(503)
        return httpx.Response(200, json={"players": []})

    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(side_effect=_reply)
    rows, banners = load_stat_rows(
        SEASON, AdpVariant.PPR, host_players=_host(), client=_fp_client()
    )
    assert rows[0].stats["rec"] == 80.0
    assert any(banner.code == "adp_missing" for banner in banners)


@respx.mock
def test_empty_all_adp_banners_missing() -> None:
    _route_fp(_envelope(_proj()), _adp())
    _rows, banners = load_stat_rows(
        SEASON, AdpVariant.PPR, host_players=_host(), client=_fp_client()
    )
    assert any(banner.code == "adp_missing" for banner in banners)


@respx.mock
def test_two_qb_fallback_adp_also_down() -> None:
    def _reply(request: httpx.Request) -> httpx.Response:
        if "/projections" in str(request.url):
            return httpx.Response(200, json=_envelope(_proj()))
        if request.url.params.get("type") == "ADP":
            if request.url.params.get("position") == "OP":
                return httpx.Response(200, json=_adp())
            return httpx.Response(503)
        return httpx.Response(200, json={"players": []})

    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(side_effect=_reply)
    _rows, banners = load_stat_rows(
        SEASON, AdpVariant.TWO_QB, host_players=_host(), client=_fp_client()
    )
    assert any(banner.code == "adp_missing" for banner in banners)


@respx.mock
def test_two_qb_fallback_all_also_empty() -> None:
    def _reply(request: httpx.Request) -> httpx.Response:
        if "/projections" in str(request.url):
            return httpx.Response(200, json=_envelope(_proj()))
        if request.url.params.get("type") == "ADP":
            return httpx.Response(200, json=_adp())
        return httpx.Response(200, json={"players": []})

    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(side_effect=_reply)
    _rows, banners = load_stat_rows(
        SEASON, AdpVariant.TWO_QB, host_players=_host(), client=_fp_client()
    )
    assert any(banner.code == "adp_missing" for banner in banners)


@respx.mock
def test_fetch_adp_is_cached() -> None:
    from vorpal.ingest.projections import fetch_adp

    route = respx.get(url__regex=r".*consensus-rankings.*").mock(
        return_value=httpx.Response(200, json=_adp())
    )
    client = _fp_client()
    fetch_adp(SEASON, client=client, scoring="PPR", position="ALL")
    fetch_adp(SEASON, client=client, scoring="PPR", position="ALL")
    assert route.call_count == 1
