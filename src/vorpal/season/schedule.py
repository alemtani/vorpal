"""Which jobs run at a given Pacific time, and what was already sent.

One hourly cron calls ``jobs_due``. Deciding in PT here means the clock
change on 11/1 never shifts a send. GitHub delays and drops scheduled
runs, so a slot stays due for the rest of its PT day until a run records
it. A later slot of the same job replaces an earlier one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


@dataclass(frozen=True)
class Due:
    job: str
    always: bool
    """False: send only when the advice changed since the last send."""
    slot: str = field(default="", compare=False)
    """The PT slot this run covers, e.g. ``2026-10-20T05``. Empty for trades."""


# (weekday, PT hour) -> lineup run. Runs at about :45 past the hour.
# Morning slots start at 05:00 so a delayed run still lands before 08:00.
LINEUP: dict[tuple[int, int], bool] = {
    (WED, 5): True,
    (THU, 5): False,
    (THU, 15): False,  # TNF inactives
    (FRI, 5): False,
    (SAT, 5): False,
    (SUN, 5): False,
    (SUN, 8): False,  # early-game inactives
    (SUN, 11): False,  # late-game inactives
    (SUN, 15): False,  # SNF
    (MON, 5): False,
    (MON, 15): False,  # MNF
}
WAIVERS = (TUE, 5)


def _slot(local: datetime, hours: list[int]) -> str | None:
    """Today's latest slot hour that has started, as a key."""
    started = [h for h in hours if h <= local.hour]
    return f"{local:%Y-%m-%d}T{max(started):02d}" if started else None


def jobs_due(now: datetime, log: SentLog | None = None) -> list[Due]:
    """Jobs to run now. With ``log``, a slot it already holds is skipped."""
    local = now.astimezone(PT)
    day = local.weekday()
    due = [Due("trades", always=False)]
    slots = {
        "waivers": ({WAIVERS[1]: True} if day == WAIVERS[0] else {}),
        "lineup": {h: always for (d, h), always in LINEUP.items() if d == day},
    }
    for job, hours in slots.items():
        slot = _slot(local, list(hours))
        if slot is None or (log is not None and not log.changed(f"slot:{job}", slot)):
            continue
        due.append(Due(job, always=hours[int(slot[-2:])], slot=slot))
    return due


class SentLog:
    """Last key sent per job, in a small JSON file the Actions cache keeps."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, str] = (
            json.loads(path.read_text()) if path.exists() else {}
        )

    def changed(self, job: str, key: str) -> bool:
        return self._data.get(job) != key

    def record(self, job: str, key: str) -> None:
        self._data[job] = key
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=1, sort_keys=True))
