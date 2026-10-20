"""Blend the opportunity model with the vendor mean, then apply status."""

from __future__ import annotations

from collections.abc import Mapping

# 2025 backtest (season.fit): Sleeper alone 5.261 error per player-week,
# model weight 0.25 5.262, 0.5 5.290, 1.0 5.454.
MODEL_WEIGHT = 0.25
FULL_ROLE_GAMES = 3

STATUS_FACTOR: dict[str, float] = {
    "Questionable": 0.85,
    "Doubtful": 0.25,
    "Out": 0.0,
    "IR": 0.0,
    "Sus": 0.0,
    "PUP": 0.0,
}


def blend(
    model: float | None,
    vendors: Mapping[str, float],
    role_games: int,
    weight: float = MODEL_WEIGHT,
) -> float | None:
    """Model weight scales down when few games match this week's role."""
    if not vendors:
        return model
    mean = sum(vendors.values()) / len(vendors)
    if model is None:
        return mean
    w = weight * min(1.0, role_games / FULL_ROLE_GAMES)
    return w * model + (1 - w) * mean


def status_factor(status: str | None) -> float:
    return STATUS_FACTOR.get(status or "", 1.0)
