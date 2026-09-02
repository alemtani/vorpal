"""FantasyPros paging probe. Public cap vs real pages. Live marker is off in CI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vorpal.ingest.client import FantasyProsClient, PagingProbeResult
from vorpal.ingest.fp import (
    fp_player_list,
    fp_truncated,
    merge_fp_player_payloads,
    paging_added_rows,
)

SEASON = "2026"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fantasypros"


def _capped(*players: dict[str, Any], count: int = 520) -> dict[str, Any]:
    return {
        "count": count,
        "limit": 10,
        "public_api_limited": True,
        "tier": "free",
        "players": list(players),
    }


def _row(pid: int, rank: int) -> dict[str, Any]:
    return {"player_id": pid, "player_name": f"P{pid}", "rank_ecr": rank}


def _client() -> FantasyProsClient:
    return FantasyProsClient(api_key="test-key", http=httpx.Client())


def test_recorded_default_body_is_truncated_not_a_full_board() -> None:
    payload = json.loads(
        (FIXTURES / "consensus_rankings_ppr.json").read_text(encoding="utf-8")
    )
    assert payload["public_api_limited"] is True
    assert payload["limit"] == 10
    assert payload["tier"] == "free"
    assert payload["count"] == 520
    assert len(fp_player_list(payload)) == 10
    assert fp_truncated(payload) is True


def test_empty_envelope_without_count_is_not_truncated() -> None:
    assert fp_truncated({"players": []}) is False
    assert fp_truncated([{"player_id": 1}]) is False


def test_paging_added_rows_is_false_for_the_same_ten() -> None:
    first = _capped(_row(1, 1), _row(2, 2))
    same = _capped(_row(1, 1), _row(2, 2))
    assert paging_added_rows(first, same) is False


def test_paging_added_rows_is_true_when_page_two_is_new_ids() -> None:
    first = _capped(_row(1, 1), _row(2, 2))
    page2 = _capped(_row(11, 11), _row(12, 12))
    assert paging_added_rows(first, page2) is True


def test_merge_keeps_first_id_and_appends_new_rows() -> None:
    first = _capped(_row(1, 1), _row(2, 2), count=4)
    page2 = _capped(_row(2, 2), _row(3, 3), count=4)
    merged = merge_fp_player_payloads([first, page2])
    assert isinstance(merged, dict)
    ids = [row["player_id"] for row in fp_player_list(merged)]
    assert ids == [1, 2, 3]
    assert merged["count"] == 4


def test_probe_result_from_capped_bodies_is_not_real_paging() -> None:
    body = _capped(_row(1, 1), _row(2, 2))
    probe = PagingProbeResult(default=body, page2=body, offset10=body, limit100=body)
    assert probe.paging_is_real is False
    assert probe.still_public_capped is True


def test_probe_result_is_real_when_limit_returns_more_rows() -> None:
    top = _capped(_row(1, 1), _row(2, 2))
    wide = {
        "count": 520,
        "limit": 100,
        "public_api_limited": False,
        "tier": "paid",
        "players": [_row(i, i) for i in range(1, 21)],
    }
    probe = PagingProbeResult(default=top, page2=top, offset10=top, limit100=wide)
    assert probe.paging_is_real is True
    assert probe.still_public_capped is False


@respx.mock
def test_probe_sends_page_offset_and_limit() -> None:
    route = respx.get(url__regex=r".*/consensus-rankings.*").mock(
        return_value=httpx.Response(200, json=_capped(_row(1, 1)))
    )
    probe = _client().probe_consensus_paging(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    params = [dict(call.request.url.params) for call in route.calls]
    assert len(params) == 4
    assert params[0].get("page") is None
    assert params[0].get("offset") is None
    assert params[0].get("limit") is None
    assert params[0]["position"] == "ALL"
    assert params[0]["type"] == "draft"
    extras = [
        {k: v for k, v in item.items() if k in {"page", "offset", "limit"}}
        for item in params[1:]
    ]
    assert {"page": "2"} in extras
    assert {"offset": "10"} in extras
    assert {"limit": "100"} in extras
    assert probe.still_public_capped is True
    assert probe.paging_is_real is False


@respx.mock
def test_truncated_rankings_do_not_merge_when_probes_repeat_the_same_ten() -> None:
    body = _capped(*[_row(i, i) for i in range(1, 11)])
    route = respx.get(url__regex=r".*/consensus-rankings.*").mock(
        return_value=httpx.Response(200, json=body)
    )
    payload = _client().get_consensus_rankings(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    assert [row["player_id"] for row in fp_player_list(payload)] == list(range(1, 11))
    extras = [
        {
            k: v
            for k, v in dict(call.request.url.params).items()
            if k in {"page", "offset", "limit"}
        }
        for call in route.calls
    ]
    assert extras[0] == {}
    assert {"page": "2"} in extras
    assert {"offset": "10"} in extras
    assert {"limit": "100"} in extras
    assert route.call_count == 4


@respx.mock
def test_limit_100_new_rows_are_merged_into_ingest() -> None:
    top = _capped(_row(1, 1), _row(2, 2), count=4)
    wide = {
        "count": 4,
        "limit": 100,
        "public_api_limited": False,
        "tier": "paid",
        "players": [_row(1, 1), _row(2, 2), _row(3, 3), _row(4, 4)],
    }

    def _reply(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("limit") == "100":
            return httpx.Response(200, json=wide)
        if request.url.params.get("limit") == "4":
            return httpx.Response(200, json=wide)
        return httpx.Response(200, json=top)

    respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    ids = [row["player_id"] for row in fp_player_list(payload)]
    assert ids == [1, 2, 3, 4]


@respx.mock
def test_page_two_new_ids_are_merged_and_later_pages_follow() -> None:
    page1 = _capped(_row(1, 1), _row(2, 2), count=6)
    page2 = _capped(_row(3, 3), _row(4, 4), count=6)
    page3 = _capped(_row(5, 5), _row(6, 6), count=6)

    def _reply(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        if page == "2":
            return httpx.Response(200, json=page2)
        if page == "3":
            return httpx.Response(200, json=page3)
        return httpx.Response(200, json=page1)

    respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(SEASON, position="QB", scoring="PPR")
    ids = [row["player_id"] for row in fp_player_list(payload)]
    assert ids == [1, 2, 3, 4, 5, 6]


@respx.mock
def test_offset_new_ids_are_merged() -> None:
    first = _capped(_row(1, 1), _row(2, 2), count=4)
    rest = _capped(_row(3, 3), _row(4, 4), count=4)

    def _reply(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("offset") == "10":
            return httpx.Response(200, json=rest)
        if request.url.params.get("offset") == "4":
            return httpx.Response(200, json=rest)
        if request.url.params.get("offset") == "2":
            return httpx.Response(200, json=rest)
        return httpx.Response(200, json=first)

    respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    ids = [row["player_id"] for row in fp_player_list(payload)]
    assert ids == [1, 2, 3, 4]


@respx.mock
def test_complete_rankings_do_not_probe_when_not_truncated() -> None:
    body = {"players": [_row(1, 1)]}
    route = respx.get(url__regex=r".*/consensus-rankings.*").mock(
        return_value=httpx.Response(200, json=body)
    )
    _client().get_adp(SEASON, scoring="PPR", position="ALL")
    assert route.call_count == 1


@respx.mock
def test_truncated_projections_probe_limit_page_and_offset() -> None:
    top = {
        "count": 32,
        "limit": 10,
        "public_api_limited": True,
        "tier": "free",
        "players": [
            {"fpid": 1, "name": "A", "position_id": "QB"},
            {"fpid": 2, "name": "B", "position_id": "QB"},
        ],
    }
    route = respx.get(url__regex=r".*/projections.*").mock(
        return_value=httpx.Response(200, json=top)
    )
    _client().get_projections(SEASON, scoring="PPR")
    extras = [
        {
            k: v
            for k, v in dict(call.request.url.params).items()
            if k in {"page", "offset", "limit"}
        }
        for call in route.calls
        if call.request.url.params.get("position") == "QB"
    ]
    assert extras[0] == {}
    assert {"limit": "100"} in extras
    assert {"page": "2"} in extras
    assert {"offset": "10"} in extras


@respx.mock
def test_limit_100_still_short_asks_for_catalog_count() -> None:
    first = _capped(_row(1, 1), _row(2, 2), count=6)
    mid = {
        "count": 6,
        "limit": 100,
        "public_api_limited": False,
        "tier": "paid",
        "players": [_row(1, 1), _row(2, 2), _row(3, 3), _row(4, 4)],
    }
    full = {
        "count": 6,
        "limit": 6,
        "public_api_limited": False,
        "tier": "paid",
        "players": [_row(i, i) for i in range(1, 7)],
    }

    def _reply(request: httpx.Request) -> httpx.Response:
        limit = request.url.params.get("limit")
        if limit == "6":
            return httpx.Response(200, json=full)
        if limit == "100":
            return httpx.Response(200, json=mid)
        return httpx.Response(200, json=first)

    respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    ids = [row["player_id"] for row in fp_player_list(payload)]
    assert ids == [1, 2, 3, 4, 5, 6]


@respx.mock
def test_offset_continue_uses_current_length() -> None:
    first = _capped(_row(1, 1), _row(2, 2), count=6)
    second = _capped(_row(3, 3), _row(4, 4), count=6)
    third = _capped(_row(5, 5), _row(6, 6), count=6)

    def _reply(request: httpx.Request) -> httpx.Response:
        offset = request.url.params.get("offset")
        page = request.url.params.get("page")
        limit = request.url.params.get("limit")
        if limit or page:
            return httpx.Response(200, json=first)
        if offset == "10":
            return httpx.Response(200, json=second)
        if offset == "4":
            return httpx.Response(200, json=third)
        return httpx.Response(200, json=first)

    respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    ids = [row["player_id"] for row in fp_player_list(payload)]
    assert ids == [1, 2, 3, 4, 5, 6]


def test_probe_longer_list_without_new_ids_is_real() -> None:
    top = {"players": [_row(1, 1)]}
    wide = {"players": [_row(1, 1), {"player_name": "anon"}]}
    probe = PagingProbeResult(default=top, page2=top, offset10=top, limit100=wide)
    assert probe.paging_is_real is True


def test_still_public_capped_rejects_non_free_bodies() -> None:
    free = _capped(_row(1, 1))
    assert (
        PagingProbeResult(
            default=[], page2=[], offset10=[], limit100=[]
        ).still_public_capped
        is False
    )
    no_flag = {"tier": "free", "players": [_row(1, 1)]}
    assert (
        PagingProbeResult(
            default=no_flag, page2=no_flag, offset10=no_flag, limit100=no_flag
        ).still_public_capped
        is False
    )
    paid = {**free, "tier": "paid"}
    assert (
        PagingProbeResult(
            default=paid, page2=paid, offset10=paid, limit100=paid
        ).still_public_capped
        is False
    )
    eleven = _capped(*[_row(i, i) for i in range(1, 12)], count=12)
    assert (
        PagingProbeResult(
            default=eleven, page2=eleven, offset10=eleven, limit100=eleven
        ).still_public_capped
        is False
    )


def test_merge_bare_lists_and_nameless_rows() -> None:
    merged = merge_fp_player_payloads(
        [[{"player_id": 1}, {"player_name": "X"}], [{"player_id": 1}, {"player_id": 2}]]
    )
    assert isinstance(merged, list)
    assert [row.get("player_id") for row in merged] == [1, None, 2]


@respx.mock
def test_page_three_without_new_ids_stops() -> None:
    page1 = _capped(_row(1, 1), _row(2, 2), count=10)
    page2 = _capped(_row(3, 3), _row(4, 4), count=10)

    def _reply(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    route = respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(SEASON, position="QB", scoring="PPR")
    ids = [row["player_id"] for row in fp_player_list(payload)]
    assert ids == [1, 2, 3, 4]
    pages = [call.request.url.params.get("page") for call in route.calls]
    assert "3" in pages
    assert "4" not in pages


@respx.mock
def test_offset_continue_stops_when_the_next_slice_repeats() -> None:
    first = _capped(_row(1, 1), _row(2, 2), count=10)
    second = _capped(_row(3, 3), _row(4, 4), count=10)

    def _reply(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("limit") or request.url.params.get("page"):
            return httpx.Response(200, json=first)
        if request.url.params.get("offset") == "10":
            return httpx.Response(200, json=second)
        return httpx.Response(200, json=first)

    route = respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    ids = [row["player_id"] for row in fp_player_list(payload)]
    assert ids == [1, 2, 3, 4]
    offsets = [call.request.url.params.get("offset") for call in route.calls]
    assert "10" in offsets
    assert "4" in offsets


@respx.mock
def test_limit_equal_to_catalog_does_not_refetch() -> None:
    first = _capped(_row(1, 1), count=100)
    mid = {
        "count": 100,
        "limit": 100,
        "public_api_limited": False,
        "tier": "paid",
        "players": [_row(i, i) for i in range(1, 21)],
    }

    def _reply(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("limit") == "100":
            return httpx.Response(200, json=mid)
        return httpx.Response(200, json=first)

    route = respx.get(url__regex=r".*/consensus-rankings.*").mock(side_effect=_reply)
    payload = _client().get_consensus_rankings(
        SEASON, position="ALL", scoring="PPR", ranking_type="draft"
    )
    assert len(fp_player_list(payload)) == 20
    limits = [call.request.url.params.get("limit") for call in route.calls]
    assert limits.count("100") == 1


@pytest.mark.live
def test_live_public_key_paging_probe() -> None:
    key = os.environ.get("FANTASYPROS_API_KEY")
    if not key:
        pytest.skip("FANTASYPROS_API_KEY unset")
    client = FantasyProsClient(api_key=key)
    try:
        probe = client.probe_consensus_paging(
            SEASON, position="ALL", scoring="PPR", ranking_type="draft"
        )
    finally:
        client.close()
    default_n = len(fp_player_list(probe.default))
    page2_n = len(fp_player_list(probe.page2))
    offset_n = len(fp_player_list(probe.offset10))
    limit_n = len(fp_player_list(probe.limit100))
    assert default_n >= 0
    if probe.still_public_capped:
        assert page2_n <= 10
        assert offset_n <= 10
        assert limit_n <= 10
        assert probe.paging_is_real is False
    else:
        assert probe.paging_is_real is True
