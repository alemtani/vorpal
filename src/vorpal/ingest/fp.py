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


def fp_row_ids(payload: Any) -> set[str]:
    """Player ids present in a rankings or projections payload."""
    ids: set[str] = set()
    for item in fp_player_list(payload):
        pid = fp_player_id(item)
        if pid:
            ids.add(pid)
    return ids


def fp_truncated(payload: Any) -> bool:
    """True when the envelope's ``count`` is larger than the returned list.

    Missing ``count`` is not a cap: empty test doubles must not trigger
    paging probes.
    """
    if not isinstance(payload, dict):
        return False
    catalog = as_int(payload.get("count"))
    if catalog is None:
        return False
    return len(fp_player_list(payload)) < catalog


def paging_added_rows(base: Any, extra: Any) -> bool:
    """True when extra has at least one player id that base does not."""
    return bool(fp_row_ids(extra) - fp_row_ids(base))


def merge_fp_player_payloads(payloads: Sequence[Any]) -> Any:
    """First envelope wins. Players concatenate; first id keeps its row."""
    players: list[dict[str, Any]] = []
    seen: set[str] = set()
    envelope: dict[str, Any] | None = None
    for payload in payloads:
        if envelope is None and isinstance(payload, dict):
            envelope = dict(payload)
        for item in fp_player_list(payload):
            pid = fp_player_id(item)
            if pid:
                if pid in seen:
                    continue
                seen.add(pid)
            players.append(item)
    if envelope is not None:
        out = dict(envelope)
        out["players"] = players
        return out
    return players
