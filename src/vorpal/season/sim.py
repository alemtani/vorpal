"""Best legal lineup, and rest-of-season value under random injuries."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

SLOT_POSITIONS: dict[str, frozenset[str]] = {
    "QB": frozenset({"QB"}),
    "RB": frozenset({"RB"}),
    "WR": frozenset({"WR"}),
    "TE": frozenset({"TE"}),
    "WRRB_FLEX": frozenset({"RB", "WR"}),
    "REC_FLEX": frozenset({"WR", "TE"}),
    "FLEX": frozenset({"RB", "WR", "TE"}),
    "SUPER_FLEX": frozenset({"QB", "RB", "WR", "TE"}),
}
NOT_STARTERS = frozenset({"BN", "IR", "TAXI"})

PointsFn = Callable[[str, int], float]


def lineup_slots(roster_positions: Iterable[str]) -> list[str]:
    """Starting slots, most specific first. That order makes greedy optimal."""
    slots = [s for s in roster_positions if s not in NOT_STARTERS]
    unknown = [s for s in slots if s not in SLOT_POSITIONS]
    if unknown:
        raise ValueError(f"unknown lineup slot: {', '.join(unknown)}")
    return sorted(slots, key=lambda s: len(SLOT_POSITIONS[s]))


def best_lineup(
    points: Mapping[str, float], positions: Mapping[str, str], slots: Sequence[str]
) -> tuple[float, list[tuple[str, str]]]:
    used: set[str] = set()
    starters: list[tuple[str, str]] = []
    total = 0.0
    for slot in slots:
        ok = SLOT_POSITIONS[slot]
        pool = [p for p in points if p not in used and positions.get(p) in ok]
        if not pool:
            continue
        pick = max(pool, key=lambda p: points[p])
        used.add(pick)
        starters.append((slot, pick))
        total += points[pick]
    return total, starters


@dataclass(frozen=True)
class Value:
    regular: float
    playoffs: float
    total: float


@dataclass
class SeasonSim:
    """Monte Carlo over weeks. Each player's injury draws depend only on his id.

    So two rosters that share a player see the same weeks lost for him, and a
    move's gain is not swamped by sampling noise.
    """

    weeks: Iterable[int]
    playoff_start: int
    n: int = 2000
    p_miss: float = 0.08
    seed: int = 7
    playoff_weight: float = 1.5
    _draws: dict[str, list[list[bool]]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.weeks = list(self.weeks)

    def _healthy(self, pid: str) -> list[list[bool]]:
        if pid not in self._draws:
            rnd = random.Random(f"{self.seed}:{pid}")
            sims = []
            for _ in range(self.n):
                out, row = 0, []
                for _week in self.weeks:
                    if out > 0:
                        out -= 1
                        row.append(False)
                    elif rnd.random() < self.p_miss:
                        out = rnd.choice((0, 0, 1, 2, 3))
                        row.append(False)
                    else:
                        row.append(True)
                sims.append(row)
            self._draws[pid] = sims
        return self._draws[pid]

    def value(
        self,
        roster: Sequence[str],
        points: PointsFn,
        positions: Mapping[str, str],
        slots: Sequence[str],
    ) -> Value:
        weeks = list(self.weeks)
        base = {(p, w): points(p, w) for p in roster for w in weeks}
        draws = {p: self._healthy(p) for p in roster}
        regular = playoffs = 0.0
        for i in range(self.n):
            for j, w in enumerate(weeks):
                pts = {p: base[p, w] if draws[p][i][j] else 0.0 for p in roster}
                total, _ = best_lineup(pts, positions, slots)
                if w >= self.playoff_start:
                    playoffs += total
                else:
                    regular += total
        regular, playoffs = regular / self.n, playoffs / self.n
        return Value(regular, playoffs, regular + self.playoff_weight * playoffs)
