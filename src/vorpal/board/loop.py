"""Draft-night poll loop. Time, host client, and recompute are injected."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vorpal.board.feedback import FeedbackCollector
from vorpal.board.render import render, render_unavailable
from vorpal.board.schedule import next_backoff, poll_interval
from vorpal.board.snapshot import SnapshotCollector, snapshot_path_for
from vorpal.contracts import Banner, Draft, Payload, Pick, Proposal
from vorpal.errors import PlatformError, VorpalError


class DraftPollClient(Protocol):
    """S1 client surface the loop needs. S8 injects a bound client.

    Only ``get_draft`` and ``get_picks`` run on this loop. Forecast files
    stay outside; they are fetched once per process.
    """

    def get_draft(self) -> Draft:
        """Current draft. ``status`` is the poll-rate source of truth."""

    def get_picks(self) -> tuple[Pick, ...]:
        """Current picks. The only live input besides draft metadata."""


@dataclass(frozen=True, slots=True)
class Frame:
    """One computed board. S8's recompute callable returns this."""

    payload: Payload
    proposal: Proposal
    banners: tuple[Banner, ...]


def write_html(path: Path, html: str) -> None:
    """Write ``html`` via a same-directory replace. Readers never see a partial file."""

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(path)


class _WriteOnce:
    """``write_html``, plus a one-shot callback after the first page lands.

    Latches on the write, not on the poll: the callback only ever sees a file
    that exists. A callback that raises is the caller's to handle — the loop
    never lets it stop a draft.
    """

    __slots__ = ("_on_first", "_written")

    def __init__(self, on_first: Callable[[Path], None] | None) -> None:
        self._on_first = on_first
        self._written = False

    def __call__(self, path: Path, html: str) -> None:
        write_html(path, html)
        if self._written:
            return
        self._written = True
        if self._on_first is not None:
            self._on_first(path)


def run_loop(
    client: DraftPollClient,
    recompute: Callable[[Draft, tuple[Pick, ...]], Frame],
    output_path: Path | str,
    *,
    now: Callable[[], float],
    sleep: Callable[[float], None],
    should_stop: Callable[[], bool] | None = None,
    feedback: FeedbackCollector | None = None,
    on_first_board: Callable[[Path], None] | None = None,
) -> None:
    """Poll draft and picks, recompute, write ``board.html``, until complete.

    ``now`` and ``sleep`` are injected. Tests pass a fake clock; S8 passes
    wall-clock callables. Permanent ``VorpalError`` subclasses write a loud
    page and re-raise. ``PlatformError`` backs off 5s, 15s, 45s, then holds,
    and resets the schedule on the next success. A completed draft also
    writes a redacted JSON snapshot next to the board (#22). Skip
    records (#29) persist at click when ``feedback`` is passed.

    ``on_first_board`` is called once, with ``path``, after the first page is
    written — board, platform-error, or refusal alike. The loop rewrites the
    same file every poll and an open tab follows it, so opening per poll would
    only bury the operator in tabs.
    """

    path = Path(output_path)
    write = _WriteOnce(on_first_board)
    last: tuple[Frame, float] | None = None
    failures = 0
    collector = SnapshotCollector()
    while True:
        if should_stop is not None and should_stop():
            return
        fetched_at = now()
        try:
            draft = client.get_draft()
            picks = client.get_picks()
            frame = recompute(draft, picks)
        except PlatformError as exc:
            failures += 1
            _write_platform_error(path, exc, last, fetched_at, now, write)
            sleep(next_backoff(failures))
            continue
        except VorpalError as exc:
            _write_refusal(path, exc, fetched_at, now, write)
            raise
        failures = 0
        last = (frame, fetched_at)
        age = now() - fetched_at
        write(
            path,
            render(frame.payload, frame.proposal, age, frame.banners),
        )
        collector.observe(frame)
        if feedback is not None:
            feedback.observe(frame, picks)
        if draft.status == "complete":
            snap = snapshot_path_for(path)
            collector.write(snap, picks)
            if feedback is not None:
                feedback.finish(snap)
            return
        sleep(poll_interval(draft.status))


def _write_platform_error(
    path: Path,
    exc: PlatformError,
    last: tuple[Frame, float] | None,
    fetched_at: float,
    now: Callable[[], float],
    write: Callable[[Path, str], None] = write_html,
) -> None:
    extra = (Banner(code="platform_error", message=exc.message),)
    if last is None:
        write(
            path,
            render_unavailable(
                exc.message,
                now() - fetched_at,
                extra,
            ),
        )
        return
    frame, good_at = last
    age = now() - good_at
    write(
        path,
        render(frame.payload, frame.proposal, age, extra + frame.banners),
    )


def _write_refusal(
    path: Path,
    exc: VorpalError,
    fetched_at: float,
    now: Callable[[], float],
    write: Callable[[Path, str], None] = write_html,
) -> None:
    code = _refusal_code(exc)
    write(
        path,
        render_unavailable(
            exc.message,
            now() - fetched_at,
            (Banner(code=code, message=exc.message),),
        ),
    )


def _refusal_code(exc: VorpalError) -> str:
    chars: list[str] = []
    for char in type(exc).__name__:
        if char.isupper() and chars:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)
