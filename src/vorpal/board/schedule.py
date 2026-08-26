"""Poll cadence, backoff, and stale-board thresholds.

Unknown draft statuses use the idle interval, not a fourth rate. Grey-out
skips when pick_timer is 0 or null. Backoff caps at 45s and holds.
"""

from __future__ import annotations

DRAFTING_POLL_S = 3
IDLE_POLL_S = 15
DEGRADE_AFTER_S = 15
BACKOFF_SCHEDULE_S = (5, 15, 45)


def poll_interval(status: str) -> int:
    """Seconds between draft/picks polls. Only ``drafting`` uses 3s."""

    return DRAFTING_POLL_S if status == "drafting" else IDLE_POLL_S


def next_backoff(consecutive_failures: int) -> int:
    """Seconds to wait after N consecutive errors. Caps at 45s (hold)."""

    index = min(max(consecutive_failures, 1) - 1, len(BACKOFF_SCHEDULE_S) - 1)
    return BACKOFF_SCHEDULE_S[index]


def is_degraded(age_seconds: float) -> bool:
    """True once age is 15s or older."""

    return age_seconds >= DEGRADE_AFTER_S


def is_greyed_out(age_seconds: float, pick_timer: int | None) -> bool:
    """Grey-out when age reaches pick_timer. Skip when the timer is 0 or null."""

    if pick_timer is None or pick_timer == 0:
        return False
    return age_seconds >= pick_timer
