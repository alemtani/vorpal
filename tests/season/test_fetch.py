"""Season HTTP. respx stands in for every host."""

import json
from datetime import date

import httpx
import pytest
import respx

from vorpal.errors import PlatformError
from vorpal.season.fetch import SLEEPER, SLEEPER_DATA, Source, default_cache_dir


@pytest.fixture
def source(tmp_path):
    http = httpx.Client()
    yield Source(http=http, cache_dir=tmp_path, today=lambda: date(2026, 10, 20))
    http.close()


def test_default_cache_dir_is_under_home() -> None:
    assert default_cache_dir().parts[-2:] == ("vorpal", "season")


@respx.mock
def test_league_endpoints(source) -> None:
    respx.get(f"{SLEEPER}/state/nfl").respond(json={"week": 7})
    respx.get(f"{SLEEPER}/league/L").respond(json={"league_id": "L"})
    respx.get(f"{SLEEPER}/league/L/rosters").respond(json=[{"roster_id": 1}])
    respx.get(f"{SLEEPER}/league/L/users").respond(json=[{"user_id": "u"}])
    respx.get(f"{SLEEPER}/league/L/matchups/6").respond(json=[])
    respx.get(f"{SLEEPER}/league/L/transactions/6").respond(json=[])
    assert source.state() == {"week": 7}
    assert source.league("L") == {"league_id": "L"}
    assert source.rosters("L") == [{"roster_id": 1}]
    assert source.users("L") == [{"user_id": "u"}]
    assert source.matchups("L", 6) == []
    assert source.transactions("L", 6) == []


@respx.mock
def test_weekly_stats_and_projections_ask_for_skill_positions(source) -> None:
    stats = respx.get(f"{SLEEPER_DATA}/stats/nfl/2026/6").respond(json=[{"a": 1}])
    respx.get(f"{SLEEPER_DATA}/projections/nfl/2026/7").respond(json=[])
    respx.get(f"{SLEEPER_DATA}/schedule/nfl/regular/2026").respond(json=[])
    assert source.stats(2026, 6) == [{"a": 1}]
    assert source.projections(2026, 7) == []
    assert source.schedule(2026) == []
    q = str(stats.calls[0].request.url)
    assert "position%5B%5D=QB" in q and "position%5B%5D=TE" in q


@respx.mock
def test_players_are_fetched_once_a_day(source, tmp_path) -> None:
    (tmp_path / "players-2026-10-19.json").write_text("{}")
    route = respx.get(f"{SLEEPER}/players/nfl").respond(json={"1": {"x": 1}})
    assert source.players() == {"1": {"x": 1}}
    assert source.players() == {"1": {"x": 1}}
    assert route.call_count == 1
    assert [p.name for p in tmp_path.iterdir()] == ["players-2026-10-20.json"]


@respx.mock
def test_espn_sends_the_filter_header(source) -> None:
    route = respx.get(url__startswith="https://lm-api-reads.fantasy.espn.com").respond(
        json={"players": []}
    )
    assert source.espn(2026, 7) == {"players": []}
    req = route.calls[0].request
    assert json.loads(req.headers["X-Fantasy-Filter"])["players"]["limit"] == 1000
    assert "scoringPeriodId=7" in str(req.url)


@respx.mock
def test_fantasycalc_params(source) -> None:
    route = respx.get("https://api.fantasycalc.com/values/current").respond(json=[])
    assert source.fantasycalc(10, 2, 1) == []
    assert "numQbs=2" in str(route.calls[0].request.url)


@respx.mock
def test_http_errors_become_platform_errors(source) -> None:
    respx.get(f"{SLEEPER}/state/nfl").respond(status_code=503)
    with pytest.raises(PlatformError, match="state/nfl"):
        source.state()
    respx.get(f"{SLEEPER}/league/L").respond(text="not json")
    with pytest.raises(PlatformError):
        source.league("L")


def test_source_builds_its_own_client() -> None:
    assert Source()._http is not None
