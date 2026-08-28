"""Thin HTTP client for api.sleeper.app. Parse is ``SleeperHost``."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

from vorpal.contracts import Draft, League, Pick, Player, User
from vorpal.errors import PlatformError
from vorpal.platform import LeagueHost, SleeperHost
from vorpal.sleeper.backoff import backoff_seconds

T = TypeVar("T")

DEFAULT_BASE_URL = "https://api.sleeper.app/v1"
MAX_CALLS_PER_MINUTE = 1000
MIN_INTERVAL_SECONDS = 60.0 / MAX_CALLS_PER_MINUTE
PLAYERS_TTL_SECONDS = 24 * 60 * 60


def default_players_cache_path() -> Path:
    """On-disk /players cache. Tests inject a temp path instead of this."""
    return Path.home() / ".cache" / "vorpal" / "sleeper_players.json"


class SleeperClient:
    """Documented Sleeper reads. Fetch JSON, then ``SleeperHost().parse_*``."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http: httpx.Client | None = None,
        host: LeagueHost | None = None,
        players_cache_path: Path | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_http = http is None
        self._http = http or httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "vorpal"},
        )
        self._host = host if host is not None else SleeperHost()
        self.players_cache_path = (
            players_cache_path
            if players_cache_path is not None
            else default_players_cache_path()
        )
        self._clock = clock if clock is not None else time.time
        self._sleep = sleep if sleep is not None else time.sleep
        self._last_call_at: float | None = None
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        """Failures since the last successful fetch. Backoff uses this."""
        return self._consecutive_failures

    def get_draft(self, draft_id: str) -> Draft:
        """GET /draft/{id}. ``draft.status`` is the state, not start_time."""
        return self._parse(self._get(f"/draft/{draft_id}"), self._host.parse_draft)

    def get_picks(self, draft_id: str) -> tuple[Pick, ...]:
        """GET /draft/{id}/picks."""
        return self._parse(
            self._get(f"/draft/{draft_id}/picks"), self._host.parse_picks
        )

    def get_league(self, league_id: str) -> League:
        """GET /league/{id}."""
        return self._parse(self._get(f"/league/{league_id}"), self._host.parse_league)

    def get_user(self, name_or_id: str) -> User:
        """GET /user/{username_or_id}."""
        return self._parse(self._get(f"/user/{name_or_id}"), self._host.parse_user)

    def get_players(self) -> dict[str, Player]:
        """GET /players/nfl. Cached to disk for one day. No active=true filter."""
        cached = self._read_players_cache()
        if cached is not None:
            return self._host.parse_players(cached)
        payload = self._get("/players/nfl")
        players = self._parse(payload, self._host.parse_players)
        self._write_players_cache(payload)
        return players

    def close(self) -> None:
        """Close an owned httpx client. Injected clients are left open."""
        if self._owns_http:
            self._http.close()

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get(self, path: str) -> Any:
        wait = backoff_seconds(self._consecutive_failures)
        if wait > 0:
            self._sleep(wait)
        now = self._clock()
        if self._last_call_at is not None:
            gap = MIN_INTERVAL_SECONDS - (now - self._last_call_at)
            if gap > 0:
                self._sleep(gap)
        try:
            response = self._http.get(self._url(path))
        except httpx.HTTPError as exc:
            self._last_call_at = self._clock()
            self._consecutive_failures += 1
            raise PlatformError(f"Sleeper GET {path} failed: {exc}") from exc
        self._last_call_at = self._clock()
        if response.status_code >= 400:
            self._consecutive_failures += 1
            raise PlatformError(f"Sleeper GET {path} returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            self._consecutive_failures += 1
            raise PlatformError(f"Sleeper GET {path} returned invalid JSON") from exc

    def _parse(self, payload: Any, parse: Callable[[Any], T]) -> T:
        try:
            result = parse(payload)
        except PlatformError:
            self._consecutive_failures += 1
            raise
        self._consecutive_failures = 0
        return result

    def _read_players_cache(self) -> Any | None:
        try:
            envelope = json.loads(self.players_cache_path.read_text(encoding="utf-8"))
            age = self._clock() - float(envelope["fetched_at"])
            payload = envelope["players"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
        if age >= PLAYERS_TTL_SECONDS or not isinstance(payload, dict):
            return None
        return payload

    def _write_players_cache(self, payload: Any) -> None:
        path = self.players_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"fetched_at": self._clock(), "players": payload}
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(envelope), encoding="utf-8")
        tmp.replace(path)
