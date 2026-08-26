"""Two-pass VOLS. Bench is not absorbed. Market-only rows are excluded."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vorpal.contracts import Replacement, Slot
from vorpal.valuation.slots import ELIGIBLE, fill_order, starter_counts

MAX_REPLACEMENT_RANK_SHIFT = 2


@dataclass(frozen=True, slots=True)
class ScoredPlayer:
    player_id: str
    position: str
    points: float
    market_only: bool = False
    gp: float | None = None
    bye: int | None = None
    out_weeks: frozenset[int] = frozenset()
    name: str = ""


@dataclass(frozen=True, slots=True)
class PlayerValue:
    player_id: str
    position: str
    points: float
    vols: float


@dataclass(frozen=True, slots=True)
class VolsResult:
    values: tuple[PlayerValue, ...]
    replacement: dict[str, Replacement]
    replacement_ranks: dict[str, int]
    pass1_replacement_ranks: dict[str, int]

    def value_by_id(self) -> dict[str, PlayerValue]:
        return {row.player_id: row for row in self.values}


@dataclass(frozen=True, slots=True)
class _Fill:
    replacement: dict[str, Replacement]
    ranks: dict[str, int]


def compute_vols(
    players: Sequence[ScoredPlayer],
    slots: Sequence[Slot],
    teams: int,
) -> VolsResult:
    """Rank by points, fill, re-rank by that VOLS, fill once more. Stop."""
    pool = tuple(player for player in players if not player.market_only)
    points = {player.player_id: player.points for player in pool}
    pass1 = _fill(pool, slots, teams, points)
    vols1 = _vols_from(pool, pass1.replacement)
    pass2 = _fill(pool, slots, teams, vols1)
    vols2 = _vols_from(pool, pass2.replacement)
    values = tuple(
        sorted(
            (
                PlayerValue(
                    player_id=player.player_id,
                    position=player.position,
                    points=player.points,
                    vols=vols2[player.player_id],
                )
                for player in pool
            ),
            key=lambda row: (-row.vols, row.player_id),
        )
    )
    return VolsResult(
        values=values,
        replacement=pass2.replacement,
        replacement_ranks=pass2.ranks,
        pass1_replacement_ranks=pass1.ranks,
    )


def hypothetical_replacement_ranks(
    players: Sequence[ScoredPlayer],
    slots: Sequence[Slot],
    teams: int,
    result: VolsResult,
) -> dict[str, int]:
    """One more fill ranked by the solver's VOLS. Eval only, not a third pass."""
    pool = tuple(player for player in players if not player.market_only)
    metric = {row.player_id: row.vols for row in result.values}
    return _fill(pool, slots, teams, metric).ranks


def replacement_rank_shifts(
    before: Mapping[str, int],
    after: Mapping[str, int],
) -> dict[str, int]:
    """Absolute positional-index move per position present in both fills."""
    return {
        position: abs(before[position] - after[position])
        for position in before.keys() & after.keys()
    }


def _vols_from(
    pool: Sequence[ScoredPlayer],
    replacement: Mapping[str, Replacement],
) -> dict[str, float]:
    return {
        player.player_id: player.points
        - (
            replacement[player.position].points
            if player.position in replacement
            else 0.0
        )
        for player in pool
    }


def _fill(
    pool: Sequence[ScoredPlayer],
    slots: Sequence[Slot],
    teams: int,
    metric: Mapping[str, float],
) -> _Fill:
    remaining = sorted(
        pool,
        key=lambda player: (-metric.get(player.player_id, 0.0), player.player_id),
    )
    counts = starter_counts(slots)
    absorbed_by_pos: dict[str, int] = {}
    for slot in fill_order(counts):
        need = counts[slot] * teams
        eligible = ELIGIBLE[slot]
        still: list[ScoredPlayer] = []
        taken = 0
        for player in remaining:
            if taken < need and player.position in eligible:
                absorbed_by_pos[player.position] = (
                    absorbed_by_pos.get(player.position, 0) + 1
                )
                taken += 1
            else:
                still.append(player)
        remaining = still
    replacement: dict[str, Replacement] = {}
    ranks: dict[str, int] = {}
    for player in remaining:
        if player.position in replacement:
            continue
        replacement[player.position] = Replacement(player.player_id, player.points)
        ranks[player.position] = absorbed_by_pos.get(player.position, 0) + 1
    for position, count in absorbed_by_pos.items():
        ranks.setdefault(position, count + 1)
    return _Fill(replacement=replacement, ranks=ranks)
