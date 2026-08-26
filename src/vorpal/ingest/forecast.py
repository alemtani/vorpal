"""Load stats (projections or override) and ECR. ECR never blocks."""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any

import httpx

from vorpal.contracts import AdpVariant, Banner, EcrRow, OverrideRow, StatRow
from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest.cache import HEADERS
from vorpal.ingest.ecr import fetch_ecr
from vorpal.ingest.keys import counting_stats, extract_gp
from vorpal.ingest.mapping import check_mapping, map_rows
from vorpal.ingest.override import identities_from_override, load_override
from vorpal.ingest.projections import (
    fetch_projections,
    identities_from_projections,
    parse_projections,
)


def override_to_stat_rows(
    rows: tuple[OverrideRow, ...], season: str
) -> tuple[StatRow, ...]:
    out: list[StatRow] = []
    for row in rows:
        stats = counting_stats(row.stats)
        out.append(
            StatRow(
                player_id=row.player_id,
                source="override",
                week=None,
                season=season,
                stats=stats,
                adp=row.adp,
                gp=extract_gp(row.stats),
                market_only=not stats,
            )
        )
    return tuple(out)


def load_stat_rows(
    season: str,
    adp_variant: AdpVariant,
    *,
    sleeper_players: Mapping[str, Any],
    override_path: Path | str | None = None,
    client: httpx.Client | None = None,
    scoring_keys: Collection[str] | None = None,
    scoring: Mapping[str, float] | None = None,
) -> tuple[tuple[StatRow, ...], tuple[Banner, ...]]:
    banners: list[Banner] = []
    try:
        raw = fetch_projections(season, client=client)
        rows = parse_projections(raw, adp_variant)
        identities = identities_from_projections(raw, adp_variant)
        allow_name = True
    except (PlatformError, DataRefusal) as exc:
        if override_path is None:
            if isinstance(exc, DataRefusal):
                raise
            raise DataRefusal(
                "Projections host is down and no override was supplied."
            ) from exc
        override_rows = load_override(
            override_path, scoring_keys=scoring_keys, scoring=scoring
        )
        rows = override_to_stat_rows(override_rows, season)
        identities = identities_from_override(override_rows)
        allow_name = False
        banners.append(
            Banner(
                code="projections_override",
                message=(
                    "Projections host was not used; stats and ADP come "
                    "from the override CSV."
                ),
            )
        )
    report = map_rows(identities, sleeper_players, allow_name_match=allow_name)
    check_mapping(report)
    return rows, tuple(banners)


def load_forecast(
    season: str,
    adp_variant: AdpVariant,
    *,
    ecr_scoring: str,
    superflex: bool,
    sleeper_players: Mapping[str, Any],
    override_path: Path | str | None = None,
    fp_api_key: str | None = None,
    client: httpx.Client | None = None,
    scoring_keys: Collection[str] | None = None,
    scoring: Mapping[str, float] | None = None,
    min_interval_s: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[tuple[StatRow, ...], tuple[EcrRow, ...], tuple[Banner, ...]]:
    owned = False
    http = client
    if http is None:
        http = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=120.0)
        owned = True
    try:
        stats, stat_banners = load_stat_rows(
            season,
            adp_variant,
            sleeper_players=sleeper_players,
            override_path=override_path,
            client=http,
            scoring_keys=scoring_keys,
            scoring=scoring,
        )
        ecr, ecr_banners = fetch_ecr(
            season,
            scoring=ecr_scoring,
            superflex=superflex,
            sleeper_players=sleeper_players,
            fp_api_key=fp_api_key,
            client=http,
            min_interval_s=min_interval_s,
            sleep=sleep,
        )
        return stats, ecr, stat_banners + ecr_banners
    finally:
        if owned:
            http.close()
