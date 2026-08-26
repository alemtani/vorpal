"""FantasyPros consensus rankings. Down never blocks a draft."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from vorpal.contracts import Banner, EcrRow
from vorpal.ingest.cache import HEADERS, ecr_cache
from vorpal.ingest.keys import as_float, as_int
from vorpal.ingest.mapping import (
    normalize_name,
    normalize_pos,
    normalize_team,
    player_display_name,
)

FP_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
FP_SUPERFLEX_POSITIONS = ("OP", "K", "DST")
FP_URL = "https://api.fantasypros.com/public/v2/json/nfl/{season}/consensus-rankings"
ECR_MISSING = Banner(
    code="ecr_missing",
    message="FantasyPros is down; board has no ECR.",
)


@dataclass(frozen=True, slots=True)
class _FpPlayer:
    name: str
    team: str | None
    position: str
    yahoo_id: str | None
    bye: int | None
    rank_ecr: int
    rank_min: int
    rank_max: int
    rank_std: float


def parse_ecr(
    payloads: Sequence[Any],
    sleeper_players: Mapping[str, Any],
) -> tuple[tuple[EcrRow, ...], tuple[Banner, ...]]:
    yahoo, by_name_pos_team, by_name_pos = _player_indexes(sleeper_players)
    rows: dict[str, EcrRow] = {}
    join_misses = 0
    team_mismatches = 0
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        players = payload.get("players")
        if not isinstance(players, list):
            continue
        for item in players:
            if not isinstance(item, dict):
                continue
            parsed = _parse_fp_player(item)
            if parsed is None:
                continue
            host_id, mismatch = _join(parsed, yahoo, by_name_pos_team, by_name_pos)
            if host_id is None:
                join_misses += 1
                continue
            if mismatch:
                team_mismatches += 1
            if host_id in rows:
                continue
            rows[host_id] = EcrRow(
                player_id=host_id,
                name=parsed.name,
                team=parsed.team,
                position=normalize_pos(parsed.position) or parsed.position,
                bye=parsed.bye,
                rank_ecr=parsed.rank_ecr,
                rank_min=parsed.rank_min,
                rank_max=parsed.rank_max,
                rank_std=parsed.rank_std,
            )
    banners: list[Banner] = []
    if join_misses:
        banners.append(
            Banner(
                code="ecr_join_miss",
                message=(
                    f"{join_misses} FantasyPros ranks could not be joined "
                    "to a host player."
                ),
            )
        )
    if team_mismatches:
        banners.append(
            Banner(
                code="ecr_team_mismatch",
                message=(
                    f"{team_mismatches} FantasyPros ranks matched on name "
                    "and position with a team mismatch."
                ),
            )
        )
    return tuple(rows.values()), tuple(banners)


def fetch_ecr(
    season: str,
    *,
    scoring: str,
    superflex: bool,
    sleeper_players: Mapping[str, Any],
    fp_api_key: str | None = None,
    client: httpx.Client | None = None,
    min_interval_s: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[tuple[EcrRow, ...], tuple[Banner, ...]]:
    key = (season, scoring, superflex)
    if key in ecr_cache:
        return ecr_cache[key]
    missing: tuple[tuple[EcrRow, ...], tuple[Banner, ...]] = ((), (ECR_MISSING,))
    if not fp_api_key:
        ecr_cache[key] = missing
        return missing
    positions = FP_SUPERFLEX_POSITIONS if superflex else FP_POSITIONS
    payloads: list[Any] = []
    try:
        if client is None:
            with httpx.Client(
                headers=HEADERS, follow_redirects=True, timeout=60.0
            ) as owned:
                _download_ecr(
                    owned,
                    season=season,
                    scoring=scoring,
                    positions=positions,
                    fp_api_key=fp_api_key,
                    payloads=payloads,
                    min_interval_s=min_interval_s,
                    sleep=sleep,
                )
        else:
            _download_ecr(
                client,
                season=season,
                scoring=scoring,
                positions=positions,
                fp_api_key=fp_api_key,
                payloads=payloads,
                min_interval_s=min_interval_s,
                sleep=sleep,
            )
    except (httpx.HTTPError, ValueError, TypeError, OSError):
        ecr_cache[key] = missing
        return missing
    result = parse_ecr(payloads, sleeper_players)
    ecr_cache[key] = result
    return result


def _download_ecr(
    client: httpx.Client,
    *,
    season: str,
    scoring: str,
    positions: Sequence[str],
    fp_api_key: str,
    payloads: list[Any],
    min_interval_s: float,
    sleep: Callable[[float], None],
) -> None:
    url = FP_URL.format(season=season)
    headers = {**HEADERS, "x-api-key": fp_api_key}
    for index, position in enumerate(positions):
        if index and min_interval_s > 0:
            sleep(min_interval_s)
        response = client.get(
            url,
            params={"position": position, "scoring": scoring},
            headers=headers,
            timeout=60.0,
        )
        response.raise_for_status()
        payloads.append(response.json())


def _parse_fp_player(item: Mapping[str, Any]) -> _FpPlayer | None:
    rank_ecr = as_int(item.get("rank_ecr"))
    rank_min = as_int(item.get("rank_min"))
    rank_max = as_int(item.get("rank_max"))
    rank_std = as_float(item.get("rank_std"))
    if rank_ecr is None or rank_min is None or rank_max is None or rank_std is None:
        return None
    yahoo_raw = item.get("player_yahoo_id")
    yahoo_id = str(yahoo_raw) if yahoo_raw else None
    team_raw = item.get("player_team_id")
    return _FpPlayer(
        name=str(item.get("player_name") or ""),
        team=None if team_raw in (None, "") else str(team_raw),
        position=str(item.get("player_position_id") or ""),
        yahoo_id=yahoo_id,
        bye=as_int(item.get("player_bye_week")),
        rank_ecr=rank_ecr,
        rank_min=rank_min,
        rank_max=rank_max,
        rank_std=rank_std,
    )


def _player_indexes(
    players: Mapping[str, Any],
) -> tuple[
    dict[str, str],
    dict[tuple[str, str, str | None], list[str]],
    dict[tuple[str, str], list[str]],
]:
    yahoo: dict[str, str] = {}
    by_name_pos_team: dict[tuple[str, str, str | None], list[str]] = {}
    by_name_pos: dict[tuple[str, str], list[str]] = {}
    for pid, row in players.items():
        if not isinstance(row, dict):
            continue
        host_id = str(pid)
        yahoo_raw = row.get("yahoo_id")
        if yahoo_raw:
            yahoo.setdefault(str(yahoo_raw), host_id)
        name = normalize_name(player_display_name(row))
        pos = normalize_pos(str(row.get("position") or ""))
        team = normalize_team(
            None if row.get("team") in (None, "") else str(row.get("team"))
        )
        by_name_pos_team.setdefault((name, pos, team), []).append(host_id)
        by_name_pos.setdefault((name, pos), []).append(host_id)
    return yahoo, by_name_pos_team, by_name_pos


def _join(
    parsed: _FpPlayer,
    yahoo: Mapping[str, str],
    by_name_pos_team: Mapping[tuple[str, str, str | None], list[str]],
    by_name_pos: Mapping[tuple[str, str], list[str]],
) -> tuple[str | None, bool]:
    if parsed.yahoo_id and parsed.yahoo_id in yahoo:
        return yahoo[parsed.yahoo_id], False
    name = normalize_name(parsed.name)
    pos = normalize_pos(parsed.position)
    team = normalize_team(parsed.team)
    team_hits = by_name_pos_team.get((name, pos, team), [])
    if len(team_hits) == 1:
        return team_hits[0], False
    pos_hits = by_name_pos.get((name, pos), [])
    if len(pos_hits) == 1:
        return pos_hits[0], True
    return None, False
