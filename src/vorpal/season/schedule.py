"""Which jobs run at a given Pacific time, and what was already sent.

One hourly cron calls ``jobs_due``. Deciding in PT here means the clock
change on 11/1 never shifts a send.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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


# (weekday, PT hour) -> lineup run. Runs at about :45 past the hour.
LINEUP: dict[tuple[int, int], bool] = {
    (WED, 6): True,
    (THU, 6): False,
    (THU, 15): False,  # TNF inactives
    (FRI, 6): False,
    (SAT, 6): False,
    (SUN, 6): False,
    (SUN, 8): False,  # early-game inactives
    (SUN, 11): False,  # late-game inactives
    (SUN, 15): False,  # SNF
    (MON, 6): False,
    (MON, 15): False,  # MNF
}
WAIVERS = (TUE, 6)


def jobs_due(now: datetime) -> list[Due]:
    local = now.astimezone(PT)
    slot = (local.weekday(), local.hour)
    due = [Due("trades", always=False)]
    if slot == WAIVERS:
        due.append(Due("waivers", always=True))
    if slot in LINEUP:
        due.append(Due("lineup", always=LINEUP[slot]))
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
