"""Read-only HTTP for season mode: Sleeper, ESPN, FantasyCalc."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from vorpal.errors import PlatformError

SLEEPER = "https://api.sleeper.app/v1"
SLEEPER_DATA = "https://api.sleeper.com"
ESPN = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leaguedefaults/3"
)
FANTASYCALC = "https://api.fantasycalc.com/values/current"
POSITIONS = ("QB", "RB", "WR", "TE")
ESPN_LIMIT = 1000


def default_cache_dir() -> Path:
    return Path.home() / ".cache" / "vorpal" / "season"


class Source:
    """One method per endpoint. ``/players`` is cached for a calendar day."""

    def __init__(
        self,
        http: httpx.Client | None = None,
        cache_dir: Path | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._http = http or httpx.Client(
            timeout=60.0, headers={"User-Agent": "vorpal-season"}
        )
        self._cache = cache_dir or default_cache_dir()
        self._today = today

    def get(
        self,
        url: str,
        params: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            r = self._http.get(url, params=params, headers=headers)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise PlatformError(f"GET {url}: {e}") from e

    def state(self) -> dict[str, Any]:
        return self.get(f"{SLEEPER}/state/nfl")

    def league(self, league_id: str) -> dict[str, Any]:
        return self.get(f"{SLEEPER}/league/{league_id}")

    def rosters(self, league_id: str) -> list[dict[str, Any]]:
        return self.get(f"{SLEEPER}/league/{league_id}/rosters")

    def users(self, league_id: str) -> list[dict[str, Any]]:
        return self.get(f"{SLEEPER}/league/{league_id}/users")

    def matchups(self, league_id: str, week: int) -> list[dict[str, Any]]:
        return self.get(f"{SLEEPER}/league/{league_id}/matchups/{week}")

    def transactions(self, league_id: str, week: int) -> list[dict[str, Any]]:
        return self.get(f"{SLEEPER}/league/{league_id}/transactions/{week}")

    def players(self) -> dict[str, Any]:
        path = self._cache / f"players-{self._today().isoformat()}.json"
        if path.exists():
            return json.loads(path.read_text())
        data = self.get(f"{SLEEPER}/players/nfl")
        path.parent.mkdir(parents=True, exist_ok=True)
        for old in path.parent.glob("players-*.json"):
            old.unlink()
        path.write_text(json.dumps(data))
        return data

    def _weekly(self, kind: str, season: int, week: int) -> list[dict[str, Any]]:
        params = [("season_type", "regular")] + [("position[]", p) for p in POSITIONS]
        return self.get(f"{SLEEPER_DATA}/{kind}/nfl/{season}/{week}", params=params)

    def stats(self, season: int, week: int) -> list[dict[str, Any]]:
        return self._weekly("stats", season, week)

    def projections(self, season: int, week: int) -> list[dict[str, Any]]:
        return self._weekly("projections", season, week)

    def schedule(self, season: int) -> list[dict[str, Any]]:
        return self.get(f"{SLEEPER_DATA}/schedule/nfl/regular/{season}")

    def espn(self, season: int, week: int) -> dict[str, Any]:
        filt = {
            "players": {
                "limit": ESPN_LIMIT,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            }
        }
        return self.get(
            ESPN.format(season=season),
            params={"view": "kona_player_info", "scoringPeriodId": week},
            headers={"X-Fantasy-Filter": json.dumps(filt)},
        )

    def fantasycalc(self, teams: int, qbs: int, ppr: float) -> list[dict[str, Any]]:
        return self.get(
            FANTASYCALC,
            params={"isDynasty": "false", "numQbs": qbs, "numTeams": teams, "ppr": ppr},
        )
