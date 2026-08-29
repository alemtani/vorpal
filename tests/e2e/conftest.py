"""Wire both hosts to the synthetic league. No live network."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from league import (
    FANTASYPROS,
    ROSTER,
    SEASON,
    SLEEPER,
    consensus,
    host_players,
    load,
    projections,
)

from vorpal import cli
from vorpal.ingest import clear_caches


@pytest.fixture(autouse=True)
def _no_forecast_cache() -> Iterator[None]:
    clear_caches()
    yield
    clear_caches()


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    """Both hosts, wired to the synthetic league. Every route is overridable."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{SLEEPER}/draft/draft_snake_redraft", name="draft").mock(
            return_value=httpx.Response(
                200, json=load("sleeper", "draft_snake_redraft.json")
            )
        )
        mock.get(f"{SLEEPER}/draft/draft_snake_redraft/picks", name="picks").mock(
            return_value=httpx.Response(200, json=[])
        )
        mock.get(f"{SLEEPER}/league/league_snake_redraft", name="league").mock(
            return_value=httpx.Response(
                200, json=load("sleeper", "league_snake_redraft.json")
            )
        )
        mock.get(f"{SLEEPER}/user/operator", name="user").mock(
            return_value=httpx.Response(200, json=load("sleeper", "user_operator.json"))
        )
        mock.get(f"{SLEEPER}/players/nfl", name="players").mock(
            return_value=httpx.Response(200, json=host_players())
        )
        for position, _count in ROSTER:
            mock.get(
                f"{FANTASYPROS}/nfl/{SEASON}/projections",
                params__contains={"position": position},
                name=f"projections_{position}",
            ).mock(return_value=httpx.Response(200, json=projections(position)))
        mock.get(
            f"{FANTASYPROS}/nfl/{SEASON}/consensus-rankings",
            params__contains={"type": "ADP"},
            name="adp",
        ).mock(return_value=httpx.Response(200, json=consensus(kind="ADP")))
        mock.get(
            f"{FANTASYPROS}/nfl/{SEASON}/consensus-rankings",
            params__contains={"type": "draft"},
            name="ecr",
        ).mock(return_value=httpx.Response(200, json=consensus(kind="draft")))
        yield mock


@pytest.fixture(autouse=True)
def _fp_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FANTASYPROS_API_KEY", "test-key")
    # Live FantasyPros is one call a second. Eight waits per case is a minute
    # of test suite for a rate limit no mock enforces.
    monkeypatch.setattr(cli, "FP_MIN_INTERVAL_S", 0.0)
