"""FantasyPros season projections. Counting keys, mapped onto host scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vorpal.contracts import Banner, StatRow
from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest.cache import adp_cache, projection_cache
from vorpal.ingest.client import FantasyProsClient
from vorpal.ingest.fp import (
    fp_adp_value,
    fp_bye,
    fp_host_id,
    fp_name,
    fp_player_id,
    fp_player_list,
    fp_position,
    fp_stats_map,
    fp_team,
    fp_yahoo_id,
    parse_adp_map,
)
from vorpal.ingest.keys import counting_stats, extract_gp
from vorpal.ingest.mapping import MappingRow, check_mapping, map_rows


@dataclass(frozen=True, slots=True)
class ProjectionRecord:
    fp_id: str
    name: str
    position: str
    team: str | None
    yahoo_id: str | None
    host_id: str | None
    stats: dict[str, float]
    gp: float | None
    bye: int | None
    adp: float | None


def parse_projections(payload: Any) -> tuple[ProjectionRecord, ...]:
    """Parse FP season totals. Does not join to a host id."""
    if not isinstance(payload, (dict, list)):
        raise DataRefusal("Projections payload is not a list or object.")
    seen: dict[str, ProjectionRecord] = {}
    for item in fp_player_list(payload):
        record = _parse_player(item)
        if record is None:
            continue
        seen[record.fp_id] = record
    if not seen:
        raise DataRefusal("No season-total projection rows.")
    return tuple(seen.values())


def _parse_player(item: Mapping[str, Any]) -> ProjectionRecord | None:
    fp_id = fp_player_id(item)
    if not fp_id:
        return None
    week = item.get("week")
    if week not in (None, 0, "0", ""):
        return None
    position = fp_position(item)
    stats_raw = fp_stats_map(item)
    stats = counting_stats(stats_raw, position=position)
    return ProjectionRecord(
        fp_id=fp_id,
        name=fp_name(item),
        position=position,
        team=fp_team(item),
        yahoo_id=fp_yahoo_id(item),
        host_id=fp_host_id(item),
        stats=stats,
        gp=extract_gp(stats_raw),
        bye=fp_bye(item),
        adp=fp_adp_value(item),
    )


def attach_adp(
    records: Sequence[ProjectionRecord], adp_by_id: Mapping[str, float]
) -> tuple[ProjectionRecord, ...]:
    out: list[ProjectionRecord] = []
    for record in records:
        adp = record.adp
        if adp is None:
            if record.fp_id in adp_by_id:
                adp = adp_by_id[record.fp_id]
            elif record.yahoo_id and record.yahoo_id in adp_by_id:
                adp = adp_by_id[record.yahoo_id]
        out.append(
            ProjectionRecord(
                fp_id=record.fp_id,
                name=record.name,
                position=record.position,
                team=record.team,
                yahoo_id=record.yahoo_id,
                host_id=record.host_id,
                stats=record.stats,
                gp=record.gp,
                bye=record.bye,
                adp=adp,
            )
        )
    return tuple(out)


def identities_from_projections(
    records: Sequence[ProjectionRecord],
) -> list[MappingRow]:
    return [
        MappingRow(
            player_id=record.fp_id,
            name=record.name,
            position=record.position,
            team=record.team,
            adp=record.adp,
            yahoo_id=record.yahoo_id,
            host_id=record.host_id,
        )
        for record in records
    ]


def to_stat_rows(
    records: Sequence[ProjectionRecord],
    host_players: Mapping[str, Any],
    *,
    season: str,
    allow_name_match: bool = True,
) -> tuple[tuple[StatRow, ...], tuple[Banner, ...]]:
    """Join FP projection rows onto host player ids. Runs the 98% gate."""
    identities = identities_from_projections(records)
    report = map_rows(identities, host_players, allow_name_match=allow_name_match)
    check_mapping(report)
    by_fp = {record.fp_id: record for record in records}
    rows: list[StatRow] = []
    for hit in report.hits:
        record = by_fp[hit.source_player_id]
        rows.append(
            StatRow(
                player_id=hit.host_player_id,
                source="fantasypros",
                week=None,
                season=season,
                stats=record.stats,
                adp=record.adp,
                gp=record.gp,
                market_only=not record.stats,
            )
        )
    banners: list[Banner] = []
    if report.misses:
        banners.append(
            Banner(
                code="projection_join_miss",
                message=(
                    f"{len(report.misses)} FantasyPros projection rows "
                    "could not be joined to a host player."
                ),
            )
        )
    return tuple(rows), tuple(banners)


def fetch_projections(
    season: str,
    *,
    client: FantasyProsClient,
    scoring: str = "PPR",
) -> Any:
    if season in projection_cache:
        return projection_cache[season]
    data = client.get_projections(season, scoring=scoring)
    projection_cache[season] = data
    return data


def fetch_adp(
    season: str,
    *,
    client: FantasyProsClient,
    scoring: str,
    position: str,
) -> Any:
    key = (season, scoring, position)
    if key in adp_cache:
        return adp_cache[key]
    data = client.get_adp(season, scoring=scoring, position=position)
    adp_cache[key] = data
    return data


def load_adp_map(
    season: str,
    *,
    client: FantasyProsClient,
    scoring: str,
    variant_position: str,
) -> tuple[dict[str, float], tuple[Banner, ...]]:
    """Load ADP. 2QB/OP empty list falls back to ALL and banners."""
    banners: list[Banner] = []
    try:
        payload = fetch_adp(
            season, client=client, scoring=scoring, position=variant_position
        )
    except (PlatformError, DataRefusal):
        return {}, (
            Banner(code="adp_missing", message="FantasyPros ADP was not used."),
        )
    adp = parse_adp_map([payload])
    if adp or variant_position == "ALL":
        if not adp:
            banners.append(
                Banner(code="adp_missing", message="FantasyPros ADP was not used.")
            )
        return adp, tuple(banners)
    try:
        fallback = fetch_adp(season, client=client, scoring=scoring, position="ALL")
    except (PlatformError, DataRefusal):
        return {}, (
            Banner(code="adp_missing", message="FantasyPros ADP was not used."),
        )
    adp = parse_adp_map([fallback])
    if adp:
        banners.append(
            Banner(
                code="adp_1qb_market",
                message="Superflex ADP was empty; 1QB FantasyPros ADP was used.",
            )
        )
    else:
        banners.append(
            Banner(code="adp_missing", message="FantasyPros ADP was not used.")
        )
    return adp, tuple(banners)
