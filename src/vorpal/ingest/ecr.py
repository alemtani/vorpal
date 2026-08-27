"""FantasyPros consensus rankings. Down never blocks a draft."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vorpal.contracts import Banner, EcrRow
from vorpal.errors import PlatformError
from vorpal.ingest.cache import ecr_cache
from vorpal.ingest.client import FantasyProsClient
from vorpal.ingest.fp import (
    fp_bye,
    fp_host_id,
    fp_name,
    fp_player_id,
    fp_player_list,
    fp_position,
    fp_team,
    fp_yahoo_id,
)
from vorpal.ingest.keys import as_float, as_int
from vorpal.ingest.mapping import HostPlayerIndex, MappingRow, normalize_pos

ECR_MISSING = Banner(
    code="ecr_missing",
    message="FantasyPros is down; board has no ECR.",
)


def parse_ecr(
    payloads: Sequence[Any],
    host_players: Mapping[str, Any],
) -> tuple[tuple[EcrRow, ...], tuple[Banner, ...]]:
    """Join FP ranks onto host ids. First list wins when the same host id repeats."""
    index = HostPlayerIndex(host_players)
    rows: dict[str, EcrRow] = {}
    join_misses = 0
    team_mismatches = 0
    for payload in payloads:
        for item in fp_player_list(payload):
            parsed = _parse_fp_rank(item)
            if parsed is None:
                continue
            hit = index.join(parsed, allow_name_match=True)
            if hit is None:
                join_misses += 1
                continue
            if hit.team_mismatch:
                team_mismatches += 1
            if hit.host_player_id in rows:
                continue
            rows[hit.host_player_id] = EcrRow(
                player_id=hit.host_player_id,
                name=fp_name(item),
                team=fp_team(item),
                position=normalize_pos(fp_position(item)) or fp_position(item),
                bye=fp_bye(item),
                rank_ecr=as_int(item.get("rank_ecr")) or 0,
                rank_min=as_int(item.get("rank_min")) or 0,
                rank_max=as_int(item.get("rank_max")) or 0,
                rank_std=as_float(item.get("rank_std")) or 0.0,
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


def _parse_fp_rank(item: Mapping[str, Any]) -> MappingRow | None:
    rank_ecr = as_int(item.get("rank_ecr"))
    rank_min = as_int(item.get("rank_min"))
    rank_max = as_int(item.get("rank_max"))
    rank_std = as_float(item.get("rank_std"))
    if rank_ecr is None or rank_min is None or rank_max is None or rank_std is None:
        return None
    return MappingRow(
        player_id=fp_player_id(item) or fp_name(item),
        name=fp_name(item),
        position=fp_position(item),
        team=fp_team(item),
        adp=None,
        yahoo_id=fp_yahoo_id(item),
        host_id=fp_host_id(item),
    )


def fetch_ecr(
    season: str,
    *,
    scoring: str,
    superflex: bool,
    host_players: Mapping[str, Any],
    client: FantasyProsClient | None = None,
) -> tuple[tuple[EcrRow, ...], tuple[Banner, ...]]:
    key = (season, scoring, superflex)
    if key in ecr_cache:
        return ecr_cache[key]
    missing: tuple[tuple[EcrRow, ...], tuple[Banner, ...]] = ((), (ECR_MISSING,))
    if client is None or not client.api_key:
        ecr_cache[key] = missing
        return missing
    try:
        payloads = client.get_ecr_payloads(season, scoring=scoring, superflex=superflex)
    except (PlatformError, ValueError, TypeError, OSError):
        ecr_cache[key] = missing
        return missing
    result = parse_ecr(payloads, host_players)
    ecr_cache[key] = result
    return result
