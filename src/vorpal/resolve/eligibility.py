"""SPEC.md section 2 eligibility table."""

from __future__ import annotations

from vorpal.contracts import Slot

# None means any position (BN).
ELIGIBLE: dict[Slot, frozenset[str] | None] = {
    Slot.QB: frozenset({"QB"}),
    Slot.RB: frozenset({"RB"}),
    Slot.WR: frozenset({"WR"}),
    Slot.TE: frozenset({"TE"}),
    Slot.K: frozenset({"K"}),
    Slot.DEF: frozenset({"DEF"}),
    Slot.FLEX: frozenset({"RB", "WR", "TE"}),
    Slot.SUPER_FLEX: frozenset({"QB", "RB", "WR", "TE"}),
    Slot.OP: frozenset({"QB", "RB", "WR", "TE"}),
    Slot.BN: None,
    Slot.WRRB_FLEX: frozenset({"WR", "RB"}),
    Slot.REC_FLEX: frozenset({"WR", "TE"}),
    Slot.DL: frozenset({"DL"}),
    Slot.LB: frozenset({"LB"}),
    Slot.DB: frozenset({"DB"}),
    Slot.IDP_FLEX: frozenset({"DL", "LB", "DB"}),
}


def eligible_positions(slot: Slot) -> frozenset[str] | None:
    """Positions that can fill `slot`. None means any (BN)."""
    return ELIGIBLE[slot]


def legal_slots(position: str, roster: tuple[Slot, ...]) -> tuple[Slot, ...]:
    """Distinct roster slot types `position` can fill, in roster order."""
    out: list[Slot] = []
    seen: set[Slot] = set()
    for slot in roster:
        if slot in seen:
            continue
        allowed = ELIGIBLE[slot]
        if allowed is None or position in allowed:
            out.append(slot)
            seen.add(slot)
    return tuple(out)
