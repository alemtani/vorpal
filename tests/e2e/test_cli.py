"""One command, fixtures in, a rendered page out. No live network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from league import ROSTER, SEASON, load

from vorpal import cli
from vorpal.cli import _label, _Proposals, main
from vorpal.contracts import Banner
from vorpal.errors import VorpalError
from vorpal.model import StubTransport


class HintTransport:
    """Answers with the calculator pick. A valid response, never the network."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        rec = next(
            row
            for row in payload["board"]
            if row["player_id"] == payload["hint_argmax_vols"]
        )
        return {
            "player_id": rec["player_id"],
            "alternatives": [row["player_id"] for row in payload["board"][1:3]],
            "slot_filled": rec["legal_slots"][0],
            "coin_flip": False,
            "why": "best available by VOLS",
            "flags": [],
        }


def _projections_down(api: respx.MockRouter) -> None:
    """Every position route fails. The override CSV is the only way through."""
    for position, _count in ROSTER:
        api[f"projections_{position}"].mock(return_value=httpx.Response(503))


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--draft-id",
        "draft_snake_redraft",
        "--operator",
        "operator",
        "--out",
        str(tmp_path / "board.html"),
        "--players-cache",
        str(tmp_path / "players.json"),
        "--once",
        *extra,
    ]


def _run(tmp_path: Path, *extra: str, transport: Any = None) -> tuple[int, Any]:
    transport = transport if transport is not None else HintTransport()
    code = main(_argv(tmp_path, *extra), transport=transport)
    return code, transport


def test_one_command_writes_a_board(api: respx.MockRouter, tmp_path: Path) -> None:
    code, transport = _run(tmp_path)
    assert code == 0
    page = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "<html" in page
    assert transport.calls, "the model was never asked"
    rec = transport.calls[0]["hint_argmax_vols"]
    assert rec in page or _name_of(transport.calls[0], rec) in page


def _name_of(payload: dict[str, Any], player_id: str) -> str:
    return next(
        row["name"] for row in payload["board"] if row["player_id"] == player_id
    )


def test_the_forecast_is_fetched_once_however_long_the_draft_runs(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    _run(tmp_path)
    projections = [
        call for call in api.calls if "/projections" in str(call.request.url)
    ]
    # Six positions, one call each. Never polled.
    assert len(projections) == 6


def test_the_payload_carries_the_seat_the_draft_order_gives(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    _, transport = _run(tmp_path)
    payload = transport.calls[0]
    assert payload["config"]["slot"] == 2
    assert payload["state"]["next_user_pick"] == 2
    assert payload["state"]["picks_until_next"] == 1
    assert [team["slot"] for team in payload["state"]["between"]] == [1]


def test_the_board_carries_vols_adp_ecr_and_the_bye(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    _, transport = _run(tmp_path)
    row = transport.calls[0]["board"][0]
    assert row["vols"] > 0
    assert row["adp"] > 0
    assert row["ecr"] is not None
    assert row["bye"] is not None
    assert row["legal_slots"]


def test_banners_reach_stderr_before_the_board_is_written(
    api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(tmp_path)
    err = capsys.readouterr().err
    assert "banner keepers_possible" in err
    assert (tmp_path / "board.html").exists()


def test_a_degraded_model_answer_still_writes_a_board(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    code, _ = _run(tmp_path, transport=StubTransport({"nonsense": True}))
    assert code == 0
    page = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "violation_" in page


def test_a_drafted_player_leaves_the_board(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    _, clean = _run(tmp_path)
    taken = clean.calls[0]["hint_argmax_vols"]
    api["picks"].mock(return_value=httpx.Response(200, json=[_pick(taken)]))
    _, after = _run(tmp_path)
    ids = {row["player_id"] for row in after.calls[0]["board"]}
    assert taken not in ids
    assert after.calls[0]["state"]["pick_no"] == 2


def _pick(player_id: str) -> dict[str, Any]:
    return {
        "draft_id": "draft_snake_redraft",
        "player_id": player_id,
        "picked_by": "user_09",
        "roster_id": 1,
        "round": 1,
        "draft_slot": 1,
        "pick_no": 1,
        "is_keeper": None,
        "metadata": {"position": "RB", "first_name": "Rb", "last_name": "Number1"},
    }


def test_the_poll_loop_stops_on_a_complete_draft(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    slept: list[float] = []
    argv = [arg for arg in _argv(tmp_path) if arg != "--once"]
    code = main(argv, transport=HintTransport(), sleep=slept.append, now=lambda: 0.0)
    assert code == 0
    assert slept == []
    assert (tmp_path / "board.html").exists()


def test_an_unsupported_league_exits_two_with_its_own_word(
    api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = load("sleeper", "draft_snake_redraft.json")
    draft["settings"]["reversal_round"] = 3
    api["draft"].mock(return_value=httpx.Response(200, json=draft))
    code, _ = _run(tmp_path)
    assert code == 2
    assert "unsupported league:" in capsys.readouterr().err


def test_a_user_refusal_exits_two_with_its_own_word(
    api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = load("sleeper", "draft_snake_redraft.json")
    draft["draft_order"].pop("user_operator")
    api["draft"].mock(return_value=httpx.Response(200, json=draft))
    code, _ = _run(tmp_path)
    assert code == 2
    assert "user refusal:" in capsys.readouterr().err


def test_a_data_refusal_exits_two_with_its_own_word(
    api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _projections_down(api)
    code, _ = _run(tmp_path)
    assert code == 2
    assert "data refusal:" in capsys.readouterr().err


def test_a_platform_error_exits_two_with_its_own_word(
    api: respx.MockRouter, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api["draft"].mock(return_value=httpx.Response(500))
    code, _ = _run(tmp_path)
    assert code == 2
    assert "platform error:" in capsys.readouterr().err


def test_a_standalone_mock_borrows_scoring_from_the_named_league(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    draft = load("sleeper", "draft_mock_standalone.json")
    draft["draft_id"] = "draft_snake_redraft"
    draft["season"] = SEASON
    draft["draft_order"] = {"user_operator": 2}
    api["draft"].mock(return_value=httpx.Response(200, json=draft))
    code, transport = _run(tmp_path, "--scoring-league-id", "league_snake_redraft")
    assert code == 0
    codes = {banner["code"] for banner in transport.calls[0]["config"]["banners"]}
    assert {"slots_from_mock", "scoring_borrowed"} <= codes


def test_an_override_csv_replaces_the_projection_host(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    _projections_down(api)
    csv = tmp_path / "override.csv"
    csv.write_text(_override_csv(), encoding="utf-8")
    code, transport = _run(tmp_path, "--override", str(csv))
    assert code == 0
    codes = {banner["code"] for banner in transport.calls[0]["config"]["banners"]}
    assert "projections_override" not in codes  # it is a forecast banner
    board = {row["player_id"] for row in transport.calls[0]["board"]}
    assert "rb1" in board


def _override_csv() -> str:
    """Every nonzero scoring key needs a column. Most of them are zero here."""
    scoring = load("sleeper", "league_snake_redraft.json")["scoring_settings"]
    columns = sorted(key for key, weight in scoring.items() if weight)
    header = ["player_id", "adp", *columns]
    lines = [",".join(header) + "\n"]
    live = {"rush_yd": 1100.0, "rush_td": 9.0, "rec": 40.0, "rec_yd": 300.0}
    for position, count in (("rb", 60), ("wr", 60), ("qb", 24), ("te", 24)):
        for index in range(1, count + 1):
            scale = 1.0 - 0.01 * (index - 1)
            values = [f"{position}{index}", f"{float(index)}"]
            values += [
                f"{round(live.get(column, 0.0) * scale, 2)}" for column in columns
            ]
            lines.append(",".join(values) + "\n")
    return "".join(lines)


def test_an_unclassified_vorpal_error_still_names_itself() -> None:
    """The four classes are the taxonomy; a bare VorpalError still exits 2."""
    assert _label(VorpalError("odd")) == "error"


def test_a_keeper_never_reaches_the_pool(api: respx.MockRouter, tmp_path: Path) -> None:
    keeper = _pick("rb1")
    keeper["is_keeper"] = True
    api["picks"].mock(return_value=httpx.Response(200, json=[keeper]))
    _, transport = _run(tmp_path)
    board = {row["player_id"] for row in transport.calls[0]["board"]}
    assert "rb1" not in board


class _FakeState:
    def __init__(self, pick_no: int, picks_until_next: int | None) -> None:
        self.pick_no = pick_no
        self.picks_until_next = picks_until_next


class _FakePayload:
    def __init__(self, pick_no: int, picks_until_next: int | None) -> None:
        self.state = _FakeState(pick_no, picks_until_next)


class _CountingProposals(_Proposals):
    """``propose`` replaced by a counter. The gate is what is under test."""

    def __init__(self) -> None:
        super().__init__(transport=None)
        self.calls = 0

    def _call(self, payload: Any, pick_no: int) -> tuple[Any, tuple[Banner, ...]]:
        self.calls += 1
        self._proposal = f"proposal for {pick_no}"
        self._banners = ()
        self._pick_no = pick_no
        return self._proposal, ()

    def _placeholder(self, payload: Any) -> tuple[Any, tuple[Banner, ...]]:
        return f"calculator for {payload.state.pick_no}", ()


def test_a_board_that_is_not_your_pick_does_not_ask_the_model() -> None:
    proposals = _CountingProposals()
    proposal, _banners = proposals.for_payload(
        _FakePayload(pick_no=1, picks_until_next=40)
    )
    assert proposals.calls == 0
    assert proposal == "calculator for 1"


def test_one_or_two_picks_away_is_still_not_your_pick() -> None:
    """The old window of 2 burned a call on every pick in front of the seat."""
    proposals = _CountingProposals()
    for until in (2, 1):
        proposals.for_payload(_FakePayload(pick_no=10, picks_until_next=until))
    assert proposals.calls == 0


def test_the_model_runs_only_when_the_operator_is_on_the_clock() -> None:
    proposals = _CountingProposals()
    proposals.for_payload(_FakePayload(pick_no=1, picks_until_next=40))
    proposal, banners = proposals.for_payload(
        _FakePayload(pick_no=18, picks_until_next=0)
    )
    assert proposals.calls == 1
    assert proposal == "proposal for 18"
    assert banners == ()


def test_the_same_pick_on_the_clock_never_asks_twice() -> None:
    proposals = _CountingProposals()
    for _ in range(20):
        proposal, banners = proposals.for_payload(
            _FakePayload(pick_no=18, picks_until_next=0)
        )
    assert proposals.calls == 1
    assert proposal == "proposal for 18"
    assert banners == ()


def test_after_your_pick_the_page_goes_back_to_the_calculator() -> None:
    proposals = _CountingProposals()
    proposals.for_payload(_FakePayload(pick_no=18, picks_until_next=0))
    proposal, _banners = proposals.for_payload(
        _FakePayload(pick_no=19, picks_until_next=19)
    )
    assert proposals.calls == 1
    assert proposal == "calculator for 19"


def test_no_seat_means_no_clock_so_every_new_pick_asks() -> None:
    proposals = _CountingProposals()
    for pick_no in (1, 2, 3):
        proposals.for_payload(_FakePayload(pick_no=pick_no, picks_until_next=None))
    assert proposals.calls == 3


def test_the_poll_loop_does_not_ask_the_model_on_every_poll(
    api: respx.MockRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Draft night is mostly other people's picks. They are not model calls."""
    drafting = load("sleeper", "draft_snake_redraft.json")
    drafting["status"] = "drafting"
    complete = load("sleeper", "draft_snake_redraft.json")
    polls = {"draft": 0}

    def draft_response(request: httpx.Request) -> httpx.Response:
        polls["draft"] += 1
        # Three live polls, then the draft ends and the loop returns.
        return httpx.Response(200, json=drafting if polls["draft"] <= 4 else complete)

    first = _pick("nobody")
    second = {**_pick("nobody2"), "draft_slot": 2, "pick_no": 2}
    # The startup fetch, an empty first poll, then the operator's own pick
    # lands and the seat is twenty picks away. The last poll changes nothing.
    scripted = [[], [], [first, second], [first, second]]

    def picks_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=scripted.pop(0) if scripted else [first, second]
        )

    api["draft"].mock(side_effect=draft_response)
    api["picks"].mock(side_effect=picks_response)

    asked: list[int] = []
    built: list[int] = []
    real_propose = cli.propose
    real_build_payload = cli.build_payload

    def counting_propose(payload: Any, transport: Any) -> Any:
        asked.append(payload.state.pick_no)
        return real_propose(payload, transport)

    def counting_build_payload(config: Any, state: Any, *rest: Any) -> Any:
        built.append((state.pick_no, config.status))
        return real_build_payload(config, state, *rest)

    monkeypatch.setattr(cli, "propose", counting_propose)
    monkeypatch.setattr(cli, "build_payload", counting_build_payload)

    argv = [arg for arg in _argv(tmp_path) if arg != "--once"]
    code = main(argv, transport=HintTransport(), sleep=lambda _s: None, now=lambda: 0.0)
    assert code == 0
    # Seat 2 is never on the clock in this script (pick 1 is one away, pick 3
    # is twenty away). The model must not run for other people's picks.
    assert asked == []
    # Four polls, three boards. The third poll found pick 3 again and built
    # nothing. The fourth rebuilt only because `complete` is on the page.
    assert built == [(1, "drafting"), (3, "drafting"), (3, "complete")]
    page = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "proposal_not_current" not in page


def test_a_complete_draft_writes_a_redacted_snapshot(
    api: respx.MockRouter, tmp_path: Path
) -> None:
    """--once on a completed mock still writes the file. Player ids only."""
    operator_pick = _pick("rb1")
    operator_pick["draft_slot"] = 2
    operator_pick["picked_by"] = "user_operator"
    operator_pick["pick_no"] = 2
    api["picks"].mock(return_value=httpx.Response(200, json=[operator_pick]))
    code, _ = _run(tmp_path)
    assert code == 0
    snap = tmp_path / "board.snapshot.local.json"
    assert snap.is_file()
    body = json.loads(snap.read_text(encoding="utf-8"))
    assert [turn["human_pick"] for turn in body["picks"]] == ["rb1"]
    assert body["picks"][0]["pick_no"] == 2
    dumped = json.dumps(body)
    assert "league_snake_redraft" not in dumped
    assert "user_operator" not in dumped
    assert "league_id" not in dumped


def test_a_missing_github_token_does_not_fail_draft_night(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from vorpal.cli import _open_issue

    def boom(title: str, body: str) -> str:
        raise RuntimeError("no token")

    monkeypatch.setattr("vorpal.cli.gh_issue_create", boom)
    assert _open_issue("t", "b") == ""
    assert "github issue" in capsys.readouterr().err
