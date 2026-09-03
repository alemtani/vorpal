"""Redacted JSON snapshot of a completed draft. The save half of an eval case.

Payload + proposal + human pick + pick numbers. Player ids only. No league
id, no manager names, no player names. GitHub-issue filing waits on #29.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from vorpal.contracts import Payload, Pick, Proposal

IDENTITY_KEYS = frozenset(
    {
        "league_id",
        "scoring_league_id",
        "draft_id",
        "picked_by",
        "display_name",
        "username",
        "user_id",
        "first_name",
        "last_name",
        "name",
    }
)


class _Observed(Protocol):
    payload: Payload
    proposal: Proposal


def snapshot_path_for(output_path: Path | str) -> Path:
    """Sibling of the board file, gitignored via ``*.local.json``."""

    path = Path(output_path)
    return path.with_name(f"{path.stem}.snapshot.local.json")


def redact(value: object) -> object:
    """Drop league/manager identity and player names. Keep player ids."""

    if isinstance(value, dict):
        return {
            key: redact(item) for key, item in value.items() if key not in IDENTITY_KEYS
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def write_snapshot(path: Path | str, records: list[dict[str, Any]]) -> None:
    """Atomic JSON write. Readers never see a partial file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    body = {"picks": records}
    tmp.write_text(
        json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


class SnapshotCollector:
    """On-clock payload+proposal, joined to the operator's clicks at complete."""

    __slots__ = ("_frames", "_slot")

    def __init__(self) -> None:
        self._frames: dict[int, tuple[Payload, Proposal]] = {}
        self._slot: int | None = None

    def observe(self, frame: _Observed) -> None:
        payload = frame.payload
        self._slot = payload.config.slot
        until = payload.state.picks_until_next
        if until is None or until == 0:
            self._frames[payload.state.pick_no] = (payload, frame.proposal)

    def records(self, picks: tuple[Pick, ...]) -> list[dict[str, Any]]:
        slot = self._slot
        if slot is None:
            return []
        out: list[dict[str, Any]] = []
        for pick in picks:
            if pick.draft_slot != slot:
                continue
            stored = self._frames.get(pick.pick_no)
            payload_blob: object = None
            proposal_blob: object = None
            if stored is not None:
                payload, proposal = stored
                payload_blob = redact(payload.to_dict())
                proposal_blob = redact(proposal.to_dict())
            out.append(
                {
                    "human_pick": pick.player_id,
                    "payload": payload_blob,
                    "pick_no": pick.pick_no,
                    "proposal": proposal_blob,
                }
            )
        return out

    def write(self, path: Path | str, picks: tuple[Pick, ...]) -> None:
        write_snapshot(path, self.records(picks))
