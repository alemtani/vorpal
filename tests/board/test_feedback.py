"""Skip capture, why-not form, GitHub issue. No live model, no live GitHub."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


def _keys(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        found.update(obj)
        for value in obj.values():
            found.update(_keys(value))
    elif isinstance(obj, list):
        for value in obj:
            found.update(_keys(value))
    return found


def _trace(*, player_id: str = "p1") -> dict[str, Any]:
    return {
        "attempts": 1,
        "degraded": False,
        "payload": {
            "config": {"league_id": "league_secret", "slot": 2},
            "board": [{"player_id": player_id, "name": "A Back"}],
        },
        "samples": [
            {
                "player_id": player_id,
                "alternatives": ["p2"],
                "slot_filled": "RB",
                "coin_flip": False,
                "why": "best available",
                "flags": [],
            }
        ],
        "violations": [],
    }


def test_agreement_with_the_rec_is_not_a_skip(
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board.feedback import is_skip

    proposal = make_proposal(player_id="p1", alternatives=("p2",), coin_flip=False)
    assert is_skip("p1", proposal) is False


def test_click_not_equal_rec_is_a_skip(
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board.feedback import is_skip

    proposal = make_proposal(player_id="p1", alternatives=("p2",), coin_flip=False)
    assert is_skip("p2", proposal) is True
    assert is_skip("p9", proposal) is True


def test_coin_flip_outside_rec_and_alts_is_a_skip(
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board.feedback import is_skip

    proposal = make_proposal(player_id="p1", alternatives=("p2",), coin_flip=True)
    assert is_skip("p1", proposal) is False
    assert is_skip("p2", proposal) is False
    assert is_skip("p9", proposal) is True


def test_skip_is_persisted_at_click_with_empty_why_not_and_trace(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1", alternatives=("p2",))
    skips_path = tmp_path / "board.skips.local.json"
    forms: list[int] = []
    collector = FeedbackCollector(
        path=skips_path,
        why_not_form=lambda skips: forms.append(len(skips)),
        open_issue=lambda title, body: "unused",
    )
    collector.remember_trace(1, _trace())
    collector.observe(Frame(payload=payload, proposal=proposal, banners=()), ())
    assert not skips_path.exists()
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (make_pick(pick_no=1, player_id="p9"),),
    )
    assert forms == [], "why-not form must not run mid-draft"
    body = json.loads(skips_path.read_text(encoding="utf-8"))
    assert len(body["skips"]) == 1
    skip = body["skips"][0]
    assert skip["pick_no"] == 1
    assert skip["human_pick"] == "p9"
    assert skip["rec"] == "p1"
    assert skip["alternatives"] == ["p2"]
    assert skip["why_not"] is None
    assert skip["trace"]["samples"][0]["player_id"] == "p1"
    assert IDENTITY_KEYS.isdisjoint(_keys(skip))
    assert "A Back" not in json.dumps(skip)
    assert "league_secret" not in json.dumps(skip)


def test_agreement_stays_silent(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1")
    issues: list[tuple[str, str]] = []
    collector = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=lambda skips: None,
        open_issue=lambda title, body: (
            issues.append((title, body)) or "https://example"
        ),
    )
    collector.remember_trace(1, _trace())
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (),
    )
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (make_pick(pick_no=1, player_id="p1"),),
    )
    snap = tmp_path / "board.snapshot.local.json"
    snap.write_text("{}\n", encoding="utf-8")
    collector.finish(snap)
    assert not (tmp_path / "board.skips.local.json").exists()
    assert issues == []


def test_complete_opens_issue_even_when_why_not_form_is_skipped(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1", alternatives=("p2",))
    issues: list[tuple[str, str]] = []

    def boom(_skips: object) -> None:
        raise RuntimeError("operator walked away")

    collector = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=boom,
        open_issue=lambda title, body: (
            issues.append((title, body)) or "https://example/1"
        ),
    )
    collector.remember_trace(1, _trace())
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (),
    )
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (make_pick(pick_no=1, player_id="p9"),),
    )
    snap = tmp_path / "board.snapshot.local.json"
    snap.write_text('{"picks":[]}\n', encoding="utf-8")
    collector.finish(snap)
    assert len(issues) == 1
    title, body = issues[0]
    assert "p9" in body
    assert "p1" in body
    assert str(snap) in body
    assert "why-not" in body.lower() or "why_not" in body.lower()
    assert "league_secret" not in body
    assert "A Back" not in body
    assert "operator walked away" not in body
    stored = json.loads(
        (tmp_path / "board.skips.local.json").read_text(encoding="utf-8")
    )
    assert stored["skips"][0]["why_not"] is None
    _ = title


def test_issue_body_and_skips_file_carry_attempts_and_violations(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1", alternatives=("p2",))
    issues: list[tuple[str, str]] = []
    trace = _trace()
    trace["attempts"] = 2
    trace["degraded"] = True
    trace["violations"] = [
        {"code": "rec_off_board", "message": "player_id p9 is not on the board"}
    ]
    collector = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=lambda skips: None,
        open_issue=lambda title, body: (
            issues.append((title, body)) or "https://example/3"
        ),
    )
    collector.remember_trace(1, trace)
    collector.observe(Frame(payload=payload, proposal=proposal, banners=()), ())
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (make_pick(pick_no=1, player_id="p9"),),
    )
    snap = tmp_path / "board.snapshot.local.json"
    snap.write_text("{}\n", encoding="utf-8")
    collector.finish(snap)

    body = issues[0][1]
    assert "attempts: 2" in body
    assert "rec_off_board" in body

    stored = json.loads(
        (tmp_path / "board.skips.local.json").read_text(encoding="utf-8")
    )
    stored_trace = stored["skips"][0]["trace"]
    assert stored_trace["attempts"] == 2
    assert stored_trace["violations"][0]["code"] == "rec_off_board"


def test_why_not_form_at_complete_fills_the_slot(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector, SkipRecord

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1")
    issues: list[tuple[str, str]] = []

    def form(skips: list[SkipRecord]) -> None:
        assert len(skips) == 1
        skips[0].why_not = "wanted the other back"

    collector = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=form,
        open_issue=lambda title, body: (
            issues.append((title, body)) or "https://example/2"
        ),
    )
    collector.remember_trace(1, _trace())
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (),
    )
    collector.observe(
        Frame(payload=payload, proposal=proposal, banners=()),
        (make_pick(pick_no=1, player_id="p9"),),
    )
    snap = tmp_path / "board.snapshot.local.json"
    snap.write_text("{}\n", encoding="utf-8")
    collector.finish(snap)
    stored = json.loads(
        (tmp_path / "board.skips.local.json").read_text(encoding="utf-8")
    )
    assert stored["skips"][0]["why_not"] == "wanted the other back"
    assert "wanted the other back" in issues[0][1]


def test_github_opener_is_injected_and_never_called_live() -> None:
    from vorpal.board.feedback import gh_issue_create

    calls: list[Any] = []

    class Result:
        returncode = 0
        stdout = "https://github.com/alemtani/vorpal/issues/99\n"
        stderr = ""

    def ok(argv: list[str], **kwargs: Any) -> Any:
        calls.append(argv)
        return Result()

    url = gh_issue_create("draft feedback", "player ids only", run=ok)
    assert url.endswith("/issues/99")
    assert calls[0][:3] == ["gh", "issue", "create"]
    assert "--repo" in calls[0]
    assert "alemtani/vorpal" in calls[0]
    assert "--title" in calls[0]
    assert "--body" in calls[0]
    assert "player ids only" in " ".join(calls[0])


def test_github_create_failure_raises_and_is_swallowed_by_finish(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector, gh_issue_create

    class Result:
        returncode = 1
        stdout = ""
        stderr = "no token"

    def bad(argv: list[str], **kwargs: Any) -> Any:
        return Result()

    try:
        gh_issue_create("t", "b", run=bad)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "no token" in str(exc)

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    collector = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=lambda skips: None,
        open_issue=lambda title, body: (_ for _ in ()).throw(RuntimeError("no token")),
    )
    collector.remember_trace(1, _trace())
    collector.observe(
        Frame(payload=payload, proposal=make_proposal(player_id="p1"), banners=()),
        (),
    )
    collector.observe(
        Frame(payload=payload, proposal=make_proposal(player_id="p1"), banners=()),
        (make_pick(pick_no=1, player_id="p9"),),
    )
    snap = tmp_path / "board.snapshot.local.json"
    snap.write_text("{}\n", encoding="utf-8")
    collector.finish(snap)  # must not raise


class _FakeIO:
    def __init__(self, lines: list[str], *, tty: bool) -> None:
        self._lines = list(lines)
        self._tty = tty
        self.written: list[str] = []

    def isatty(self) -> bool:
        return self._tty

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)

    def write(self, text: str) -> int:
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        return None


def test_tty_why_not_form_is_a_no_op_without_a_tty() -> None:
    from vorpal.board.feedback import SkipRecord, tty_why_not_form

    skip = SkipRecord(
        pick_no=1,
        human_pick="p9",
        rec="p1",
        alternatives=("p2",),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    stdin = _FakeIO(["because adp\n"], tty=False)
    tty_why_not_form([skip], stdin=stdin, stdout=stdin)
    assert skip.why_not is None
    tty_why_not_form([], stdin=_FakeIO([], tty=True), stdout=_FakeIO([], tty=True))


def test_tty_why_not_form_fills_or_bails_on_blank() -> None:
    from vorpal.board.feedback import SkipRecord, tty_why_not_form

    filled = SkipRecord(
        pick_no=1,
        human_pick="p9",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    stdout = _FakeIO([], tty=True)
    tty_why_not_form(
        [filled], stdin=_FakeIO(["wanted the other back\n"], tty=True), stdout=stdout
    )
    assert filled.why_not == "wanted the other back"

    blank = SkipRecord(
        pick_no=2,
        human_pick="p8",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    tty_why_not_form([blank], stdin=_FakeIO(["\n"], tty=True), stdout=stdout)
    assert blank.why_not is None

    eof = SkipRecord(
        pick_no=3,
        human_pick="p7",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    tty_why_not_form([eof], stdin=_FakeIO([], tty=True), stdout=stdout)
    assert eof.why_not is None


def test_blank_row_does_not_drop_later_skips() -> None:
    from vorpal.board.feedback import SkipRecord, tty_why_not_form

    first = SkipRecord(
        pick_no=1,
        human_pick="p9",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    second = SkipRecord(
        pick_no=2,
        human_pick="p8",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    third = SkipRecord(
        pick_no=3,
        human_pick="p7",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    tty_why_not_form(
        [first, second, third],
        stdin=_FakeIO(["took the other back\n", "\n", "bye stack\n"], tty=True),
        stdout=_FakeIO([], tty=True),
    )
    assert first.why_not == "took the other back"
    assert second.why_not is None
    assert third.why_not == "bye stack"


def test_finish_does_not_open_an_issue_before_the_snapshot_exists(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector

    issues: list[tuple[str, str]] = []
    collector = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=lambda skips: None,
        open_issue=lambda title, body: issues.append((title, body)) or "https://x",
    )
    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    collector.remember_trace(1, {"samples": [{"player_id": "p1"}]})
    collector.observe(
        Frame(payload=payload, proposal=make_proposal(player_id="p1"), banners=()),
        (),
    )
    collector.observe(
        Frame(payload=payload, proposal=make_proposal(player_id="p1"), banners=()),
        (make_pick(pick_no=1, player_id="p9"),),
    )
    collector.finish(tmp_path / "missing.snapshot.local.json")
    assert issues == []
    assert (tmp_path / "board.skips.local.json").is_file()


def test_tty_why_not_form_swallows_read_errors() -> None:
    from vorpal.board.feedback import SkipRecord, tty_why_not_form

    class Boom(_FakeIO):
        def readline(self) -> str:
            raise OSError("broken pipe")

    skip = SkipRecord(
        pick_no=1,
        human_pick="p9",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    tty_why_not_form([skip], stdin=Boom([], tty=True), stdout=_FakeIO([], tty=True))
    assert skip.why_not is None


def test_default_form_does_not_block_when_stdin_is_not_a_tty() -> None:
    from vorpal.board.feedback import SkipRecord, tty_why_not_form

    skip = SkipRecord(
        pick_no=1,
        human_pick="p9",
        rec="p1",
        alternatives=(),
        coin_flip=False,
        why_not=None,
        trace={},
    )
    tty_why_not_form([skip])
    assert skip.why_not is None


def test_skips_path_for_is_gitignored_local_json() -> None:
    from vorpal.board.feedback import skips_path_for

    assert skips_path_for(Path("board.html")).name == "board.skips.local.json"


def test_unknown_seat_and_other_seats_and_late_joins_are_not_skips(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.feedback import FeedbackCollector

    issues: list[tuple[str, str]] = []
    collector = FeedbackCollector(
        path=tmp_path / "board.skips.local.json",
        why_not_form=lambda skips: None,
        open_issue=lambda title, body: issues.append((title, body)) or "x",
    )
    none_slot = make_payload(slot=None, picks_until_next=None)
    collector.observe(
        Frame(payload=none_slot, proposal=make_proposal(), banners=()),
        (make_pick(),),
    )
    seated = make_payload(pick_no=2, picks_until_next=0, next_user_pick=2, slot=2)
    collector.observe(
        Frame(payload=seated, proposal=make_proposal(player_id="p1"), banners=()),
        (make_pick(pick_no=1, player_id="p8", draft_slot=1),),
    )
    late = make_payload(pick_no=5, picks_until_next=4, next_user_pick=9, slot=2)
    collector.observe(
        Frame(payload=late, proposal=make_proposal(player_id="p1"), banners=()),
        (make_pick(pick_no=4, player_id="p9"),),
    )
    collector.observe(
        Frame(payload=late, proposal=make_proposal(player_id="p1"), banners=()),
        (make_pick(pick_no=4, player_id="p9"),),
    )
    assert not (tmp_path / "board.skips.local.json").exists()
    collector.finish(tmp_path / "board.snapshot.local.json")
    assert issues == []
