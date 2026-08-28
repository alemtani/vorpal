"""Hypothetical extra VOLS pass. A failure here is a model problem."""

from __future__ import annotations

import pytest

from vorpal.contracts import Slot
from vorpal.valuation import (
    MAX_REPLACEMENT_RANK_SHIFT,
    ScoredPlayer,
    compute_vols,
    hypothetical_replacement_ranks,
    replacement_rank_shifts,
    score_player,
)


def _shifts(players: tuple[ScoredPlayer, ...], slots: tuple[Slot, ...], teams: int):
    result = compute_vols(players, slots, teams)
    extra = hypothetical_replacement_ranks(players, slots, teams, result)
    return replacement_rank_shifts(result.replacement_ranks, extra), result, extra


@pytest.mark.invariant
def test_hypothetical_pass_moves_no_position_more_than_two_on_superflex_table(
    sf_table: tuple[ScoredPlayer, ...],
    sf_slots: tuple[Slot, ...],
) -> None:
    shifts, result, extra = _shifts(sf_table, sf_slots, teams=2)
    assert extra
    assert result.replacement_ranks
    for position, move in shifts.items():
        assert move <= MAX_REPLACEMENT_RANK_SHIFT, (
            f"{position} replacement rank moved {move} "
            f"(limit {MAX_REPLACEMENT_RANK_SHIFT})"
        )


@pytest.mark.invariant
def test_hypothetical_pass_on_superflex_cliff_table(
    sf_cliff_table: tuple[ScoredPlayer, ...],
    sf_slots: tuple[Slot, ...],
) -> None:
    shifts, _, _ = _shifts(sf_cliff_table, sf_slots, teams=2)
    for position, move in shifts.items():
        assert move <= MAX_REPLACEMENT_RANK_SHIFT, (
            f"{position} replacement rank moved {move}"
        )


def _scored_from_projections(
    scoring: dict[str, float],
    rows: list[dict[str, object]],
) -> tuple[ScoredPlayer, ...]:
    players: list[ScoredPlayer] = []
    for row in rows:
        raw_player = row.get("player")
        if not isinstance(raw_player, dict):
            continue
        position = str(raw_player.get("position") or "")
        if position not in {"QB", "RB", "WR", "TE", "K", "DEF"}:
            continue
        stats_raw = row.get("stats")
        if not isinstance(stats_raw, dict):
            continue
        stats = {str(key): float(value) for key, value in stats_raw.items()}
        counting = {
            key: value
            for key, value in stats.items()
            if not key.startswith("adp")
            and not key.startswith("pts_")
            and key not in {"gp", "cmp_pct"}
        }
        if not counting:
            continue
        players.append(
            ScoredPlayer(
                player_id=str(row.get("player_id") or ""),
                position=position,
                points=score_player(position, stats, scoring),
                gp=stats.get("gp"),
            )
        )
    return tuple(players)


@pytest.mark.invariant
def test_hypothetical_pass_on_snake_redraft_fixture(
    snake_scoring: dict[str, float],
    projection_rows: list[dict[str, object]],
    snake_slots: tuple[Slot, ...],
) -> None:
    players = _scored_from_projections(snake_scoring, projection_rows)
    shifts, _, _ = _shifts(players, snake_slots, teams=12)
    for position, move in shifts.items():
        assert move <= MAX_REPLACEMENT_RANK_SHIFT, (
            f"{position} replacement rank moved {move}"
        )


@pytest.mark.invariant
def test_hypothetical_pass_on_superflex_fixture(
    superflex_scoring: dict[str, float],
    projection_rows: list[dict[str, object]],
    superflex_slots: tuple[Slot, ...],
) -> None:
    players = _scored_from_projections(superflex_scoring, projection_rows)
    shifts, _, _ = _shifts(players, superflex_slots, teams=12)
    for position, move in shifts.items():
        assert move <= MAX_REPLACEMENT_RANK_SHIFT, (
            f"{position} replacement rank moved {move}"
        )
