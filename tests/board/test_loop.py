"""Poll loop. Fake clock, fake client. Tests never sleep."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from vorpal.contracts import Banner, Draft, Payload, Pick, Proposal
from vorpal.errors import (
    DataRefusal,
    PlatformError,
    UnsupportedLeague,
    UserRefusal,
    VorpalError,
)


class FakeClock:
    """Monotonic clock that advances only when sleep() is called, or by advance()."""

    def __init__(self, t: float = 1_000.0) -> None:
        self.t = t
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeClient:
    """Records draft/picks calls. Optional per-call errors. Repeats the last draft."""

    def __init__(
        self,
        drafts: Draft | list[Draft],
        picks: tuple[Pick, ...] | list[tuple[Pick, ...]] = (),
        errors: list[BaseException | None] | None = None,
    ) -> None:
        self._drafts = [drafts] if isinstance(drafts, Draft) else list(drafts)
        if isinstance(picks, tuple):
            self._picks: list[tuple[Pick, ...]] = [picks]
        else:
            self._picks = list(picks)
        self._errors = list(errors or [])
        self.log: list[str] = []
        self.n = 0

    def get_draft(self) -> Draft:
        self.log.append("get_draft")
        self._raise()
        draft = self._drafts[min(self.n, len(self._drafts) - 1)]
        self.n += 1
        return draft

    def get_picks(self) -> tuple[Pick, ...]:
        self.log.append("get_picks")
        return self._picks[min(self.n - 1, len(self._picks) - 1)]

    def get_projections(self) -> None:
        raise AssertionError("loop must not poll projections")

    def get_players(self) -> None:
        raise AssertionError("loop must not fetch /players on the poll loop")

    def get_ecr(self) -> None:
        raise AssertionError("loop must not poll FantasyPros")

    def _raise(self) -> None:
        if self.n < len(self._errors):
            err = self._errors[self.n]
            if err is not None:
                self.n += 1
                raise err


def _frame(payload: Payload, proposal: Proposal, banners: tuple[Banner, ...] = ()):
    from vorpal.board import Frame

    return Frame(payload=payload, proposal=proposal, banners=tuple(banners))


def _recompute(
    payload: Payload,
    proposal: Proposal,
    banners: tuple[Banner, ...] = (),
):
    calls: list[tuple[Draft, tuple[Pick, ...]]] = []

    def inner(draft: Draft, picks: tuple[Pick, ...]):
        calls.append((draft, picks))
        return _frame(payload, proposal, banners)

    inner.calls = calls  # type: ignore[attr-defined]
    return inner


def _stop_after_polls(client: FakeClient, n: int):
    def should_stop() -> bool:
        return client.n >= n

    return should_stop


def test_drafting_polls_every_3s(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    client = FakeClient(make_draft(status="drafting"))
    run_loop(
        client,
        _recompute(make_payload(), make_proposal()),
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
        should_stop=_stop_after_polls(client, 3),
    )
    assert clock.sleeps == [3, 3, 3]


def test_non_drafting_statuses_poll_every_15s_until_complete(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    for status in ("pre_draft", "paused", "mystery"):
        clock = FakeClock()
        client = FakeClient(make_draft(status=status))
        run_loop(
            client,
            _recompute(make_payload(status=status), make_proposal()),
            tmp_path / f"{status}.html",
            now=clock.now,
            sleep=clock.sleep,
            should_stop=_stop_after_polls(client, 2),
        )
        assert clock.sleeps == [15, 15], status


def test_complete_writes_once_and_does_not_sleep(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    path = tmp_path / "board.html"
    client = FakeClient(make_draft(status="complete"))
    run_loop(
        client,
        _recompute(make_payload(status="complete"), make_proposal()),
        path,
        now=clock.now,
        sleep=clock.sleep,
    )
    assert clock.sleeps == []
    assert path.is_file()
    html = path.read_text(encoding="utf-8")
    assert "A Back" in html
    assert not (tmp_path / "board.html.tmp").exists()


def test_drafting_then_complete_sleeps_once_then_stops(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    client = FakeClient(
        [
            make_draft(status="drafting"),
            make_draft(status="complete"),
        ]
    )
    run_loop(
        client,
        _recompute(make_payload(), make_proposal()),
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
    )
    assert clock.sleeps == [3]


def test_error_backoff_is_5_15_45_hold_and_resets_on_success(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    err = PlatformError("sleeper 500")
    client = FakeClient(
        make_draft(status="drafting"),
        errors=[err, err, err, err, None, err],
    )
    run_loop(
        client,
        _recompute(make_payload(), make_proposal()),
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
        should_stop=_stop_after_polls(client, 6),
    )
    assert clock.sleeps == [5, 15, 45, 45, 3, 5]


def test_loop_never_calls_projections_players_or_fantasypros(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    pick = make_pick()
    client = FakeClient(make_draft(status="complete"), picks=(pick,))
    recompute = _recompute(make_payload(), make_proposal())
    run_loop(
        client,
        recompute,
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
    )
    assert client.log == ["get_draft", "get_picks"]
    assert recompute.calls[0][1] == (pick,)


def test_failed_poll_rewrites_last_board_with_age_and_degrades(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    client = FakeClient(
        make_draft(status="drafting"),
        errors=[None, PlatformError("timeout")],
    )
    run_loop(
        client,
        _recompute(make_payload(), make_proposal()),
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
        should_stop=_stop_after_polls(client, 2),
    )
    assert clock.sleeps == [3, 5]
    html = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "A Back" in html
    assert "timeout" in html
    assert 'data-age-seconds="3"' in html


def test_stale_error_path_greys_out_at_pick_timer_but_not_when_timer_off(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    errors: list[BaseException | None] = [None] + [PlatformError("down")] * 5
    clock = FakeClock()
    client = FakeClient(make_draft(status="drafting", pick_timer=60), errors=errors)
    run_loop(
        client,
        _recompute(make_payload(pick_timer=60), make_proposal()),
        tmp_path / "on.html",
        now=clock.now,
        sleep=clock.sleep,
        should_stop=_stop_after_polls(client, 6),
    )
    html = (tmp_path / "on.html").read_text(encoding="utf-8")
    assert 'data-greyed="true"' in html
    assert 'data-degraded="true"' in html
    assert "not current" in html.lower()

    clock2 = FakeClock()
    client2 = FakeClient(
        make_draft(status="drafting", pick_timer=0),
        errors=errors,
    )
    run_loop(
        client2,
        _recompute(make_payload(pick_timer=0), make_proposal()),
        tmp_path / "off.html",
        now=clock2.now,
        sleep=clock2.sleep,
        should_stop=_stop_after_polls(client2, 6),
    )
    off = (tmp_path / "off.html").read_text(encoding="utf-8")
    assert 'data-greyed="false"' in off
    assert 'data-degraded="true"' in off


def test_first_poll_platform_error_writes_unavailable_page(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    client = FakeClient(
        make_draft(status="drafting"),
        errors=[PlatformError("sleeper returned 500")],
    )
    run_loop(
        client,
        _recompute(make_payload(), make_proposal()),
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
        should_stop=_stop_after_polls(client, 1),
    )
    html = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "sleeper returned 500" in html
    assert "not current" in html.lower()
    assert "A Back" not in html
    assert clock.sleeps == [5]


@pytest.mark.parametrize(
    "exc",
    [
        UnsupportedLeague("dynasty is out of v1"),
        DataRefusal("override file is missing counting stats"),
        UserRefusal("operator is not in draft_order"),
    ],
)
def test_permanent_refusals_write_loudly_then_raise(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    exc: VorpalError,
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    client = FakeClient(make_draft(), errors=[exc])
    with pytest.raises(type(exc), match=exc.message):
        run_loop(
            client,
            _recompute(make_payload(), make_proposal()),
            tmp_path / "board.html",
            now=clock.now,
            sleep=clock.sleep,
        )
    html = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert exc.message in html
    assert "not current" in html.lower()
    assert 'class="banner"' in html
    assert clock.sleeps == []


def test_recompute_platform_error_uses_backoff(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    client = FakeClient(make_draft(status="drafting"))

    def boom(draft: Draft, picks: tuple[Pick, ...]):
        raise PlatformError("model host 502")

    run_loop(
        client,
        boom,
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
        should_stop=_stop_after_polls(client, 2),
    )
    assert clock.sleeps == [5, 15]
    html = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "model host 502" in html


def test_loop_passes_recompute_banners_into_render(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import run_loop

    clock = FakeClock()
    extra = (Banner(code="ecr_missing", message="FantasyPros is down"),)
    client = FakeClient(make_draft(status="complete"))
    run_loop(
        client,
        _recompute(make_payload(), make_proposal(), banners=extra),
        tmp_path / "board.html",
        now=clock.now,
        sleep=clock.sleep,
    )
    html = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "FantasyPros is down" in html


def test_board_package_does_not_import_model_ingest_or_sleeper_or_sleep() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "vorpal" / "board"
    needle_sleep = "time" + ".sleep"
    forbidden = (
        needle_sleep,
        "vorpal.ingest",
        "vorpal.model",
        "vorpal.sleeper",
        "vorpal.payload",
        "vorpal.valuation",
        "fantasypros",
        "projections",
    )
    files = list(root.glob("*.py"))
    assert files, "board package must exist"
    for path in files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} contains {token}"


def test_board_tests_do_not_sleep() -> None:
    root = Path(__file__).resolve().parent
    needle = "time" + ".sleep"
    for path in root.rglob("*.py"):
        assert needle not in path.read_text(encoding="utf-8"), path.name


def test_complete_writes_redacted_snapshot_and_drafting_does_not(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame, run_loop

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1")

    def recompute(draft: Draft, picks: tuple[Pick, ...]) -> Frame:
        return Frame(payload=payload, proposal=proposal, banners=())

    drafting_dir = tmp_path / "live"
    drafting_dir.mkdir()
    clock = FakeClock()
    live = FakeClient(make_draft(status="drafting"))
    run_loop(
        live,
        recompute,
        drafting_dir / "board.html",
        now=clock.now,
        sleep=clock.sleep,
        should_stop=_stop_after_polls(live, 2),
    )
    assert (drafting_dir / "board.html").is_file()
    assert not (drafting_dir / "board.snapshot.local.json").exists()

    done_dir = tmp_path / "done"
    done_dir.mkdir()
    pick = make_pick(pick_no=1, player_id="p9")
    run_loop(
        FakeClient(
            [make_draft(status="drafting"), make_draft(status="complete")],
            picks=[(), (pick,)],
        ),
        recompute,
        done_dir / "board.html",
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )
    snap = done_dir / "board.snapshot.local.json"
    assert snap.is_file()
    body = json.loads(snap.read_text(encoding="utf-8"))
    turn = body["picks"][0]
    assert turn["human_pick"] == "p9"
    assert turn["proposal"]["player_id"] == "p1"
    assert turn["pick_no"] == 1
    dumped = json.dumps(body)
    assert "league_test" not in dumped
    assert "user_operator" not in dumped
    assert "A Back" not in dumped


def test_loop_persists_skip_then_opens_issue_on_complete(
    tmp_path: Path,
    make_draft: Callable[..., Draft],
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame, run_loop
    from vorpal.board.feedback import FeedbackCollector

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1", alternatives=("p2",))
    issues: list[tuple[str, str]] = []
    feedback = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=lambda skips: None,
        open_issue=lambda title, body: (
            issues.append((title, body)) or "https://example/3"
        ),
    )
    feedback.remember_trace(
        1,
        {
            "payload": {"board": [{"player_id": "p1"}]},
            "samples": [{"player_id": "p1"}],
        },
    )

    def recompute(draft: Draft, picks: tuple[Pick, ...]) -> Frame:
        return Frame(payload=payload, proposal=proposal, banners=())

    pick = make_pick(pick_no=1, player_id="p9")
    run_loop(
        FakeClient(
            [make_draft(status="drafting"), make_draft(status="complete")],
            picks=[(), (pick,)],
        ),
        recompute,
        tmp_path / "board.html",
        now=FakeClock().now,
        sleep=FakeClock().sleep,
        feedback=feedback,
    )
    assert (tmp_path / "board.snapshot.local.json").is_file()
    assert (tmp_path / "board.skips.local.json").is_file()
    assert len(issues) == 1
    assert "p9" in issues[0][1]
    assert "board.snapshot.local.json" in issues[0][1]
