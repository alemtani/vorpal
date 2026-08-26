"""FantasyPros ECR. Join miss is a banner. Down must not block a draft."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vorpal.contracts import Banner
from vorpal.ingest import fetch_ecr, parse_ecr

SEASON = "2026"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fp(*parts: str) -> dict[str, Any]:
    path = FIXTURES.joinpath("fantasypros", *parts)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_join_on_yahoo_id(sleeper_players: dict[str, Any]) -> None:
    rows, banners = parse_ecr([_fp("consensus_rankings_ppr_qb.json")], sleeper_players)
    by_name = {row.name: row for row in rows}
    assert "Josh Allen" in by_name
    assert by_name["Josh Allen"].player_id == "4984"
    assert by_name["Josh Allen"].rank_ecr == 1
    assert by_name["Josh Allen"].bye == 7
    assert isinstance(by_name["Josh Allen"].rank_std, float)
    assert all(isinstance(banner, Banner) for banner in banners)


def test_join_miss_omits_ecr_and_banners_the_count(
    sleeper_players: dict[str, Any],
) -> None:
    payload = {
        "players": [
            {
                "player_name": "Josh Allen",
                "player_team_id": "BUF",
                "player_position_id": "QB",
                "player_yahoo_id": "30977",
                "player_bye_week": "7",
                "rank_ecr": 1,
                "rank_min": "1",
                "rank_max": "2",
                "rank_std": "0.18",
            },
            {
                "player_name": "Nobody McGhost",
                "player_team_id": "ZZ",
                "player_position_id": "RB",
                "player_yahoo_id": "999999",
                "rank_ecr": 99,
                "rank_min": "90",
                "rank_max": "110",
                "rank_std": "1.0",
            },
        ]
    }
    rows, banners = parse_ecr([payload], sleeper_players)
    assert [row.name for row in rows] == ["Josh Allen"]
    miss = next(banner for banner in banners if banner.code == "ecr_join_miss")
    assert "1" in miss.message
    assert "Nobody McGhost" not in {row.name for row in rows}


def test_dst_joins_on_name_when_yahoo_id_is_null(
    sleeper_players: dict[str, Any],
) -> None:
    rows, banners = parse_ecr([_fp("consensus_rankings_ppr_dst.json")], sleeper_players)
    by_id = {row.player_id: row for row in rows}
    assert "HOU" in by_id
    assert by_id["HOU"].name == "Houston Texans"
    assert by_id["HOU"].position == "DEF"
    assert by_id["HOU"].bye == 8
    # FP JAC vs Sleeper JAX is a name+pos hit with a team mismatch flag.
    assert "JAX" in by_id
    assert any(banner.code == "ecr_team_mismatch" for banner in banners)


def test_malformed_payload_does_not_raise(sleeper_players: dict[str, Any]) -> None:
    rows, banners = parse_ecr(
        [
            "not-an-object",
            {"players": "nope"},
            {"players": [None, {"player_name": "X"}]},
            {"players": [{"player_name": "NoRank"}]},
        ],
        {**sleeper_players, "bad": "not-a-row"},
    )
    assert rows == ()
    assert banners == ()


def test_rank_and_bye_coercion(sleeper_players: dict[str, Any]) -> None:
    payload = {
        "players": [
            {
                "player_name": "Josh Allen",
                "player_team_id": "BUF",
                "player_position_id": "QB",
                "player_yahoo_id": "30977",
                "player_bye_week": "7",
                "rank_ecr": "1",
                "rank_min": "1",
                "rank_max": "4",
                "rank_std": "0.50",
            }
        ]
    }
    # yahoo 30977 is Josh Allen in the recorded players subset (player_id 4984).
    rows, _banners = parse_ecr([payload, payload], sleeper_players)
    assert len(rows) == 1
    assert rows[0].rank_ecr == 1
    assert rows[0].rank_min == 1
    assert rows[0].rank_max == 4
    assert rows[0].rank_std == pytest.approx(0.5)
    assert rows[0].bye == 7


@respx.mock
def test_fantasypros_down_banners_ecr_missing_and_returns_no_rows(
    sleeper_players: dict[str, Any],
) -> None:
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(503, json={"error": "down"})
    )
    rows, banners = fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=False,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
    )
    assert rows == ()
    assert any(banner.code == "ecr_missing" for banner in banners)


@respx.mock
def test_fetch_ecr_type_error_is_ecr_missing(
    sleeper_players: dict[str, Any],
) -> None:
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        side_effect=TypeError("broken")
    )
    rows, banners = fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=False,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
    )
    assert rows == ()
    assert any(banner.code == "ecr_missing" for banner in banners)


@respx.mock
def test_missing_api_key_is_ecr_missing_without_a_call(
    sleeper_players: dict[str, Any],
) -> None:
    route = respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(200, json={"players": []})
    )
    rows, banners = fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=False,
        sleeper_players=sleeper_players,
        fp_api_key=None,
    )
    assert rows == ()
    assert any(banner.code == "ecr_missing" for banner in banners)
    assert route.call_count == 0


@respx.mock
def test_fetch_ecr_uses_scoring_and_positions(
    sleeper_players: dict[str, Any],
) -> None:
    def _reply(request: httpx.Request) -> httpx.Response:
        position = request.url.params.get("position")
        scoring = request.url.params.get("scoring")
        assert scoring == "HALF"
        return httpx.Response(
            200,
            json={"players": [], "position_id": position, "scoring": scoring},
        )

    route = respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        side_effect=_reply
    )
    fetch_ecr(
        SEASON,
        scoring="HALF",
        superflex=False,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
    )
    positions = {call.request.url.params.get("position") for call in route.calls}
    assert positions == {"QB", "RB", "WR", "TE", "K", "DST"}
    assert "OP" not in positions


@respx.mock
def test_superflex_fetches_op_not_skill_positions(
    sleeper_players: dict[str, Any],
) -> None:
    route = respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(200, json={"players": []})
    )
    fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=True,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
    )
    positions = {call.request.url.params.get("position") for call in route.calls}
    assert positions == {"OP", "K", "DST"}
    assert "QB" not in positions


@respx.mock
def test_fetch_ecr_is_cached(
    sleeper_players: dict[str, Any],
) -> None:
    route = respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(200, json={"players": []})
    )
    fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=False,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
    )
    fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=False,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
    )
    assert route.call_count == 6


@respx.mock
def test_fetch_ecr_spaces_calls_when_asked(
    sleeper_players: dict[str, Any],
) -> None:
    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(
        return_value=httpx.Response(200, json={"players": []})
    )
    slept: list[float] = []
    fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=True,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
        min_interval_s=1.1,
        sleep=slept.append,
    )
    assert slept == [1.1, 1.1]


@respx.mock
def test_fetch_then_parse_live_fixture_shape(
    sleeper_players: dict[str, Any],
) -> None:
    qb = _fp("consensus_rankings_ppr_qb.json")

    def _reply(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("position") == "QB":
            return httpx.Response(200, json=qb)
        return httpx.Response(200, json={"players": []})

    respx.get(url__regex=r"https://api.fantasypros.com/.*").mock(side_effect=_reply)
    rows, banners = fetch_ecr(
        SEASON,
        scoring="PPR",
        superflex=False,
        sleeper_players=sleeper_players,
        fp_api_key="test-key",
    )
    assert any(row.name == "Josh Allen" for row in rows)
    assert not any(banner.code == "ecr_missing" for banner in banners)
