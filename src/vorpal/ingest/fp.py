"""FantasyPros wire field access. Shared by projections, ADP, and ECR."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vorpal.ingest.keys import as_float, as_int
from vorpal.ingest.mapping import as_id, host_id_from_fp


def fp_player_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    players = payload.get("players")
    if players is None:
        players = payload.get("player")
    if not isinstance(players, list):
        return []
    return [item for item in players if isinstance(item, dict)]


def fp_player_id(item: Mapping[str, Any]) -> str | None:
    return as_id(item.get("fpid") or item.get("player_id"))


def fp_yahoo_id(item: Mapping[str, Any]) -> str | None:
    return as_id(
        item.get("player_yahoo_id") or item.get("yahooid") or item.get("yahoo_id")
    )


def fp_name(item: Mapping[str, Any]) -> str:
    return str(item.get("player_name") or item.get("name") or "")


def fp_team(item: Mapping[str, Any]) -> str | None:
    raw = (
        item.get("player_team_id")
        if item.get("player_team_id") not in (None, "")
        else item.get("team_id")
    )
    if raw in (None, ""):
        raw = item.get("team")
    if raw in (None, ""):
        return None
    return str(raw)


def fp_position(item: Mapping[str, Any]) -> str:
    return str(
        item.get("player_position_id")
        or item.get("position_id")
        or item.get("position")
        or ""
    )


def fp_bye(item: Mapping[str, Any]) -> int | None:
    return as_int(item.get("player_bye_week") or item.get("bye"))


def fp_stats_map(item: Mapping[str, Any]) -> Mapping[str, Any]:
    stats = item.get("stats")
    if isinstance(stats, dict):
        return stats
    return item


def fp_adp_value(item: Mapping[str, Any]) -> float | None:
    for key in ("adp", "rank_ave", "rank_ecr"):
        number = as_float(item.get(key))
        if number is not None:
            return number
    stats = item.get("stats")
    if isinstance(stats, dict):
        for key in ("adp", "rank_ave", "rank_ecr"):
            number = as_float(stats.get(key))
            if number is not None:
                return number
    return None


def fp_host_id(item: Mapping[str, Any]) -> str | None:
    return host_id_from_fp(item)


def parse_adp_map(payloads: Sequence[Any]) -> dict[str, float]:
    """fp_id and yahoo_id -> ADP. First value wins per key."""
    out: dict[str, float] = {}
    for payload in payloads:
        for item in fp_player_list(payload):
            adp = fp_adp_value(item)
            if adp is None:
                continue
            pid = fp_player_id(item)
            yahoo = fp_yahoo_id(item)
            if pid and pid not in out:
                out[pid] = adp
            if yahoo and yahoo not in out:
                out[yahoo] = adp
    return out
