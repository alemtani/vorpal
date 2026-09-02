"""Thin HTTP client for api.fantasypros.com. Parse stays in ingest."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest.cache import HEADERS
from vorpal.ingest.fp import (
    fp_player_list,
    fp_truncated,
    merge_fp_player_payloads,
    paging_added_rows,
)
from vorpal.ingest.keys import as_int

DEFAULT_BASE_URL = "https://api.fantasypros.com/public/v2/json"
PROJECTION_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
ECR_OVERALL = "ALL"
ECR_SUPERFLEX = "OP"
# 520-row cheat sheets at 10/page, plus headroom if a paid key pages larger.
MAX_RANKING_PAGES = 80
PAGING_PROBES: tuple[dict[str, str], ...] = (
    {"limit": "100"},
    {"page": "2"},
    {"offset": "10"},
)


@dataclass(frozen=True, slots=True)
class PagingProbeResult:
    """Raw bodies for the default call plus page=2, offset=10, limit=100."""

    default: Any
    page2: Any
    offset10: Any
    limit100: Any

    @property
    def paging_is_real(self) -> bool:
        """True when a probe returns new ids or a longer player list."""
        base_n = len(fp_player_list(self.default))
        for extra in (self.page2, self.offset10, self.limit100):
            if paging_added_rows(self.default, extra):
                return True
            if len(fp_player_list(extra)) > base_n:
                return True
        return False

    @property
    def still_public_capped(self) -> bool:
        """True when every body stays free-tier, 10 rows, no new ids."""
        if self.paging_is_real:
            return False
        for body in (self.default, self.page2, self.offset10, self.limit100):
            if not isinstance(body, dict):
                return False
            if body.get("public_api_limited") is not True:
                return False
            if body.get("tier") != "free":
                return False
            if len(fp_player_list(body)) > 10:
                return False
        return True


class FantasyProsClient:
    """Documented FantasyPros reads. Fetch JSON; callers parse."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        http: httpx.Client | None = None,
        min_interval_s: float = 0.0,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_http = http is None
        self._http = http or httpx.Client(
            headers=HEADERS,
            follow_redirects=True,
            timeout=timeout,
        )
        self._min_interval_s = min_interval_s
        self._sleep = sleep if sleep is not None else time.sleep
        self._clock = clock if clock is not None else time.time
        self._last_call_at: float | None = None
        self._lock = threading.Lock()

    @property
    def api_key(self) -> str | None:
        return self._api_key

    def close(self) -> None:
        """Close an owned httpx client. Injected clients are left open."""
        if self._owns_http:
            self._http.close()

    def get_projections(self, season: str, *, scoring: str = "PPR") -> Any:
        """GET /nfl/{season}/projections?week=0 per position, then merge.

        A combined ``positions=`` query returns only the default position
        (QB) on the public API. Fetch each position and join the lists.
        """
        merged: list[Any] = []
        envelope: dict[str, Any] = {}
        for position in PROJECTION_POSITIONS:
            payload = self._get_complete(
                f"/nfl/{season}/projections",
                {"week": "0", "position": position, "scoring": scoring},
            )
            if isinstance(payload, dict):
                envelope = payload
            merged.extend(fp_player_list(payload))
        if envelope:
            out = dict(envelope)
            out["players"] = merged
            return out
        return merged

    def get_consensus_rankings(
        self,
        season: str,
        *,
        position: str,
        scoring: str,
        ranking_type: str | None = None,
    ) -> Any:
        """GET /nfl/{season}/consensus-rankings. Merge pages if they add rows."""
        params: dict[str, str] = {"position": position, "scoring": scoring}
        if ranking_type:
            params["type"] = ranking_type
        return self._get_complete(f"/nfl/{season}/consensus-rankings", params)

    def probe_consensus_paging(
        self,
        season: str,
        *,
        position: str,
        scoring: str,
        ranking_type: str | None = None,
    ) -> PagingProbeResult:
        """Hit page=2, offset=10, and limit=100. Record; do not merge."""
        params: dict[str, str] = {"position": position, "scoring": scoring}
        if ranking_type:
            params["type"] = ranking_type
        path = f"/nfl/{season}/consensus-rankings"
        default = self._get(path, params)
        page2 = self._get(path, {**params, "page": "2"})
        offset10 = self._get(path, {**params, "offset": "10"})
        limit100 = self._get(path, {**params, "limit": "100"})
        return PagingProbeResult(
            default=default,
            page2=page2,
            offset10=offset10,
            limit100=limit100,
        )

    def get_ecr_payloads(
        self, season: str, *, scoring: str, superflex: bool
    ) -> list[Any]:
        """One overall list. rank_ecr is draft order, not positional rank.

        1QB uses ``ALL``. Superflex uses ``OP``. Do not stitch QB/RB/WR
        lists: those ranks all start at 1 and break ecr_best.
        """
        position = ECR_SUPERFLEX if superflex else ECR_OVERALL
        # ALL without type is HTTP 400. type=draft is the overall cheat sheet.
        ranking_type = "draft" if position == ECR_OVERALL else None
        return [
            self.get_consensus_rankings(
                season,
                position=position,
                scoring=scoring,
                ranking_type=ranking_type,
            )
        ]

    def get_adp(self, season: str, *, scoring: str, position: str) -> Any:
        """GET consensus-rankings with type=ADP."""
        return self.get_consensus_rankings(
            season, position=position, scoring=scoring, ranking_type="ADP"
        )

    def _get_complete(self, path: str, params: Mapping[str, str]) -> Any:
        """Fetch one list. If ``count`` exceeds rows, try limit/page/offset.

        A free-tier body that repeats the same ten rows is not a page:
        stop after the three probes and keep the first payload.
        """
        first = self._get(path, params)
        if not fp_truncated(first):
            return first
        merged = first
        worked: dict[str, str] | None = None
        for extra in PAGING_PROBES:
            nxt = self._get(path, {**dict(params), **extra})
            if paging_added_rows(merged, nxt):
                merged = merge_fp_player_payloads([merged, nxt])
                worked = extra
                break
        if worked is None:
            return first
        if not fp_truncated(merged):
            return merged
        return self._continue_paging(path, params, worked, merged)

    def _continue_paging(
        self,
        path: str,
        params: Mapping[str, str],
        worked: Mapping[str, str],
        merged: Any,
    ) -> Any:
        base = dict(params)
        if "limit" in worked:
            catalog = as_int(merged.get("count"))
            if catalog is not None and str(catalog) != worked["limit"]:
                nxt = self._get(path, {**base, "limit": str(catalog)})
                if paging_added_rows(merged, nxt):
                    merged = merge_fp_player_payloads([merged, nxt])
        elif "page" in worked:
            for page in range(3, MAX_RANKING_PAGES + 1):
                if not fp_truncated(merged):
                    break
                nxt = self._get(path, {**base, "page": str(page)})
                if not paging_added_rows(merged, nxt):
                    break
                merged = merge_fp_player_payloads([merged, nxt])
        elif "offset" in worked:
            for _step in range(MAX_RANKING_PAGES):
                if not fp_truncated(merged):
                    break
                nxt = self._get(
                    path, {**base, "offset": str(len(fp_player_list(merged)))}
                )
                if not paging_added_rows(merged, nxt):
                    break
                merged = merge_fp_player_payloads([merged, nxt])
        return merged

    def _get(self, path: str, params: Mapping[str, str]) -> Any:
        headers = {**HEADERS}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        url = f"{self._base_url}{path}"
        with self._lock:
            now = self._clock()
            if self._last_call_at is not None and self._min_interval_s > 0:
                gap = self._min_interval_s - (now - self._last_call_at)
                if gap > 0:
                    self._sleep(gap)
            try:
                response = self._http.get(url, params=dict(params), headers=headers)
            except httpx.HTTPError as exc:
                self._last_call_at = self._clock()
                raise PlatformError(f"FantasyPros GET {path} failed: {exc}") from exc
            self._last_call_at = self._clock()
        if response.status_code >= 400:
            raise PlatformError(
                f"FantasyPros GET {path} returned {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise PlatformError(
                f"FantasyPros GET {path} returned invalid JSON"
            ) from exc


def require_api_key(api_key: str | None) -> str:
    if not api_key:
        raise DataRefusal(
            "FantasyPros API key is missing and no override was supplied."
        )
    return api_key
