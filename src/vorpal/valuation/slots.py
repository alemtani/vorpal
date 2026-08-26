"""Starter-slot eligibility and fill order. Bench is not startable."""

from __future__ import annotations

from collections.abc import Sequence

from vorpal.contracts import Slot

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
