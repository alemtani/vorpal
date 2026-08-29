"""Which starter slots would sit empty in a given week.

Only the bye-hole gate uses this, and only to compare one lineup against
another. It never scores points, so it does not care who is better — only
whether a body can legally stand in each starting slot.

Bench is not a starting slot. A player on bye that week is not there.
"""

from __future__ import annotations

from vorpal.contracts import Slot

# Fill order. Lower fills first, because a slot that accepts fewer
# positions has fewer ways to be covered later. A dedicated QB slot takes
# only a QB; SUPER_FLEX takes almost anyone. Fill SUPER_FLEX first with
# your only QB and you report an empty QB slot that was never really empty.
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
    """Return the starter slots nobody can fill in `week`.

    Each player is `(legal_slots, bye)`. Greedy first fit: walk the
    starting slots most-restrictive first, and give each one the first
    player who is still free and legal there. A slot that finds nobody is
    a hole. Each player fills at most one slot.

    Greedy is exact here because the fill order handles the only case a
    naive pass gets wrong — spending a scarce player on a slot a common
    one could have covered. Roster sizes are ~15, so there is no reason
    to reach for real bipartite matching.
    """
    # Everyone on the roster who actually plays this week.
    available = [legal for legal, bye in players if bye != week]
    filled_by: set[int] = set()

    starters = sorted(
        (slot for slot in slots if slot is not Slot.BN),
        # slot.value only breaks ties, so the result never depends on the
        # order the league happened to list its slots in.
        key=lambda slot: (_RESTRICT.get(slot, 99), slot.value),
    )

    empty: list[Slot] = []
    for slot in starters:
        # First player not yet used who can legally start in this slot.
        filler = next(
            (
                index
                for index, legal in enumerate(available)
                if index not in filled_by and slot in legal
            ),
            None,
        )
        if filler is None:
            empty.append(slot)
        else:
            filled_by.add(filler)
    return tuple(empty)
