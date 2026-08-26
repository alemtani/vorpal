"""Optional inputs for gates that are not (payload, proposal) alone."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GateFixtures:
    """Extra inputs. A missing field is NOT_PERFORMED for that gate.

    Empty collections are present: an empty forbid set means nothing is
    forbidden, and the gate still runs.
    """

    forbid: frozenset[str] | None = None
    require: frozenset[str] | None = None
    stability_ids: tuple[str, ...] | None = None
    replacement_rank_delta: dict[str, int] | None = None
    available_at_next: frozenset[str] | None = None
    dated_points: dict[str, float] | None = None
    user_lineup: tuple[str, ...] | None = None
    policy_lineup: tuple[str, ...] | None = None
