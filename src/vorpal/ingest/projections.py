"""Sleeper projections: season totals, counting keys, one company."""

from __future__ import annotations

from typing import Any

import httpx

from vorpal.contracts import AdpVariant, StatRow
from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest.cache import HEADERS, projection_cache
from vorpal.ingest.keys import counting_stats, extract_adp, extract_gp
from vorpal.ingest.mapping import MappingRow

EXPECTED_COMPANY = "rotowire"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
PROJECTIONS_HOST = "https://api.sleeper.com"


def parse_projections(payload: Any, adp_variant: AdpVariant) -> tuple[StatRow, ...]:
    if not isinstance(payload, list):
        raise DataRefusal("Projections payload is not a list.")
    companies: set[str] = set()
    kept: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("week") is not None:
            continue
        player_id = str(item.get("player_id") or "")
        if not player_id:
            continue
        companies.add(str(item.get("company") or ""))
        kept.append(item)
    if not kept:
        raise DataRefusal("No season-total projection rows.")
    if companies != {EXPECTED_COMPANY}:
        if len(companies) != 1:
            raise DataRefusal(
                f"Projections mix companies {sorted(companies)}; "
                f"expected only {EXPECTED_COMPANY}."
            )
        raise DataRefusal(
            f"Projections company is {next(iter(companies))!r}, not {EXPECTED_COMPANY}."
        )
    by_id: dict[str, StatRow] = {}
    for item in kept:
        player_id = str(item.get("player_id") or "")
        stats_raw = item.get("stats") if isinstance(item.get("stats"), dict) else {}
        stats = counting_stats(stats_raw)
        season = str(item.get("season") or "")
        by_id[player_id] = StatRow(
            player_id=player_id,
            source=EXPECTED_COMPANY,
            week=None,
            season=season,
            stats=stats,
            adp=extract_adp(stats_raw, adp_variant),
            gp=extract_gp(stats_raw),
            market_only=not stats,
        )
    return tuple(by_id.values())


def identities_from_projections(
    payload: Any,
    adp_variant: AdpVariant,
) -> list[MappingRow]:
    if not isinstance(payload, list):
        return []
    by_id: dict[str, MappingRow] = {}
    for item in payload:
        if not isinstance(item, dict) or item.get("week") is not None:
            continue
        player_id = str(item.get("player_id") or "")
        if not player_id:
            continue
        player = item.get("player") if isinstance(item.get("player"), dict) else {}
        first = str(player.get("first_name") or "")
        last = str(player.get("last_name") or "")
        stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
        team_raw = player.get("team")
        by_id[player_id] = MappingRow(
            player_id=player_id,
            name=f"{first} {last}".strip(),
            position=str(player.get("position") or ""),
            team=None if team_raw in (None, "") else str(team_raw),
            adp=extract_adp(stats, adp_variant),
        )
    return list(by_id.values())


def fetch_projections(season: str, *, client: httpx.Client | None = None) -> Any:
    if season in projection_cache:
        return projection_cache[season]
    if client is None:
        with httpx.Client(
            headers=HEADERS, follow_redirects=True, timeout=120.0
        ) as owned:
            data = _get_projections(owned, season)
    else:
        data = _get_projections(client, season)
    projection_cache[season] = data
    return data


def _get_projections(client: httpx.Client, season: str) -> Any:
    url = f"{PROJECTIONS_HOST}/projections/nfl/{season}"
    params: list[tuple[str, str]] = [("season_type", "regular")]
    params.extend(("position[]", pos) for pos in POSITIONS)
    try:
        response = client.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise PlatformError(f"projections host failed: {exc}") from exc
    except ValueError as exc:
        raise PlatformError("projections host returned invalid JSON") from exc
