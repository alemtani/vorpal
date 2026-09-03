"""Draft-night skip capture. Empty why-not at click; form and issue at complete.

No prompt mid-draft. No live GitHub in tests — the opener is injected.
Traces are whatever propose returned, redacted to player ids.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO

from vorpal.board.snapshot import redact
from vorpal.contracts import Pick, Proposal

OpenIssue = Callable[[str, str], str]
WhyNotForm = Callable[[list["SkipRecord"]], None]


class _Observed(Protocol):
    payload: Any
    proposal: Proposal


@dataclass(slots=True)
class SkipRecord:
    """One differing pick. ``why_not`` stays empty until the complete-time form."""

    pick_no: int
    human_pick: str
    rec: str
    alternatives: tuple[str, ...]
    coin_flip: bool
    why_not: str | None
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "alternatives": list(self.alternatives),
            "coin_flip": self.coin_flip,
            "human_pick": self.human_pick,
            "pick_no": self.pick_no,
            "rec": self.rec,
            "trace": self.trace,
            "why_not": self.why_not,
        }


def is_skip(human_pick: str, proposal: Proposal) -> bool:
    """True when the click is not the rec, unless coin_flip and the click is an alt."""

    rec = proposal.player_id
    if human_pick == rec:
        return False
    if human_pick in proposal.alternatives:
        return not proposal.coin_flip
    return True


def skips_path_for(output_path: Path | str) -> Path:
    path = Path(output_path)
    return path.with_name(f"{path.stem}.skips.local.json")


class FeedbackCollector:
    """Skip records at click; why-not form and GitHub issue at complete."""

    __slots__ = (
        "_open_issue",
        "_on_clock",
        "_path",
        "_seen",
        "_skips",
        "_slot",
        "_traces",
        "_why_not_form",
    )

    def __init__(
        self,
        *,
        path: Path | str,
        why_not_form: WhyNotForm,
        open_issue: OpenIssue,
    ) -> None:
        self._path = Path(path)
        self._why_not_form = why_not_form
        self._open_issue = open_issue
        self._skips: list[SkipRecord] = []
        self._seen: set[int] = set()
        self._on_clock: dict[int, Proposal] = {}
        self._slot: int | None = None
        self._traces: dict[int, dict[str, Any]] = {}

    def remember_trace(self, pick_no: int, trace: dict[str, Any]) -> None:
        self._traces[pick_no] = redact(trace)  # type: ignore[assignment]

    def observe(self, frame: _Observed, picks: tuple[Pick, ...]) -> None:
        payload = frame.payload
        self._slot = payload.config.slot
        until = payload.state.picks_until_next
        if until is None or until == 0:
            self._on_clock[payload.state.pick_no] = frame.proposal
        slot = self._slot
        if slot is None:
            return
        for pick in picks:
            if pick.draft_slot != slot or pick.pick_no in self._seen:
                continue
            self._seen.add(pick.pick_no)
            proposal = self._on_clock.get(pick.pick_no)
            if proposal is None or not is_skip(pick.player_id, proposal):
                continue
            self._skips.append(
                SkipRecord(
                    pick_no=pick.pick_no,
                    human_pick=pick.player_id,
                    rec=proposal.player_id,
                    alternatives=proposal.alternatives,
                    coin_flip=proposal.coin_flip,
                    why_not=None,
                    trace=self._traces.get(pick.pick_no, {}),
                )
            )
            self._persist()

    def finish(self, snapshot_path: Path | str) -> None:
        snap = Path(snapshot_path)
        if not self._skips or not snap.is_file():
            return
        try:
            self._why_not_form(self._skips)
        except Exception:
            pass
        self._persist()
        title, body = issue_text(self._skips, snap)
        try:
            self._open_issue(title, body)
        except Exception:
            pass

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        body = {"skips": [redact(skip.to_dict()) for skip in self._skips]}
        tmp.write_text(
            json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self._path)


def issue_text(skips: list[SkipRecord], snapshot_path: Path) -> tuple[str, str]:
    """GitHub issue title and body. Player ids only."""

    title = f"draft feedback: {len(skips)} skip(s)"
    lines = [
        f"Snapshot: `{snapshot_path}`",
        "",
        "## Skips",
    ]
    for skip in skips:
        why = skip.why_not if skip.why_not else "(empty)"
        trace = skip.trace
        attempts = trace.get("attempts", "?")
        codes = [violation["code"] for violation in trace.get("violations", [])]
        lines.extend(
            [
                f"### pick {skip.pick_no}",
                f"- rec: `{skip.rec}`",
                f"- human: `{skip.human_pick}`",
                f"- alternatives: `{list(skip.alternatives)}`",
                f"- attempts: {attempts}",
                f"- violations: `{codes}`",
                f"- why-not: {why}",
                "",
                "```json",
                json.dumps(skip.trace, indent=2, sort_keys=True, ensure_ascii=False),
                "```",
                "",
            ]
        )
    return title, "\n".join(lines)


def tty_why_not_form(
    skips: list[SkipRecord],
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """One aggregate form. Blank row or non-TTY leaves that slot empty."""

    if not skips:
        return
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stderr
    if not in_stream.isatty():
        return
    print(
        "why-not for each skip (blank line leaves that row empty):",
        file=out_stream,
    )
    for skip in skips:
        print(
            f"  pick {skip.pick_no} rec={skip.rec} human={skip.human_pick}",
            file=out_stream,
        )
        try:
            line = in_stream.readline()
        except Exception:
            return
        if line == "":
            return
        text = line.strip()
        if text:
            skip.why_not = text


def gh_issue_create(
    title: str,
    body: str,
    *,
    run: Callable[..., Any] = subprocess.run,
) -> str:
    """Open an issue with ``gh``. Tests pass a stub ``run``; never live in CI."""

    result = run(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            "alemtani/vorpal",
            "--title",
            title,
            "--body",
            body,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if getattr(result, "returncode", 1) != 0:
        err = getattr(result, "stderr", "") or "gh issue create failed"
        raise RuntimeError(err)
    return str(getattr(result, "stdout", "")).strip()
