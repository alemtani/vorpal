"""Extra inputs some gates need, which the payload cannot carry.

The payload is what the model saw at one pick. These are things only the
eval harness knows: what a human marked right or wrong, what five reruns
returned, what a completed draft actually did next.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GateFixtures:
    """A field left as None makes its gate NOT_PERFORMED.

    None and empty are different on purpose. An empty `forbid` means a
    human looked and forbade nobody, so the gate runs and passes. None
    means nobody looked.
    """

    # Human-written for one fixture: players who must not / must be named.
    forbid: frozenset[str] | None = None
    require: frozenset[str] | None = None

    # The picks from five reruns of one byte-identical payload.
    stability_ids: tuple[str, ...] | None = None

    # position -> ranks a third VOLS pass would move its replacement.
    replacement_rank_delta: dict[str, int] | None = None

    # Read off a completed draft: who was still on the board at our next turn.
    available_at_next: frozenset[str] | None = None

    # Draft-day projections, and the two rosters to compare with them.
    dated_points: dict[str, float] | None = None
    user_lineup: tuple[str, ...] | None = None
    policy_lineup: tuple[str, ...] | None = None
