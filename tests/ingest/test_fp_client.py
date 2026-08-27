"""FantasyProsClient groups HTTP. Rate limit is one lock for all threads."""

from __future__ import annotations

import httpx
import pytest
import respx

from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest.client import FantasyProsClient, require_api_key


@respx.mock
def test_get_projections_sends_week_zero_and_api_key() -> None:
    route = respx.get(url__regex=r".*/nfl/2026/projections.*").mock(
        return_value=httpx.Response(200, json={"players": []})
    )
    client = FantasyProsClient(api_key="secret", http=httpx.Client())
    client.get_projections("2026", scoring="HALF")
    assert route.call_count == 6
    request = route.calls[0].request
    assert request.url.params.get("week") == "0"
    assert request.url.params.get("scoring") == "HALF"
    assert request.url.params.get("position") == "QB"
    assert request.headers.get("x-api-key") == "secret"
    positions = {call.request.url.params.get("position") for call in route.calls}
    assert positions == {"QB", "RB", "WR", "TE", "K", "DST"}


@respx.mock
def test_get_projections_merges_bare_lists() -> None:
    respx.get(url__regex=r".*/nfl/2026/projections.*").mock(
        return_value=httpx.Response(
            200, json=[{"fpid": 1, "name": "X", "position_id": "QB"}]
        )
    )
    client = FantasyProsClient(api_key="k", http=httpx.Client())
    payload = client.get_projections("2026")
    assert isinstance(payload, list)
    assert payload[0]["fpid"] == 1


@respx.mock
def test_connect_error_is_platform_error() -> None:
    respx.get(url__regex=r".*fantasypros.com/.*").mock(
        side_effect=httpx.ConnectError("nope")
    )
    client = FantasyProsClient(api_key="k", http=httpx.Client())
    with pytest.raises(PlatformError, match="failed"):
        client.get_projections("2026")


def test_require_api_key_raises_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="API key"):
        require_api_key(None)
    assert require_api_key("k") == "k"


@respx.mock
def test_rate_limit_lock_spaces_calls() -> None:
    respx.get(url__regex=r".*fantasypros.com/.*").mock(
        return_value=httpx.Response(200, json={"players": []})
    )
    slept: list[float] = []
    client = FantasyProsClient(
        api_key="k",
        http=httpx.Client(),
        min_interval_s=1.1,
        sleep=slept.append,
        clock=lambda: 0.0,
    )
    client.get_projections("2026")
    client.get_adp("2026", scoring="PPR", position="ALL")
    assert slept == [1.1] * 6
