"""Board assembly, draft state, and payload serialisation. SPEC.md section 4."""

from vorpal.payload.assemble import (
    BOARD_CAPPED,
    DEFERRED_POSITIONS,
    build_payload,
    cap_board,
    position_depth,
    remaining_need,
)
from vorpal.payload.rows import build_rows
from vorpal.payload.state import (
    RECENT_PICKS,
    build_state,
    needs_from,
    next_pick_for_slot,
    pick_no_for,
    slot_on_the_clock,
)

__all__ = [
    "BOARD_CAPPED",
    "DEFERRED_POSITIONS",
    "RECENT_PICKS",
    "build_payload",
    "build_rows",
    "build_state",
    "cap_board",
    "needs_from",
    "next_pick_for_slot",
    "pick_no_for",
    "position_depth",
    "remaining_need",
    "slot_on_the_clock",
]
