"""Startable-slot fill for the bye-hole gate.

Keeps a greedy most-restrictive-first assignment. Bench is never a
startable slot. Used only to compare empty slots, not to score points.
"""

from __future__ import annotations

from vorpal.contracts import Slot

# Lower is more restrictive. Dedicated slots fill before flex.
_RESTRICT: dict[Slot, int] = {
    Slot.QB: 0,
    Slot.RB: 0,
    Slot.WR: 0,
    Slot.TE: 0,
    Slot.K: 0,
    Slot.DEF: 0,
    Slot.DL: 0,
    Slot.LB: 0,
    Slot.DB: 0,
    Slot.WRRB_FLEX: 1,
    Slot.REC_FLEX: 1,
    Slot.IDP_FLEX: 1,
    Slot.FLEX: 2,
    Slot.SUPER_FLEX: 3,
    Slot.OP: 3,
    Slot.BN: 9,
}

_BY_POSITION: dict[str, tuple[Slot, ...]] = {
    "QB": (Slot.QB, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
    "RB": (Slot.RB, Slot.FLEX, Slot.WRRB_FLEX, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
    "WR": (
        Slot.WR,
        Slot.FLEX,
        Slot.WRRB_FLEX,
        Slot.REC_FLEX,
        Slot.SUPER_FLEX,
        Slot.OP,
        Slot.BN,
    ),
    "TE": (Slot.TE, Slot.FLEX, Slot.REC_FLEX, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
    "K": (Slot.K, Slot.BN),
    "DEF": (Slot.DEF, Slot.BN),
}


def legal_slots_for_position(position: str) -> tuple[Slot, ...]:
    """Canonical eligibility. Unknown positions are bench-only."""
    return _BY_POSITION.get(position, (Slot.BN,))


def empty_startable_slots(
    slots: tuple[Slot, ...],
    players: tuple[tuple[tuple[Slot, ...], int | None], ...],
    week: int,
) -> tuple[Slot, ...]:
    """Return unfilled starter slots in `week`.

    Each player is `(legal_slots, bye)`. A player whose bye is `week` is
    unavailable. BN is dropped. Assignment is most-restrictive first so a
    QB is not spent on SUPER_FLEX while the QB slot sits empty.
    """
    available = [legal for legal, bye in players if bye != week]
    used: set[int] = set()
    ordered = sorted(
        (slot for slot in slots if slot is not Slot.BN),
        key=lambda slot: (_RESTRICT.get(slot, 99), slot.value),
    )
    empty: list[Slot] = []
    for slot in ordered:
        match = next(
            (
                index
                for index, legal in enumerate(available)
                if index not in used and slot in legal
            ),
            None,
        )
        if match is None:
            empty.append(slot)
        else:
            used.add(match)
    return tuple(empty)
