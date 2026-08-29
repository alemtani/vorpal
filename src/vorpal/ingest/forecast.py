"""Load stats (FantasyPros or override) and ECR. ECR never blocks."""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from vorpal.contracts import (
    AdpVariant,
    Banner,
    EcrRow,
    Host,
    OverrideRow,
    Player,
    StatRow,
)
from vorpal.errors import DataRefusal, PlatformError
from vorpal.ingest.client import FantasyProsClient, require_api_key
from vorpal.ingest.ecr import fetch_ecr
from vorpal.ingest.keys import (
    counting_stats,
    extract_gp,
    fp_adp_position,
    fp_adp_scoring,
)
from vorpal.ingest.mapping import check_mapping, map_rows
from vorpal.ingest.override import identities_from_override, load_override
from vorpal.ingest.projections import (
    attach_adp,
    fetch_projections,
    load_adp_map,
    parse_projections,
    to_stat_rows,
)


def override_to_stat_rows(
    rows: tuple[OverrideRow, ...],
    season: str,
    *,
    host: Host = Host.SLEEPER,
) -> tuple[StatRow, ...]:
    out: list[StatRow] = []
    for row in rows:
        stats = counting_stats(row.stats, position=row.pos, host=host)
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


def unmatched_scoring_banner(
    rows: tuple[StatRow, ...], scoring: Mapping[str, float] | None
) -> Banner | None:
    """Banner nonzero scoring keys that no row carries. Do not silent-zero."""
    if not scoring:
        return None
    present: set[str] = set()
    for row in rows:
        present.update(row.stats)
    missing = sorted(
        key for key, weight in scoring.items() if weight != 0 and key not in present
    )
    if not missing:
        return None
    return Banner(
        code="unmapped_scoring_keys",
        message=(
            "Scoring keys with no projected counting stat: " + ", ".join(missing) + "."
        ),
    )


def load_stat_rows(
    season: str,
    adp_variant: AdpVariant,
    *,
    host_players: Mapping[str, Player],
    override_path: Path | str | None = None,
    client: FantasyProsClient | None = None,
    scoring_keys: Collection[str] | None = None,
    scoring: Mapping[str, float] | None = None,
    ecr_scoring: str | None = None,
    host: Host = Host.SLEEPER,
) -> tuple[tuple[StatRow, ...], tuple[Banner, ...]]:
    banners: list[Banner] = []
    try:
        if client is None or not client.api_key:
            require_api_key(None)
        assert client is not None
        scoring_label = fp_adp_scoring(adp_variant, ecr_scoring)
        raw = fetch_projections(season, client=client, scoring=scoring_label)
        records = parse_projections(raw, host=host)
        adp, adp_banners = load_adp_map(
            season,
            client=client,
            scoring=scoring_label,
            variant_position=fp_adp_position(adp_variant),
        )
        banners.extend(adp_banners)
        records = attach_adp(records, adp)
        rows, join_banners = to_stat_rows(records, host_players, season=season)
        banners.extend(join_banners)
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
        rows = override_to_stat_rows(override_rows, season, host=host)
        identities = identities_from_override(override_rows)
        report = map_rows(identities, host_players, allow_name_match=False)
        check_mapping(report)
        banners.append(
            Banner(
                code="projections_override",
                message=(
                    "Projections host was not used; stats and ADP come "
                    "from the override CSV."
                ),
            )
        )
    extra = unmatched_scoring_banner(rows, scoring)
    if extra:
        banners.append(extra)
    return rows, tuple(banners)


def load_forecast(
    season: str,
    adp_variant: AdpVariant,
    *,
    ecr_scoring: str,
    superflex: bool,
    host_players: Mapping[str, Player],
    override_path: Path | str | None = None,
    fp_api_key: str | None = None,
    client: httpx.Client | FantasyProsClient | None = None,
    scoring_keys: Collection[str] | None = None,
    scoring: Mapping[str, float] | None = None,
    min_interval_s: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    host: Host = Host.SLEEPER,
) -> tuple[tuple[StatRow, ...], tuple[EcrRow, ...], tuple[Banner, ...]]:
    owned = False
    if isinstance(client, FantasyProsClient):
        fp = client
    else:
        fp = FantasyProsClient(
            api_key=fp_api_key,
            http=client,
            min_interval_s=min_interval_s,
            sleep=sleep,
        )
        owned = client is None
    try:
        # Stats and ECR do not depend on each other. Fan out, then join.
        with ThreadPoolExecutor(max_workers=2) as pool:
            stats_f = pool.submit(
                load_stat_rows,
                season,
                adp_variant,
                host_players=host_players,
                override_path=override_path,
                client=fp,
                scoring_keys=scoring_keys,
                scoring=scoring,
                ecr_scoring=ecr_scoring,
                host=host,
            )
            ecr_f = pool.submit(
                fetch_ecr,
                season,
                scoring=ecr_scoring,
                superflex=superflex,
                host_players=host_players,
                client=fp,
            )
            stats, stat_banners = stats_f.result()
            ecr, ecr_banners = ecr_f.result()
        return stats, ecr, stat_banners + ecr_banners
    finally:
        if owned:
            fp.close()
