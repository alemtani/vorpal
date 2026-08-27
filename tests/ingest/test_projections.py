"""FantasyPros projections parse to counting keys. respx for transport."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from vorpal.contracts import StatRow
from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest import fetch_projections, parse_projections
from vorpal.ingest.client import FantasyProsClient
from vorpal.ingest.fp import parse_adp_map
from vorpal.ingest.projections import attach_adp, to_stat_rows

SEASON = "2026"
FP = "https://api.fantasypros.com/public/v2/json"


def _player(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "fpid": 1,
        "name": "Jane Doe",
        "position_id": "WR",
        "team_id": "KC",
        "player_yahoo_id": "111",
        "stats": {
            "rec_rec": 80.0,
            "rec_yds": 1000.0,
            "points": 250.0,
            "points_ppr": 250.0,
            "points_half": 210.0,
            "games": 17.0,
        },
    }
    payload.update(overrides)
    return payload


def _envelope(*players: dict[str, Any]) -> dict[str, Any]:
    return {"season": SEASON, "week": "0", "players": list(players)}


def _host(player_id: str = "s1", yahoo: str = "111") -> dict[str, Any]:
    return {
        player_id: {
            "player_id": player_id,
            "first_name": "Jane",
            "last_name": "Doe",
            "full_name": "Jane Doe",
            "position": "WR",
            "team": "KC",
            "yahoo_id": int(yahoo) if yahoo.isdigit() else yahoo,
        }
    }


def _stat_keys(rows: tuple[StatRow, ...]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        keys.update(row.stats)
    return keys


def test_no_fantasy_point_key_survives_into_statrow(
    projections_payload: dict[str, Any],
) -> None:
    records = parse_projections(projections_payload)
    assert records
    leaked = [
        key
        for row in records
        for key in row.stats
        if key.startswith("pts_") and not key.startswith("pts_allow")
    ]
    assert leaked == []
    for row in records:
        assert "points" not in row.stats
        assert "points_ppr" not in row.stats
        assert "pts_ppr" not in row.stats


def test_synthetic_points_columns_are_stripped() -> None:
    records = parse_projections(_envelope(_player()))
    assert len(records) == 1
    assert "points" not in records[0].stats
    assert records[0].stats["rec"] == 80.0
    assert records[0].stats["rec_yd"] == 1000.0


def test_fixture_maps_pass_yds_and_keeps_dst_sack(
    projections_payload: dict[str, Any],
) -> None:
    records = parse_projections(projections_payload)
    by_name = {row.name: row for row in records}
    assert "Josh Allen" in by_name
    assert by_name["Josh Allen"].stats["pass_yd"] > 0
    assert "pass_yds" not in by_name["Josh Allen"].stats
    dst = [row for row in records if row.position in {"DST", "DEF"}]
    assert dst
    assert "pa" not in dst[0].stats
    assert dst[0].stats["sack"] > 0
    kickers = [row for row in records if row.position == "K"]
    assert kickers
    assert "fg" not in kickers[0].stats
    assert kickers[0].stats["xpm"] > 0


def test_gp_is_lifted_onto_the_row() -> None:
    row = parse_projections(_envelope(_player()))[0]
    assert row.gp == 17.0
    assert "gp" not in row.stats
    assert "games" not in row.stats


def test_join_uses_yahoo_id_not_fp_id() -> None:
    records = parse_projections(_envelope(_player()))
    rows, _banners = to_stat_rows(records, _host("s1"), season=SEASON)
    assert rows[0].player_id == "s1"
    assert rows[0].source == "fantasypros"


def test_adp_attaches_by_yahoo_id() -> None:
    records = parse_projections(_envelope(_player()))
    records = attach_adp(records, {"111": 33.0})
    assert records[0].adp == 33.0


def test_unjoined_row_banners_when_the_gate_still_passes() -> None:
    records = parse_projections(
        _envelope(
            _player(),
            _player(
                fpid=99,
                name="Ghost",
                position_id="RB",
                team_id="ZZ",
                player_yahoo_id="",
            ),
        )
    )
    records = attach_adp(records, {"1": 1.0})
    rows, banners = to_stat_rows(records, _host("s1"), season=SEASON)
    assert len(rows) == 1
    assert any(banner.code == "projection_join_miss" for banner in banners)


def test_sleeper_id_on_fp_row_joins_as_host_id() -> None:
    records = parse_projections(_envelope(_player(sleeper_id="s1", player_yahoo_id="")))
    rows, _banners = to_stat_rows(records, _host("s1"), season=SEASON)
    assert rows[0].player_id == "s1"


def test_list_payload_and_team_fallback() -> None:
    records = parse_projections(
        [
            "junk",
            _player(player_team_id="", team_id="", team="KC", stats={"rec": 5}),
            {"fpid": 3, "name": "NoTeam", "position_id": "WR", "rec_yds": 7},
        ]
    )
    by_id = {row.fp_id: row for row in records}
    assert by_id["1"].team == "KC"
    assert by_id["1"].stats["rec"] == 5.0
    assert by_id["3"].team is None
    assert by_id["3"].stats["rec_yd"] == 7.0


def test_adp_from_nested_stats() -> None:
    adp = parse_adp_map([{"players": [{"fpid": 1, "stats": {"adp": 9.5}}]}])
    assert adp["1"] == 9.5


def test_adp_skips_rows_without_a_number() -> None:
    assert parse_adp_map([{"players": [{"fpid": 1, "name": "X"}]}]) == {}
    assert parse_adp_map([{"players": [{"fpid": 2, "stats": {"rush_yds": 1}}]}]) == {}
    assert parse_adp_map(["nope"]) == {}


def test_market_only_when_adp_and_no_stats() -> None:
    records = parse_projections(_envelope(_player(stats={"games": 17.0}, fpid=1)))
    records = attach_adp(records, {"1": 12.0})
    rows, _banners = to_stat_rows(records, _host("s1"), season=SEASON)
    assert rows[0].market_only is True
    assert rows[0].adp == 12.0
    assert rows[0].stats == {}


def test_adp_from_rank_ave(adp_payload: dict[str, Any]) -> None:
    adp = parse_adp_map([adp_payload])
    assert adp
    first = adp_payload["players"][0]
    pid = str(first["player_id"])
    yahoo = str(first["player_yahoo_id"])
    expected = float(first["rank_ave"])
    assert adp[pid] == pytest.approx(expected)
    assert adp[yahoo] == pytest.approx(expected)


def test_weekly_player_rows_are_dropped() -> None:
    weekly = _player(fpid=2, week=3)
    records = parse_projections(_envelope(_player(), weekly))
    assert [row.fp_id for row in records] == ["1"]


def test_blank_player_id_is_dropped() -> None:
    records = parse_projections(_envelope(_player(fpid="", player_id=""), _player()))
    assert [row.fp_id for row in records] == ["1"]


def test_payload_that_is_not_a_list_or_object_raises_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="list or object"):
        parse_projections("nope")


def test_empty_season_totals_raise_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="No season"):
        parse_projections(_envelope(_player(week=1)))


def test_non_numeric_stat_values_are_skipped() -> None:
    payload = _player(stats={"rec_rec": "nope", "rec_yds": 10, "points": 9})
    row = parse_projections(_envelope(payload))[0]
    assert "rec" not in row.stats
    assert row.stats["rec_yd"] == 10.0


def test_duplicate_player_id_keeps_the_last_season_row() -> None:
    first = _player(stats={"rec_rec": 1.0, "games": 1})
    second = _player(stats={"rec_rec": 9.0, "games": 1})
    row = parse_projections(_envelope(first, second))[0]
    assert row.stats["rec"] == 9.0


@respx.mock
def test_fetch_projections_hits_fantasypros_once() -> None:
    route = respx.get(url__regex=r".*/nfl/2026/projections.*").mock(
        return_value=httpx.Response(200, json=_envelope(_player()))
    )
    http = httpx.Client()
    client = FantasyProsClient(api_key="k", http=http)
    first = fetch_projections(SEASON, client=client)
    second = fetch_projections(SEASON, client=client)
    assert first == second
    assert route.call_count == 6
    url = str(route.calls[0].request.url)
    assert "week=0" in url


@respx.mock
def test_fetch_http_error_is_platform_error() -> None:
    respx.get(url__regex=r".*/projections.*").mock(return_value=httpx.Response(500))
    client = FantasyProsClient(api_key="k", http=httpx.Client())
    with pytest.raises(PlatformError, match="FantasyPros"):
        fetch_projections(SEASON, client=client)


@respx.mock
def test_fetch_invalid_json_is_platform_error() -> None:
    respx.get(url__regex=r".*/projections.*").mock(
        return_value=httpx.Response(
            200, text="not-json", headers={"content-type": "text/plain"}
        )
    )
    client = FantasyProsClient(api_key="k", http=httpx.Client())
    with pytest.raises(PlatformError):
        fetch_projections(SEASON, client=client)


@respx.mock
def test_fetch_timeout_is_platform_error() -> None:
    respx.get(url__regex=r".*/projections.*").mock(
        side_effect=httpx.TimeoutException("slow")
    )
    client = FantasyProsClient(api_key="k", http=httpx.Client())
    with pytest.raises(PlatformError, match="FantasyPros"):
        fetch_projections(SEASON, client=client)
