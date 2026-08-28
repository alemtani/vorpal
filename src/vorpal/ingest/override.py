"""Override CSV keyed by player_id. No name matching."""

from __future__ import annotations

import csv
import io
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from vorpal.contracts import OverrideRow
from vorpal.errors import DataRefusal
from vorpal.ingest.keys import as_float, counting_stats, is_fantasy_point_key
from vorpal.ingest.mapping import MappingRow

IDENTITY = frozenset({"player_id", "name", "team", "pos", "adp", "adp_stdev"})


def parse_override(
    text: str,
    *,
    scoring_keys: Collection[str] | None = None,
    scoring: Mapping[str, float] | None = None,
) -> tuple[OverrideRow, ...]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise DataRefusal("Override CSV is empty.")
    reader.fieldnames = [(name or "").strip() for name in reader.fieldnames]
    headers = set(reader.fieldnames)
    if "player_id" not in headers:
        raise DataRefusal("Override CSV is missing required column player_id.")
    if "adp" not in headers:
        raise DataRefusal("Override CSV is missing required column adp.")
    needed: set[str] = set()
    if scoring_keys is not None:
        needed.update(scoring_keys)
    if scoring is not None:
        needed.update(key for key, weight in scoring.items() if weight != 0)
    rows: list[OverrideRow] = []
    seen: set[str] = set()
    for raw in reader:
        row = {
            (key or "").strip(): (value.strip() if isinstance(value, str) else value)
            for key, value in raw.items()
        }
        player_id = str(row.get("player_id") or "")
        if not player_id:
            raise DataRefusal("Override CSV has a blank player_id.")
        if player_id in seen:
            raise DataRefusal(f"Override CSV has duplicate player_id {player_id}.")
        seen.add(player_id)
        adp = as_float(row.get("adp"))
        if adp is None:
            raise DataRefusal(f"Override CSV is missing adp for player_id {player_id}.")
        stats = _override_stats(row)
        missing = sorted(key for key in needed if key not in stats)
        if missing:
            raise DataRefusal(
                "Override CSV is missing counting stats: " + ", ".join(missing) + "."
            )
        rows.append(
            OverrideRow(
                player_id=player_id,
                stats=counting_stats(stats),
                adp=adp,
                adp_stdev=as_float(row.get("adp_stdev")),
                name=row.get("name") or None,
                team=row.get("team") or None,
                pos=row.get("pos") or None,
            )
        )
    if not rows:
        raise DataRefusal("Override CSV is empty.")
    return tuple(rows)


def load_override(
    path: Path | str,
    *,
    scoring_keys: Collection[str] | None = None,
    scoring: Mapping[str, float] | None = None,
) -> tuple[OverrideRow, ...]:
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DataRefusal(f"Override CSV could not be read: {file}") from exc
    return parse_override(text, scoring_keys=scoring_keys, scoring=scoring)


def identities_from_override(rows: tuple[OverrideRow, ...]) -> list[MappingRow]:
    return [
        MappingRow(
            player_id=row.player_id,
            name=row.name or "",
            position=row.pos or "",
            team=row.team,
            adp=row.adp,
            host_id=row.player_id,
        )
        for row in rows
    ]


def _override_stats(row: Mapping[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in row.items():
        name = str(key)
        if name in IDENTITY or is_fantasy_point_key(name):
            continue
        number = as_float(value)
        if number is None:
            continue
        out[name] = number
    return out
