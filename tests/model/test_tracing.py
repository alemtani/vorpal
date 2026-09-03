"""SampleRecorder and TraceSink. No live LangSmith call."""

from __future__ import annotations

import json
import sys
import threading
from types import SimpleNamespace
from typing import Any

from vorpal.contracts import (
    AdpVariant,
    Banner,
    BoardRow,
    DraftState,
    LeagueConfig,
    Need,
    Payload,
    Proposal,
    RecentPick,
    Recommendation,
    Replacement,
    Slot,
    Violation,
)
from vorpal.model import EFFORT, MODEL_ID, SampleRecorder, StubTransport, propose


def test_sample_recorder_returns_the_inner_response_unchanged() -> None:
    from vorpal.model import SampleRecorder

    inner_calls: list[dict[str, Any]] = []

    class Inner:
        def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
            inner_calls.append(payload)
            return {
                "player_id": "p1",
                "alternatives": [],
                "slot_filled": "RB",
                "coin_flip": False,
                "why": "x",
                "flags": [],
            }

    recorder = SampleRecorder(Inner())
    raw = recorder.complete({"board": [{"player_id": "p1", "name": "A Back"}]})
    assert raw["player_id"] == "p1"
    assert inner_calls[0]["board"][0]["name"] == "A Back"


def test_sample_recorder_buffers_one_pair_per_call() -> None:
    from vorpal.model import SampleRecorder

    class Inner:
        def __init__(self) -> None:
            self._n = 0

        def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
            self._n += 1
            return {"player_id": f"p{self._n}"}

    recorder = SampleRecorder(Inner())
    recorder.complete({})
    recorder.complete({})
    pairs = recorder.take()
    assert [sample["player_id"] for sample, _latency in pairs] == ["p1", "p2"]
    for _sample, latency_ms in pairs:
        assert isinstance(latency_ms, float)
        assert latency_ms >= 0.0


def test_take_clears_the_buffer() -> None:
    from vorpal.model import SampleRecorder

    class Inner:
        def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"player_id": "p1"}

    recorder = SampleRecorder(Inner())
    recorder.complete({})
    assert len(recorder.take()) == 1
    assert recorder.take() == []


# --- TraceSink -----------------------------------------------------------


class _RecordingClient:
    """Stand-in for langsmith.Client. Tests inspect created/updated runs."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[Any, dict[str, Any]]] = []
        self.flush_calls = 0

    def create_run(self, *args: Any, **kwargs: Any) -> None:
        if args:
            kwargs.setdefault("name", args[0])
            if len(args) > 1:
                kwargs.setdefault("inputs", args[1])
            if len(args) > 2:
                kwargs.setdefault("run_type", args[2])
        self.created.append(kwargs)

    def update_run(self, run_id: Any, **kwargs: Any) -> None:
        self.updated.append((run_id, kwargs))

    def flush(self) -> None:
        self.flush_calls += 1


def _proposal(**kwargs: Any) -> Proposal:
    body: dict[str, Any] = {
        "player_id": "p1",
        "alternatives": ("p2",),
        "slot_filled": Slot.RB,
        "coin_flip": False,
        "why": "we passed Loveland",
        "flags": (),
    }
    body.update(kwargs)
    return Proposal(**body)


def _rec(
    *,
    degraded: bool = False,
    attempts: int = 1,
    violations: tuple[Violation, ...] = (),
    **proposal_kw: Any,
) -> Recommendation:
    return Recommendation(
        proposal=_proposal(**proposal_kw),
        violations=violations,
        degraded=degraded,
        attempts=attempts,
    )


def _identity_payload() -> dict[str, Any]:
    return {
        "league_id": "league_secret",
        "username": "manager_bob",
        "board": [{"player_id": "12517", "name": "Colston Loveland"}],
    }


def _payload() -> Payload:
    return Payload(
        config=LeagueConfig(
            teams=12,
            rounds=15,
            slots=(Slot.RB, Slot.WR, Slot.FLEX, Slot.BN),
            scoring={"rec": 1.0},
            scoring_summary="PPR",
            banners=(Banner(code="board_capped", message="board is capped"),),
            slot=2,
            adp_variant=AdpVariant.PPR,
        ),
        state=DraftState(
            pick_no=1,
            user_roster=(),
            needs={"RB": Need(filled=0, required=1)},
            weekly=(),
            recent=(RecentPick(player_id="x", position="WR", pick_no=0),),
            next_user_pick=1,
            picks_until_next=0,
            between=(),
        ),
        replacement={"RB": Replacement(player_id="999", points=100.0)},
        hint_argmax_vols="4866",
        board=(
            BoardRow(
                player_id="4866",
                name="Saquon Barkley",
                position="RB",
                points=280.0,
                vols=40.0,
                delta_starter_points=12.0,
                adp=1.5,
                legal_slots=(Slot.RB, Slot.FLEX),
                ecr=1,
                ecr_min=1,
            ),
            BoardRow(
                player_id="7564",
                name="Amon-Ra St. Brown",
                position="WR",
                points=250.0,
                vols=30.0,
                delta_starter_points=8.0,
                adp=8.0,
                legal_slots=(Slot.WR, Slot.FLEX),
                ecr=4,
                ecr_min=2,
            ),
        ),
    )


def _valid_sample() -> dict[str, Any]:
    return {
        "player_id": "4866",
        "alternatives": ["7564"],
        "slot_filled": "RB",
        "coin_flip": False,
        "why": "highest VOLS and fills an empty RB starter",
        "flags": ["EMPTY_STARTER"],
    }


def _parents(client: _RecordingClient) -> list[dict[str, Any]]:
    return [run for run in client.created if not run.get("parent_run_id")]


def _children(client: _RecordingClient) -> list[dict[str, Any]]:
    return [run for run in client.created if run.get("parent_run_id")]


def test_tracing_off_without_key_is_a_noop() -> None:
    from vorpal.model.tracing import TraceSink

    sink = TraceSink(environ={"VORPAL_TRACING": "on"})
    assert sink.enabled() is False
    sink.log(1, _identity_payload(), _rec(), [({"player_id": "p1"}, 1.0)], 2.0)
    sink.patch_human_pick(1, "p9")
    sink.flush()


def test_tracing_off_when_gate_is_off_is_a_noop() -> None:
    from vorpal.model.tracing import TraceSink

    sink = TraceSink(
        environ={"VORPAL_TRACING": "off", "LANGSMITH_API_KEY": "ls-secret"}
    )
    assert sink.enabled() is False


def test_tracing_off_when_gate_unset_is_a_noop() -> None:
    from vorpal.model.tracing import TraceSink

    sink = TraceSink(environ={"LANGSMITH_API_KEY": "ls-secret"})
    assert sink.enabled() is False


def test_tracing_off_when_langsmith_is_absent(monkeypatch: Any) -> None:
    from vorpal.model.tracing import TraceSink

    monkeypatch.setitem(sys.modules, "langsmith", None)
    sink = TraceSink(environ={"VORPAL_TRACING": "on", "LANGSMITH_API_KEY": "ls-secret"})
    assert sink.enabled() is False


def test_tracing_off_does_not_change_propose() -> None:
    from vorpal.model.tracing import TraceSink

    inner = StubTransport(_valid_sample())
    recorder = SampleRecorder(inner)
    sink = TraceSink(environ={})
    payload = _payload()
    result = propose(payload, recorder)
    samples = recorder.take()
    sink.log(1, payload, result, samples, 3.0)
    assert result.degraded is False
    assert result.proposal.player_id == "4866"
    assert len(inner.calls) == 1
    assert sink.enabled() is False


def test_connect_error_disables_the_sink_and_prints_to_stderr(
    monkeypatch: Any, capsys: Any
) -> None:
    from vorpal.model.tracing import TraceSink

    class Boom:
        def __init__(self) -> None:
            raise RuntimeError("connect refused")

    monkeypatch.setitem(sys.modules, "langsmith", SimpleNamespace(Client=Boom))
    sink = TraceSink(environ={"VORPAL_TRACING": "on", "LANGSMITH_API_KEY": "ls-secret"})
    assert sink.enabled() is False
    assert "connect refused" in capsys.readouterr().err


def test_gate_on_and_key_and_import_enables_the_sink(monkeypatch: Any) -> None:
    from vorpal.model.tracing import TraceSink

    created: list[int] = []

    class FakeClient:
        def __init__(self) -> None:
            created.append(1)

        def create_run(self, *args: Any, **kwargs: Any) -> None:
            return None

        def update_run(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setitem(sys.modules, "langsmith", SimpleNamespace(Client=FakeClient))
    sink = TraceSink(
        environ={
            "VORPAL_TRACING": "true",
            "LANGSMITH_API_KEY": "ls-secret",
            "LANGSMITH_PROJECT": "vorpal-test",
        }
    )
    assert sink.enabled() is True
    assert created == [1]


def test_injected_client_enables_without_env() -> None:
    from vorpal.model.tracing import TraceSink

    sink = TraceSink(client=_RecordingClient(), draft_session="sess")
    assert sink.enabled() is True
    assert sink.draft_session == "sess"


def test_sdk_raise_at_log_does_not_fail_the_call(capsys: Any) -> None:
    from vorpal.model.tracing import TraceSink

    class Boom:
        def create_run(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("langsmith down")

        def update_run(self, *args: Any, **kwargs: Any) -> None:
            return None

    sink = TraceSink(client=Boom(), draft_session="sess")
    result = _rec()
    sink.log(1, _identity_payload(), result, [({"player_id": "p1"}, 1.0)], 2.0)
    sink.flush()
    assert "langsmith down" in capsys.readouterr().err


def test_traced_payload_drops_drafters_keeps_players() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    rec = _rec(player_id="12517", why="we passed Loveland")
    sink.log(
        3,
        _identity_payload(),
        rec,
        [({"player_id": "12517", "why": "we passed Loveland"}, 1.5)],
        4.0,
    )
    sink.flush()
    parent = _parents(client)[0]
    blob = json.dumps({"inputs": parent["inputs"], "outputs": parent["outputs"]})
    assert "league_secret" not in blob
    assert "manager_bob" not in blob
    assert "Colston Loveland" in blob
    assert "12517" in blob
    assert "we passed Loveland" in blob
    payload_in = parent["inputs"]["payload"]
    assert "league_id" not in payload_in
    assert "username" not in payload_in
    assert payload_in["board"][0]["name"] == "Colston Loveland"
    assert payload_in["board"][0]["player_id"] == "12517"


def test_retry_logs_one_parent_with_two_children_and_attempts_2() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    samples = [
        ({"player_id": "ghost"}, 1.0),
        ({"player_id": "p1", "why": "ok"}, 2.0),
    ]
    rec = _rec(attempts=2, player_id="p1")
    sink.log(1, {"board": []}, rec, samples, 3.5)
    sink.flush()
    parents = _parents(client)
    children = _children(client)
    assert len(parents) == 1
    assert len(children) == 2
    assert parents[0]["outputs"]["attempts"] == 2
    assert parents[0]["name"] == "propose"
    assert {child["outputs"]["proposal"]["player_id"] for child in children} == {
        "ghost",
        "p1",
    }
    for child in children:
        assert child["name"] == "complete"
        assert child["outputs"]["model"] == MODEL_ID
        assert child["outputs"]["effort"] == EFFORT
        assert child["parent_run_id"] == parents[0]["id"]
    assert "sess" in parents[0]["tags"]
    assert parents[0]["extra"]["metadata"]["draft_session"] == "sess"


def test_degraded_path_records_flag_and_violation_codes() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    rec = _rec(
        degraded=True,
        attempts=2,
        violations=(
            Violation(
                code="rec_off_board",
                message="player_id ghost is not on the board",
            ),
        ),
        player_id="4866",
    )
    sink.log(
        1,
        {},
        rec,
        [({"player_id": "ghost"}, 1.0), ({"player_id": "ghost"}, 1.2)],
        8.0,
    )
    sink.flush()
    parent = _parents(client)[0]
    assert parent["outputs"]["degraded"] is True
    assert parent["outputs"]["violations"] == [
        {"code": "rec_off_board", "message": "player_id ghost is not on the board"}
    ]
    assert parent["outputs"]["attempts"] == 2
    assert parent["outputs"]["latency_ms"] == 8.0


def test_log_does_not_block_on_the_sink() -> None:
    from vorpal.model.tracing import TraceSink

    started = threading.Event()
    release = threading.Event()
    finished: list[int] = []

    class Blocking:
        def create_run(self, *args: Any, **kwargs: Any) -> None:
            started.set()
            assert release.wait(timeout=5)
            finished.append(1)

        def update_run(self, *args: Any, **kwargs: Any) -> None:
            return None

    sink = TraceSink(client=Blocking(), draft_session="sess")
    returned = threading.Event()

    def call() -> None:
        sink.log(
            1,
            _identity_payload(),
            _rec(),
            [({"player_id": "p1"}, 2.0)],
            5.0,
        )
        returned.set()

    thread = threading.Thread(target=call)
    thread.start()
    assert returned.wait(timeout=1.0), "log blocked on the sink"
    assert started.wait(timeout=1.0)
    assert finished == []
    release.set()
    thread.join(timeout=1.0)
    sink.flush()
    assert finished


def test_patch_human_pick_on_a_down_sink_drops_the_patch(capsys: Any) -> None:
    from vorpal.model.tracing import TraceSink

    class Down:
        def create_run(self, *args: Any, **kwargs: Any) -> None:
            return None

        def update_run(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("patch refused")

    sink = TraceSink(client=Down(), draft_session="sess")
    sink.log(1, {}, _rec(), [({"player_id": "p1"}, 1.0)], 1.0)
    sink.patch_human_pick(1, "p9")
    assert "patch refused" in capsys.readouterr().err


def test_patch_unknown_pick_is_a_noop() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    sink.patch_human_pick(99, "p9")
    assert client.updated == []


def test_patch_human_pick_writes_the_player_id() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    sink.log(4, {"board": []}, _rec(), [({"player_id": "p1"}, 1.0)], 2.0)
    sink.patch_human_pick(4, "p9")
    assert len(client.updated) == 1
    run_id, body = client.updated[0]
    assert run_id == _parents(client)[0]["id"]
    assert body["outputs"]["human_pick"] == "p9"


def test_flush_raise_is_swallowed(capsys: Any) -> None:
    from vorpal.model.tracing import TraceSink

    class Flusher:
        def create_run(self, *args: Any, **kwargs: Any) -> None:
            return None

        def update_run(self, *args: Any, **kwargs: Any) -> None:
            return None

        def flush(self) -> None:
            raise RuntimeError("flush down")

    sink = TraceSink(client=Flusher(), draft_session="sess")
    sink.log(1, {}, _rec(), [({"player_id": "p1"}, 1.0)], 1.0)
    sink.flush()
    assert "flush down" in capsys.readouterr().err


def test_project_defaults_to_vorpal_draft() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, environ={}, draft_session="sess")
    sink.log(1, {}, _rec(), [({"player_id": "p1"}, 1.0)], 1.0)
    sink.flush()
    assert _parents(client)[0]["project_name"] == "vorpal-draft"


def test_project_reads_env() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(
        client=client,
        environ={"LANGSMITH_PROJECT": "custom-draft"},
        draft_session="sess",
    )
    sink.log(1, {}, _rec(), [({"player_id": "p1"}, 1.0)], 1.0)
    sink.flush()
    assert _parents(client)[0]["project_name"] == "custom-draft"


def test_payload_to_dict_is_redacted() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    payload = _payload()
    sink.log(1, payload, _rec(player_id="4866"), [(_valid_sample(), 1.0)], 2.0)
    sink.flush()
    parent = _parents(client)[0]
    board = parent["inputs"]["payload"]["board"]
    assert board[0]["name"] == "Saquon Barkley"
    assert board[0]["player_id"] == "4866"


def test_non_dict_payload_redacts_to_empty() -> None:
    from vorpal.model.tracing import TraceSink

    class Weird:
        def to_dict(self) -> str:
            return "nope"

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    sink.log(1, None, _rec(), [({"player_id": "p1"}, 1.0)], 1.0)
    sink.log(2, Weird(), _rec(), [({"player_id": "p1"}, 1.0)], 1.0)
    sink.flush()
    assert _parents(client)[0]["inputs"]["payload"] == {}
    assert _parents(client)[1]["inputs"]["payload"] == {}


def test_child_keeps_raw_why() -> None:
    from vorpal.model.tracing import TraceSink

    client = _RecordingClient()
    sink = TraceSink(client=client, draft_session="sess")
    raw = {"player_id": "12517", "why": "we passed Loveland"}
    sink.log(1, {}, _rec(), [(raw, 1.0)], 2.0)
    sink.flush()
    child = _children(client)[0]
    assert child["outputs"]["proposal"]["why"] == "we passed Loveland"
    assert child["outputs"]["proposal"] is raw


def test_proposals_seam_times_propose_and_hands_the_call_to_the_collector() -> None:
    from vorpal.cli import _Proposals

    class Collector:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def record_call(
            self,
            pick_no: int,
            payload: Any,
            recommendation: Recommendation,
            samples: list[tuple[dict[str, Any], float]],
            latency_ms: float,
        ) -> None:
            self.calls.append(
                {
                    "latency_ms": latency_ms,
                    "payload": payload,
                    "pick_no": pick_no,
                    "recommendation": recommendation,
                    "samples": samples,
                }
            )

    inner = StubTransport(_valid_sample())
    collector = Collector()
    proposals = _Proposals(SampleRecorder(inner), collector=collector)
    proposal, banners = proposals.for_payload(_payload())
    assert proposal.player_id == "4866"
    assert banners == ()
    assert len(collector.calls) == 1
    call = collector.calls[0]
    assert call["pick_no"] == 1
    assert call["recommendation"].attempts == 1
    assert call["recommendation"].degraded is False
    assert len(call["samples"]) == 1
    assert call["samples"][0][0]["player_id"] == "4866"
    assert call["latency_ms"] >= 0.0
