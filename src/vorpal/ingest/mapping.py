"""Fail-closed player mapping across sources."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vorpal.errors import DataRefusal

_SUFFIXES = re.compile(r"\b(?:jr|sr|ii|iii|iv|v)\b", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DST_POS = {"DST", "D/ST", "DEF"}


@dataclass(frozen=True, slots=True)
class MappingRow:
    player_id: str
    name: str
    position: str
    team: str | None
    adp: float | None


@dataclass(frozen=True, slots=True)
class MappingHit:
    source_player_id: str
    host_player_id: str
    method: str
    team_mismatch: bool
    adp: float | None
    name: str


@dataclass(frozen=True, slots=True)
class MappingMiss:
    source_player_id: str
    name: str
    position: str
    team: str | None
    adp: float | None


@dataclass(frozen=True, slots=True)
class MappingReport:
    hits: tuple[MappingHit, ...]
    misses: tuple[MappingMiss, ...]
    window_misses: tuple[MappingMiss, ...]
    top_n: int
    considered: int
    matched: int
    match_rate: float
    team_mismatches: int

    def format(self) -> str:
        rate = f"{self.match_rate:.1%}"
        lines = [
            (
                f"Mapping match rate {rate} ({self.matched}/{self.considered}) "
                f"is below 98% on the top {self.top_n} by ADP."
            ),
            "Unmatched:",
        ]
        for miss in self.window_misses:
            adp = "none" if miss.adp is None else f"{miss.adp}"
            team = miss.team or "-"
            lines.append(
                f"  {miss.source_player_id} {miss.name} {miss.position} "
                f"{team} adp={adp}"
            )
        return "\n".join(lines)


def normalize_name(name: str) -> str:
    lowered = name.lower()
    stripped = _NON_ALNUM.sub(" ", lowered)
    no_suffix = _SUFFIXES.sub("", stripped)
    return " ".join(no_suffix.split())


def normalize_pos(pos: str) -> str:
    value = pos.strip().upper()
    if value in _DST_POS:
        return "DEF"
    return value


def normalize_team(team: str | None) -> str | None:
    if team is None:
        return None
    text = str(team).strip().upper()
    return text or None


def player_display_name(row: Mapping[str, Any]) -> str:
    full = row.get("full_name")
    if full:
        return str(full)
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def map_rows(
    sources: Sequence[MappingRow],
    players: Mapping[str, Any],
    *,
    allow_name_match: bool = True,
    top_n: int = 300,
) -> MappingReport:
    by_id, by_name_pos_team, by_name_pos = _indexes(players)
    hits: list[MappingHit] = []
    misses: list[MappingMiss] = []
    hit_by_source: dict[str, MappingHit] = {}
    for source in sources:
        hit = _match(source, by_id, by_name_pos_team, by_name_pos, allow_name_match)
        if hit is None:
            misses.append(
                MappingMiss(
                    source_player_id=source.player_id,
                    name=source.name,
                    position=source.position,
                    team=source.team,
                    adp=source.adp,
                )
            )
            continue
        hits.append(hit)
        hit_by_source[source.player_id] = hit
    ranked = [row for row in sources if row.adp is not None]
    ranked.sort(key=lambda row: row.adp if row.adp is not None else 0.0)
    window = ranked[:top_n]
    matched = sum(1 for row in window if row.player_id in hit_by_source)
    considered = len(window)
    window_ids = {row.player_id for row in window}
    window_misses = tuple(
        miss for miss in misses if miss.source_player_id in window_ids
    )
    rate = (matched / considered) if considered else 0.0
    return MappingReport(
        hits=tuple(hits),
        misses=tuple(misses),
        window_misses=window_misses,
        top_n=top_n,
        considered=considered,
        matched=matched,
        match_rate=rate,
        team_mismatches=sum(1 for hit in hits if hit.team_mismatch),
    )


def check_mapping(report: MappingReport, *, min_rate: float = 0.98) -> None:
    if report.considered == 0:
        raise DataRefusal("No players with ADP to map.")
    if report.matched < min_rate * report.considered:
        raise DataRefusal(report.format())


def _indexes(
    players: Mapping[str, Any],
) -> tuple[
    set[str],
    dict[tuple[str, str, str | None], list[str]],
    dict[tuple[str, str], list[str]],
]:
    by_id: set[str] = set()
    by_name_pos_team: dict[tuple[str, str, str | None], list[str]] = {}
    by_name_pos: dict[tuple[str, str], list[str]] = {}
    for pid, row in players.items():
        if not isinstance(row, dict):
            continue
        host_id = str(pid)
        by_id.add(host_id)
        name = normalize_name(player_display_name(row))
        pos = normalize_pos(str(row.get("position") or ""))
        team = normalize_team(
            None if row.get("team") in (None, "") else str(row.get("team"))
        )
        by_name_pos_team.setdefault((name, pos, team), []).append(host_id)
        by_name_pos.setdefault((name, pos), []).append(host_id)
    return by_id, by_name_pos_team, by_name_pos


def _match(
    source: MappingRow,
    by_id: set[str],
    by_name_pos_team: dict[tuple[str, str, str | None], list[str]],
    by_name_pos: dict[tuple[str, str], list[str]],
    allow_name_match: bool,
) -> MappingHit | None:
    if source.player_id and source.player_id in by_id:
        return MappingHit(
            source_player_id=source.player_id,
            host_player_id=source.player_id,
            method="player_id",
            team_mismatch=False,
            adp=source.adp,
            name=source.name,
        )
    if not allow_name_match:
        return None
    name = normalize_name(source.name)
    pos = normalize_pos(source.position)
    team = normalize_team(source.team)
    team_hits = by_name_pos_team.get((name, pos, team), [])
    if len(team_hits) == 1:
        return MappingHit(
            source_player_id=source.player_id,
            host_player_id=team_hits[0],
            method="name_pos_team",
            team_mismatch=False,
            adp=source.adp,
            name=source.name,
        )
    pos_hits = by_name_pos.get((name, pos), [])
    if len(pos_hits) == 1:
        return MappingHit(
            source_player_id=source.player_id,
            host_player_id=pos_hits[0],
            method="name_pos",
            team_mismatch=True,
            adp=source.adp,
            name=source.name,
        )
    return None
