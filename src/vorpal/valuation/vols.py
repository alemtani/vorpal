"""Two-pass VOLS. Bench is not absorbed. Market-only rows are excluded."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vorpal.contracts import Replacement, Slot
from vorpal.valuation.slots import greedy_fill, starter_counts

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
    """Rank by points, fill, re-rank by that VOLS, fill once more. Stop.

    Two passes because the definition is circular: VOLS is points minus the
    replacement's points, but replacement depends on who starts, and who
    starts should be decided by value, not by raw points.

    Pass 1 breaks the circle. Projected points is the only ranking available
    before any replacement level exists, so fill on that and read off a first
    replacement per position. That gives a first VOLS.

    Pass 2 spends it. Re-rank by that VOLS and fill again. This is where flex
    seats change hands: by points a QB or RB tops the list, but by VOLS a WR
    who beats his replacement by 60 outranks an RB who beats his by 20. Those
    seats move, so the replacement line moves with them.

    Two by fiat, not by convergence. This is a fixed-point iteration that
    could oscillate. `hypothetical_replacement_ranks` runs one more fill and
    the invariant test asserts no position's line moves more than
    MAX_REPLACEMENT_RANK_SHIFT. A failure there means the model is unstable,
    not that this code is wrong.
    """
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
    """Play out how the whole league fills its starters, then read the leftovers.

    Rank the pool best-first by `metric`, seat every roster's starting slots
    league-wide (`counts[slot] * teams`), and look at who is left. The best
    leftover at a position is the replacement: the player nobody starts, the
    waiver-wire baseline that VOLS measures against.

    `metric` is the only thing that changes between passes, so the same fill
    serves pass 1 (points), pass 2 (pass-1 VOLS), and the eval fill.

    `ranks[position]` is that replacement's positional index, 1-based: how
    many players at his position are ahead of him, plus one. In a 12-team
    league starting 2 RB and 1 FLEX, 24 RBs come off the board from RB slots
    and however many more win FLEX seats, so the RB line falls somewhere past
    24. A position whose players were all absorbed has no leftover; record
    where its line fell anyway.
    """
    remaining = sorted(
        pool,
        key=lambda player: (-metric.get(player.player_id, 0.0), player.player_id),
    )
    counts = starter_counts(slots)
    seated, remaining = greedy_fill(remaining, counts, teams=teams)
    absorbed_by_pos: dict[str, int] = {}
    for players in seated.values():
        for player in players:
            absorbed_by_pos[player.position] = (
                absorbed_by_pos.get(player.position, 0) + 1
            )
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
