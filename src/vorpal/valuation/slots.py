"""Starter-slot eligibility, fill order, and the one greedy fill.

Bench is not startable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from vorpal.contracts import Slot


class Positioned(Protocol):
    """Anything the fill can seat. Only the position decides eligibility."""

    @property
    def position(self) -> str: ...


ELIGIBLE: dict[Slot, frozenset[str]] = {
    Slot.QB: frozenset({"QB"}),
    Slot.RB: frozenset({"RB"}),
    Slot.WR: frozenset({"WR"}),
    Slot.TE: frozenset({"TE"}),
    Slot.K: frozenset({"K"}),
    Slot.DEF: frozenset({"DEF", "DST"}),
    Slot.FLEX: frozenset({"RB", "WR", "TE"}),
    Slot.WRRB_FLEX: frozenset({"WR", "RB"}),
    Slot.REC_FLEX: frozenset({"WR", "TE"}),
    Slot.SUPER_FLEX: frozenset({"QB", "RB", "WR", "TE"}),
    Slot.OP: frozenset({"QB", "RB", "WR", "TE"}),
    Slot.DL: frozenset({"DL"}),
    Slot.LB: frozenset({"LB"}),
    Slot.DB: frozenset({"DB"}),
    Slot.IDP_FLEX: frozenset({"DL", "LB", "DB"}),
}

_DEDICATED: tuple[Slot, ...] = (
    Slot.QB,
    Slot.RB,
    Slot.WR,
    Slot.TE,
    Slot.K,
    Slot.DEF,
    Slot.DL,
    Slot.LB,
    Slot.DB,
)

_FLEX_TIE: dict[Slot, int] = {
    Slot.WRRB_FLEX: 0,
    Slot.REC_FLEX: 1,
    Slot.FLEX: 2,
    Slot.IDP_FLEX: 3,
    Slot.SUPER_FLEX: 4,
    Slot.OP: 5,
}


def starter_counts(slots: Sequence[Slot]) -> dict[Slot, int]:
    """Per-roster starter counts. BN is omitted."""
    counts: dict[Slot, int] = {}
    for slot in slots:
        if slot is Slot.BN or slot not in ELIGIBLE:
            continue
        counts[slot] = counts.get(slot, 0) + 1
    return counts


def fill_order(counts: dict[Slot, int]) -> tuple[Slot, ...]:
    """Dedicated first, then flex most-restrictive first (FLEX before SUPER_FLEX)."""
    dedicated = tuple(slot for slot in _DEDICATED if counts.get(slot, 0) > 0)
    flex = [slot for slot in counts if slot not in _DEDICATED]
    flex.sort(key=lambda slot: (len(ELIGIBLE[slot]), _FLEX_TIE.get(slot, 99)))
    return dedicated + tuple(flex)


def greedy_fill[P: Positioned](
    ordered: Sequence[P],
    counts: Mapping[Slot, int],
    *,
    teams: int = 1,
) -> tuple[dict[Slot, list[P]], list[P]]:
    """Seat pre-ranked players into starting slots. One rule, two callers.

    `ordered` is best-first by whatever metric the caller ranks on: projected
    points or VOLS league-wide, this week's rate for one roster. The fill only
    reads the order, never the metric, so both callers get the same rule.

    Walks `fill_order`: dedicated slots first, then flex most-restrictive
    first. Each slot takes the best `counts[slot] * teams` players still
    unseated and eligible for it. Dedicated-before-flex is what makes a FLEX
    seat go to the best player *left* rather than the best player overall.

    Returns the players seated in each slot, plus everyone left over, still
    in rank order. A short list in `taken` means that slot went unfilled.
    """
    remaining = list(ordered)
    taken: dict[Slot, list[P]] = {}
    for slot in fill_order(dict(counts)):
        need = counts[slot] * teams
        eligible = ELIGIBLE[slot]
        seated: list[P] = []
        still: list[P] = []
        for player in remaining:
            if len(seated) < need and player.position in eligible:
                seated.append(player)
            else:
                still.append(player)
        taken[slot] = seated
        remaining = still
    return taken, remaining
