"""Season-rate weekly vector and one-roster starter fill."""

from __future__ import annotations

from collections.abc import Sequence

from vorpal.contracts import Slot, WeeklyCell
from vorpal.valuation.slots import greedy_fill, starter_counts
from vorpal.valuation.vols import ScoredPlayer

SEASON_WEEKS = 18
DEFAULT_GAMES = 17


def week_vector(
    points: float,
    *,
    gp: float | None = None,
    bye: int | None = None,
    out_weeks: frozenset[int] = frozenset(),
) -> tuple[float, ...]:
    """Rate is points/17, or points/gp. Bye and known-out weeks are 0.

    Does not invent missed weeks from gp. A served suspension is weeks 1..n
    in out_weeks. gp itself is a board field, not a week mask.
    """
    denom = DEFAULT_GAMES if gp is None else gp
    rate = 0.0 if denom <= 0 else points / denom
    weeks: list[float] = []
    for week in range(1, SEASON_WEEKS + 1):
        if bye is not None and week == bye:
            weeks.append(0.0)
        elif week in out_weeks:
            weeks.append(0.0)
        else:
            weeks.append(rate)
    return tuple(weeks)


def fill_starters(
    roster: Sequence[ScoredPlayer],
    slots: Sequence[Slot],
) -> tuple[WeeklyCell, ...]:
    """Fill this roster's starting slots each week. Empty if no positive rate."""
    vectors = {
        player.player_id: week_vector(
            player.points,
            gp=player.gp,
            bye=player.bye,
            out_weeks=player.out_weeks,
        )
        for player in roster
    }
    counts = starter_counts(slots)
    cells: list[WeeklyCell] = []
    for week in range(1, SEASON_WEEKS + 1):
        rates = {player: vectors[player.player_id][week - 1] for player in roster}
        # Same fill as VOLS, one roster instead of the league: rank by this
        # week's rate, seat the slots, and report the ones that came up short.
        ranked = sorted(
            (player for player in roster if rates[player] > 0),
            key=lambda player: (-rates[player], player.player_id),
        )
        seated, _ = greedy_fill(ranked, counts)
        starter_points = sum(
            rates[player] for players in seated.values() for player in players
        )
        empty = tuple(
            slot for slot, players in seated.items() if len(players) < counts[slot]
        )
        cells.append(WeeklyCell(week=week, starter_points=starter_points, empty=empty))
    return tuple(cells)


def delta_starter_points(
    roster: Sequence[ScoredPlayer],
    candidate: ScoredPlayer,
    slots: Sequence[Slot],
) -> float:
    """Season sum of starter_points with the candidate minus without.

    vols is global. This number is vs this roster.
    """
    base = fill_starters(roster, slots)
    added = fill_starters((*roster, candidate), slots)
    return sum(
        with_cell.starter_points - without_cell.starter_points
        for with_cell, without_cell in zip(added, base, strict=True)
    )
