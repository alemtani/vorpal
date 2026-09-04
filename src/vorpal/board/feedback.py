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
        "_trace_sink",
        "_traces",
        "_why_not_form",
    )

    def __init__(
        self,
        *,
        path: Path | str,
        why_not_form: WhyNotForm,
        open_issue: OpenIssue,
        trace_sink: Any | None = None,
    ) -> None:
        self._path = Path(path)
        self._why_not_form = why_not_form
        self._open_issue = open_issue
        self._trace_sink = trace_sink
        self._skips: list[SkipRecord] = []
        self._seen: set[int] = set()
        self._on_clock: dict[int, Proposal] = {}
        self._slot: int | None = None
        self._traces: dict[int, dict[str, Any]] = {}

    def remember_trace(self, pick_no: int, trace: dict[str, Any]) -> None:
        self._traces[pick_no] = redact(trace)  # type: ignore[assignment]

    def record_call(
        self,
        pick_no: int,
        payload: Any,
        recommendation: Any,
        samples: list[tuple[dict[str, Any], float]],
        latency_ms: float,
    ) -> None:
        """Keep the durable trace and emit the LangSmith run tree.

        ``latency_ms`` is wall-clock of ``propose``. It rides on the sink,
        not the skips file.
        """

        payload_dict = payload.to_dict() if hasattr(payload, "to_dict") else payload
        self.remember_trace(
            pick_no,
            {
                "attempts": recommendation.attempts,
                "degraded": recommendation.degraded,
                "payload": payload_dict,
                "samples": [sample for sample, _latency in samples],
                "violations": [
                    {"code": item.code, "message": item.message}
                    for item in recommendation.violations
                ],
            },
        )
        if self._trace_sink is not None:
            self._trace_sink.log(pick_no, payload, recommendation, samples, latency_ms)

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
        if self._trace_sink is not None:
            for skip in self._skips:
                try:
                    self._trace_sink.patch_human_pick(skip.pick_no, skip.human_pick)
                except Exception:
                    pass
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


# GitHub rejects a createIssue body over this many characters. A trace carries
# the whole board, so a full-length draft clears it on the third or fourth skip
# and the issue is lost after the snapshot is already on disk.
GITHUB_BODY_LIMIT = 65536


def issue_text(skips: list[SkipRecord], snapshot_path: Path) -> tuple[str, str]:
    """GitHub issue title and body. Player ids only.

    Traces are dropped, not truncated, when the body will not fit: half a JSON
    blob helps nobody, and the full trace is already on disk in the skips file
    next to the snapshot.
    """

    title = f"draft feedback: {len(skips)} skip(s)"
    body = _issue_body(skips, snapshot_path, with_traces=True)
    if len(body) <= GITHUB_BODY_LIMIT:
        return title, body
    return title, _issue_body(skips, snapshot_path, with_traces=False)


def _issue_body(
    skips: list[SkipRecord],
    snapshot_path: Path,
    *,
    with_traces: bool,
) -> str:
    lines = [
        f"Snapshot: `{snapshot_path}`",
        "",
    ]
    if not with_traces:
        skips_path = snapshot_path.with_name("board.skips.local.json")
        lines.extend(
            [
                f"Traces omitted: the body passed GitHub's {GITHUB_BODY_LIMIT}"
                " character limit. Full traces are in"
                f" `{skips_path}`.",
                "",
            ]
        )
    lines.append("## Skips")
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
            ]
        )
        if with_traces:
            lines.extend(
                [
                    "```json",
                    json.dumps(
                        skip.trace, indent=2, sort_keys=True, ensure_ascii=False
                    ),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines)


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
