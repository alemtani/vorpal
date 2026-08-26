"""Counting-stat filters. Fantasy-point columns never survive."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vorpal.contracts import AdpVariant
from vorpal.platform.sleeper import ADP_WIRE_KEYS


def is_fantasy_point_key(key: str) -> bool:
    """True for pts_ppr / pts_std / pts_half_ppr and other pts_* totals.

    DST buckets are pts_allow_* and stay as counting keys.
    """
    if key.startswith("pts_allow"):
        return False
    return key.startswith("pts_")


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    if number is None:
        return None
    return int(number)


def counting_stats(stats: Mapping[str, Any]) -> dict[str, float]:
    """Drop ADP, gp, and fantasy-point totals. Keep counting keys."""
    out: dict[str, float] = {}
    for key, value in stats.items():
        name = str(key)
        if (
            not name
            or name == "gp"
            or name.startswith("adp")
            or is_fantasy_point_key(name)
        ):
            continue
        number = as_float(value)
        if number is None:
            continue
        out[name] = number
    return out


def extract_gp(stats: Mapping[str, Any]) -> float | None:
    return as_float(stats.get("gp"))


def extract_adp(stats: Mapping[str, Any], variant: AdpVariant) -> float | None:
    return as_float(stats.get(ADP_WIRE_KEYS[variant]))
