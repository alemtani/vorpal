"""Error backoff schedule. Pure: no clock, no sleep."""

_SCHEDULE = (5.0, 15.0, 45.0)


def backoff_seconds(consecutive_failures: int) -> float:
    """Seconds to wait after N consecutive failures.

    5s, 15s, 45s, then hold at 45s. Zero when there are no failures.
    """
    if consecutive_failures <= 0:
        return 0.0
    index = min(consecutive_failures, len(_SCHEDULE)) - 1
    return _SCHEDULE[index]
