"""HTTP transport for api.sleeper.app. Parse is SleeperHost. No live calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vorpal.contracts import Draft, Host, League, Pick, Player, User
from vorpal.errors import PlatformError
from vorpal.platform import LeagueClient
from vorpal.sleeper import SleeperClient, backoff_seconds

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sleeper"
BASE = "https://api.sleeper.app/v1"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(
    cache_path: Path,
    clock: Any,
    sleep: Any,
    **kwargs: Any,
) -> SleeperClient:
    return SleeperClient(
        players_cache_path=cache_path,
        clock=clock,
        sleep=sleep,
        **kwargs,
    )


def _tiny_draft(status: str, start_time: int) -> dict[str, Any]:
    return {
        "draft_id": "d1",
        "status": status,
        "type": "snake",
        "sport": "nfl",
        "season": "2026",
        "season_type": "regular",
        "league_id": "lg1",
        "start_time": start_time,
        "settings": {"teams": 12, "rounds": 15, "pick_timer": 60},
        "metadata": {"scoring_type": "ppr"},
    }


@respx.mock
def test_get_draft_parses_snake_redraft_fixture(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    payload = _load("draft_snake_redraft.json")
    respx.get(f"{BASE}/draft/draft_snake_redraft").mock(
        return_value=httpx.Response(200, json=payload)
    )
    draft = _client(cache_path, clock, sleep).get_draft("draft_snake_redraft")
    assert isinstance(draft, Draft)
    assert draft.host is Host.SLEEPER
    assert draft.draft_id == "draft_snake_redraft"
    assert draft.status == "complete"
    assert draft.league_id == "league_snake_redraft"
    assert draft.teams == 12


@respx.mock
def test_get_draft_keeps_null_league_id_on_standalone_mock(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    respx.get(f"{BASE}/draft/draft_mock_standalone").mock(
        return_value=httpx.Response(200, json=_load("draft_mock_standalone.json"))
    )
    draft = _client(cache_path, clock, sleep).get_draft("draft_mock_standalone")
    assert draft.league_id is None
    assert draft.status == "complete"


@respx.mock
def test_draft_status_comes_from_status_not_start_time(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    respx.get(f"{BASE}/draft/mid").mock(
        return_value=httpx.Response(200, json=_load("draft_mid_draft.json"))
    )
    past = _tiny_draft("pre_draft", start_time=1)
    future = _tiny_draft("drafting", start_time=9_999_999_999_999)
    respx.get(f"{BASE}/draft/pre").mock(return_value=httpx.Response(200, json=past))
    respx.get(f"{BASE}/draft/live").mock(return_value=httpx.Response(200, json=future))
    client = _client(cache_path, clock, sleep)
    assert client.get_draft("mid").status == "paused"
    assert client.get_draft("pre").status == "pre_draft"
    assert client.get_draft("live").status == "drafting"


@respx.mock
def test_get_picks_parses_fixture(cache_path: Path, clock: Any, sleep: Any) -> None:
    respx.get(f"{BASE}/draft/draft_snake_redraft/picks").mock(
        return_value=httpx.Response(200, json=_load("picks_snake_redraft.json"))
    )
    picks = _client(cache_path, clock, sleep).get_picks("draft_snake_redraft")
    assert isinstance(picks, tuple)
    assert picks
    assert all(isinstance(pick, Pick) for pick in picks)
    assert picks[0].pick_no == 1


@respx.mock
def test_get_league_parses_fixture(cache_path: Path, clock: Any, sleep: Any) -> None:
    respx.get(f"{BASE}/league/league_snake_redraft").mock(
        return_value=httpx.Response(200, json=_load("league_snake_redraft.json"))
    )
    league = _client(cache_path, clock, sleep).get_league("league_snake_redraft")
    assert isinstance(league, League)
    assert league.league_id == "league_snake_redraft"
    assert league.host is Host.SLEEPER


@respx.mock
def test_get_user_parses_fixture(cache_path: Path, clock: Any, sleep: Any) -> None:
    respx.get(f"{BASE}/user/operator").mock(
        return_value=httpx.Response(200, json=_load("user_operator.json"))
    )
    user = _client(cache_path, clock, sleep).get_user("operator")
    assert isinstance(user, User)
    assert user.user_id == "user_operator"
    assert user.username == "operator"
    assert user.is_bot is False


@respx.mock
def test_get_players_parses_fixture_and_does_not_treat_search_rank_as_adp(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    payload = _load("players.json")
    assert "search_rank" in next(iter(payload.values()))
    respx.get(f"{BASE}/players/nfl").mock(
        return_value=httpx.Response(200, json=payload)
    )
    players = _client(cache_path, clock, sleep).get_players()
    kupp = players["4039"]
    assert isinstance(kupp, Player)
    assert kupp.host is Host.SLEEPER
    assert not hasattr(kupp, "search_rank")
    assert not hasattr(kupp, "adp")
    assert "ARI" in players
    assert players["ARI"].position == "DEF"


@respx.mock
def test_get_players_does_not_filter_inactive(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    payload = {
        "1": {
            "player_id": "1",
            "first_name": "Active",
            "last_name": "One",
            "position": "RB",
            "active": True,
            "team": "KC",
            "search_rank": 3,
        },
        "2": {
            "player_id": "2",
            "first_name": "Inactive",
            "last_name": "Two",
            "position": "RB",
            "active": False,
            "team": None,
            "search_rank": 9999999,
        },
    }
    respx.get(f"{BASE}/players/nfl").mock(
        return_value=httpx.Response(200, json=payload)
    )
    players = _client(cache_path, clock, sleep).get_players()
    assert set(players) == {"1", "2"}
    assert players["2"].active is False


@respx.mock
def test_http_error_maps_to_platform_error(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    respx.get(f"{BASE}/draft/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(PlatformError, match="404"):
        _client(cache_path, clock, sleep).get_draft("missing")


@respx.mock
def test_network_error_maps_to_platform_error(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    respx.get(f"{BASE}/league/x").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(PlatformError, match="failed"):
        _client(cache_path, clock, sleep).get_league("x")


@respx.mock
def test_timeout_maps_to_platform_error(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    respx.get(f"{BASE}/user/slow").mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(PlatformError, match="failed"):
        _client(cache_path, clock, sleep).get_user("slow")


@respx.mock
def test_invalid_json_maps_to_platform_error(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    respx.get(f"{BASE}/draft/bad").mock(
        return_value=httpx.Response(200, text="not-json")
    )
    with pytest.raises(PlatformError, match="invalid JSON"):
        _client(cache_path, clock, sleep).get_draft("bad")


@respx.mock
def test_shape_failure_maps_to_platform_error_and_returns_nothing(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    respx.get(f"{BASE}/draft/empty").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/draft/d/picks").mock(
        return_value=httpx.Response(200, json=[{"pick_no": 1}, "nope"])
    )
    client = _client(cache_path, clock, sleep)
    with pytest.raises(PlatformError):
        client.get_draft("empty")
    with pytest.raises(PlatformError, match="pick is not an object"):
        client.get_picks("d")


@respx.mock
def test_backoff_sleeps_then_resets_on_success(
    cache_path: Path, clock: Any, sleep: Any, slept: list[float]
) -> None:
    route = respx.get(f"{BASE}/draft/d1")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(500),
        httpx.Response(500),
        httpx.Response(500),
        httpx.Response(200, json=_tiny_draft("drafting", 1)),
        httpx.Response(200, json=_tiny_draft("drafting", 1)),
    ]
    client = _client(cache_path, clock, sleep)
    for _ in range(4):
        with pytest.raises(PlatformError):
            client.get_draft("d1")
    assert client.consecutive_failures == 4
    assert slept == [5.0, 15.0, 45.0]
    assert backoff_seconds(4) == 45.0
    client.get_draft("d1")
    assert client.consecutive_failures == 0
    assert slept == [5.0, 15.0, 45.0, 45.0]
    clock.advance(1.0)
    client.get_draft("d1")
    assert slept == [5.0, 15.0, 45.0, 45.0]


@respx.mock
def test_rate_limit_spaces_calls_under_1000_per_minute(
    cache_path: Path, clock: Any, sleep: Any, slept: list[float]
) -> None:
    respx.get(f"{BASE}/user/operator").mock(
        return_value=httpx.Response(200, json=_load("user_operator.json"))
    )
    client = _client(cache_path, clock, sleep)
    client.get_user("operator")
    client.get_user("operator")
    assert slept == [pytest.approx(60.0 / 1000.0)]


@respx.mock
def test_players_cache_fetches_once_across_two_calls_in_one_day(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    route = respx.get(f"{BASE}/players/nfl").mock(
        return_value=httpx.Response(200, json=_load("players.json"))
    )
    client = _client(cache_path, clock, sleep)
    first = client.get_players()
    clock.advance(86399.0)
    second = client.get_players()
    assert route.call_count == 1
    assert first == second
    assert cache_path.is_file()


@respx.mock
def test_players_cache_refetches_after_one_day(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    route = respx.get(f"{BASE}/players/nfl").mock(
        return_value=httpx.Response(200, json=_load("players.json"))
    )
    client = _client(cache_path, clock, sleep)
    client.get_players()
    clock.advance(86400.0)
    client.get_players()
    assert route.call_count == 2


@respx.mock
def test_corrupt_players_cache_is_a_miss(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("not-json", encoding="utf-8")
    respx.get(f"{BASE}/players/nfl").mock(
        return_value=httpx.Response(200, json=_load("players.json"))
    )
    players = _client(cache_path, clock, sleep).get_players()
    assert "4039" in players


def test_default_players_cache_path_is_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Any, sleep: Any
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    client = SleeperClient(clock=clock, sleep=sleep)
    expected = tmp_path / ".cache" / "vorpal" / "sleeper_players.json"
    assert client.players_cache_path == expected


def test_close_owned_client_and_leave_injected_open(
    cache_path: Path, clock: Any, sleep: Any
) -> None:
    owned = _client(cache_path, clock, sleep)
    owned.close()
    http = httpx.Client()
    injected = _client(cache_path, clock, sleep, http=http)
    injected.close()
    assert not http.is_closed
    http.close()


@respx.mock
def test_default_clock_and_sleep_come_from_time(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vorpal.sleeper.client.time.time", lambda: 0.0)
    slept: list[float] = []
    monkeypatch.setattr("vorpal.sleeper.client.time.sleep", slept.append)
    respx.get(f"{BASE}/user/operator").mock(
        return_value=httpx.Response(200, json=_load("user_operator.json"))
    )
    client = SleeperClient(players_cache_path=cache_path)
    try:
        client.get_user("operator")
        client.get_user("operator")
    finally:
        client.close()
    assert slept == pytest.approx([60.0 / 1000.0])


def test_get_players_carries_the_external_ids_the_join_needs(
    tmp_path: Path,
) -> None:
    """Ingest joins on yahoo_id. It reaches ingest as a generic external id."""
    payload = json.loads((FIXTURES / "players.json").read_text(encoding="utf-8"))
    with respx.mock(base_url=BASE) as mock:
        mock.get("/players/nfl").mock(return_value=httpx.Response(200, json=payload))
        client = SleeperClient(players_cache_path=tmp_path / "players.json")
        players = client.get_players()
        cached = client.get_players()
        client.close()
    assert players == cached
    assert any(("yahoo", "30182") in player.external_ids for player in players.values())


def test_the_client_satisfies_the_league_client_protocol() -> None:
    """The CLI depends on the protocol, never on this class."""
    assert issubclass(SleeperClient, LeagueClient)
