"""Board assembly and payload serialisation. SPEC.md section 4."""

from vorpal.payload.assemble import (
    BOARD_CAPPED,
    DEFERRED_POSITIONS,
    build_payload,
    cap_board,
    position_depth,
    remaining_need,
)

__all__ = [
    "BOARD_CAPPED",
    "DEFERRED_POSITIONS",
    "build_payload",
    "cap_board",
    "position_depth",
    "remaining_need",
]
