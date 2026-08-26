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

SEASON = "2026"
PROJECTIONS_URL = "https://api.sleeper.com/projections/nfl/2026"


def _proj(player_id: str = "1", **stats: float) -> dict[str, Any]:
    body = {
        "rec": 80.0,
        "pts_ppr": 200.0,
        "adp_ppr": 12.0,
        "gp": 17.0,
    }
    body.update(stats)
    return {
        "player_id": player_id,
        "season": SEASON,
        "week": None,
        "company": "rotowire",
        "player": {
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "WR",
            "team": "KC",
        },
        "stats": body,
    }


def _sleeper(player_id: str = "1") -> dict[str, Any]:
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


@respx.mock
def test_projections_down_without_override_is_data_refusal() -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(DataRefusal, match="override"):
        load_stat_rows(SEASON, AdpVariant.PPR, sleeper_players=_sleeper())


@respx.mock
def test_projections_down_with_override_replaces_stats_wholesale(
    tmp_path: Path,
) -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(503))
    path = tmp_path / "override.csv"
    path.write_text(_csv(), encoding="utf-8")
    rows, banners = load_stat_rows(
        SEASON,
        AdpVariant.PPR,
        sleeper_players=_sleeper(),
        override_path=path,
    )
    assert len(rows) == 1
    assert rows[0].source == "override"
    assert rows[0].adp == 12.4
    assert rows[0].stats == {"rec": 80.0, "rec_yd": 1000.0}
    assert "pts_ppr" not in rows[0].stats
    assert any(banner.code == "projections_override" for banner in banners)


@respx.mock
def test_load_stat_rows_from_projections_host() -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(200, json=[_proj()]))
    rows, banners = load_stat_rows(SEASON, AdpVariant.PPR, sleeper_players=_sleeper())
    assert rows[0].source == "rotowire"
    assert rows[0].stats["rec"] == 80.0
    assert "pts_ppr" not in rows[0].stats
    assert banners == ()


@respx.mock
def test_load_stat_rows_mapping_under_98_is_data_refusal() -> None:
    other = _proj("2")
    other["player"] = {
        "first_name": "Other",
        "last_name": "Person",
        "position": "RB",
        "team": "SF",
    }
    respx.get(PROJECTIONS_URL).mock(
        return_value=httpx.Response(200, json=[_proj("1"), other])
    )
    with pytest.raises(DataRefusal, match="98%"):
        load_stat_rows(SEASON, AdpVariant.PPR, sleeper_players=_sleeper("1"))


@respx.mock
def test_bad_projection_shape_falls_back_to_override(tmp_path: Path) -> None:
    respx.get(PROJECTIONS_URL).mock(
        return_value=httpx.Response(200, json={"nope": True})
    )
    path = tmp_path / "override.csv"
    path.write_text(_csv(), encoding="utf-8")
    rows, banners = load_stat_rows(
        SEASON,
        AdpVariant.PPR,
        sleeper_players=_sleeper(),
        override_path=path,
    )
    assert rows[0].source == "override"
    assert any(banner.code == "projections_override" for banner in banners)


@respx.mock
def test_bad_projection_shape_without_override_is_data_refusal() -> None:
    respx.get(PROJECTIONS_URL).mock(
        return_value=httpx.Response(200, json={"nope": True})
    )
    with pytest.raises(DataRefusal, match="list"):
        load_stat_rows(SEASON, AdpVariant.PPR, sleeper_players=_sleeper())


@respx.mock
def test_override_does_not_name_match_when_ids_differ(tmp_path: Path) -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(503))
    path = tmp_path / "override.csv"
    path.write_text(
        "player_id,adp,rec,name,team,pos\ncsv-1,1,10,Jane Doe,KC,WR\n",
        encoding="utf-8",
    )
    with pytest.raises(DataRefusal, match="98%|ADP|map"):
        load_stat_rows(
            SEASON,
            AdpVariant.PPR,
            sleeper_players=_sleeper("1"),
            override_path=path,
        )


@respx.mock
def test_load_forecast_returns_stats_and_ecr() -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(200, json=[_proj()]))
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(
            200,
            json={
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
            },
        )
    )
    stats, ecr, banners = load_forecast(
        SEASON,
        AdpVariant.PPR,
        ecr_scoring="PPR",
        superflex=False,
        sleeper_players=_sleeper(),
        fp_api_key="test-key",
    )
    assert stats[0].player_id == "1"
    assert ecr[0].player_id == "1"
    assert ecr[0].rank_ecr == 5
    assert ecr[0].bye == 10
    assert not any(banner.code == "ecr_missing" for banner in banners)


@respx.mock
def test_load_forecast_does_not_block_when_fantasypros_is_down() -> None:
    respx.get(PROJECTIONS_URL).mock(return_value=httpx.Response(200, json=[_proj()]))
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(500)
    )
    stats, ecr, banners = load_forecast(
        SEASON,
        AdpVariant.PPR,
        ecr_scoring="PPR",
        superflex=False,
        sleeper_players=_sleeper(),
        fp_api_key="test-key",
    )
    assert stats
    assert ecr == ()
    assert any(banner.code == "ecr_missing" for banner in banners)
