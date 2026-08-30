"""Cassettes: record once, replay by request hash. No tokens spent here.

Three tiers. The key is pure, the store is local IO, and the transport is
a contract. The last tier drives the real `recommend` / `run_stability`
through the layer, because a key built from a request nobody sends is a
key that misses forever, and stubbing both sides would only prove the
layer agrees with itself.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from vorpal.contracts import (
    Banner,
    BoardRow,
    DraftState,
    LeagueConfig,
    Need,
    Payload,
    Replacement,
    Slot,
)
from vorpal.errors import PlatformError
from vorpal.model import (
    AnthropicTransport,
    CassetteStore,
    CassetteTransport,
    StubTransport,
    build_request,
    recommend,
    request_key,
    run_stability,
)
from vorpal.model import call as call_module

RECORDED = {
    "player_id": "4866",
    "alternatives": ["7564"],
    "slot_filled": "RB",
    "coin_flip": False,
    "why": "highest VOLS and fills an empty RB starter",
    "flags": [],
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
        ),
        state=DraftState(
            pick_no=48,
            user_roster=(),
            needs={"RB": Need(filled=0, required=1)},
            weekly=(),
            recent=(),
            next_user_pick=49,
            picks_until_next=1,
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


def _store(tmp_path: Path) -> CassetteStore:
    return CassetteStore(tmp_path / "cassettes")


# --- the key: pure ---------------------------------------------------------


def test_key_is_stable_for_the_same_payload() -> None:
    body = _payload().to_dict()
    assert request_key(body) == request_key(dict(body))


def test_key_is_a_full_sha256() -> None:
    key = request_key(_payload().to_dict())
    assert len(key) == 64
    assert set(key) <= set("0123456789abcdef")


def test_a_different_board_is_a_different_key() -> None:
    body = _payload().to_dict()
    other = _payload().to_dict()
    other["board"][0]["vols"] = 41.0
    assert request_key(body) != request_key(other)


@pytest.mark.parametrize(
    "attr, value",
    [
        ("MODEL_ID", "claude-sonnet-5"),
        ("SYSTEM", "a different system prompt"),
        ("EFFORT", "high"),
        ("MAX_TOKENS", 8000),
    ],
)
def test_every_request_setting_that_can_change_the_answer_changes_the_key(
    monkeypatch: pytest.MonkeyPatch, attr: str, value: object
) -> None:
    body = _payload().to_dict()
    before = request_key(body)
    monkeypatch.setattr(call_module, attr, value)
    assert request_key(body) != before


def test_the_output_schema_is_in_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two schemas are two questions, even on the same board."""
    body = _payload().to_dict()
    before = request_key(body)
    schema = {**call_module.PROPOSAL_JSON_SCHEMA}
    schema["properties"] = {
        **schema["properties"],
        "why": {"type": "string", "description": "one sentence"},
    }
    monkeypatch.setattr(call_module, "PROPOSAL_JSON_SCHEMA", schema)
    assert request_key(body) != before


def test_the_key_hashes_the_request_the_transport_actually_sends() -> None:
    """`build_request` is the one assembler, so the key cannot drift from it."""
    body = _payload().to_dict()
    captured: dict = {}

    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=json.dumps(RECORDED))],
            )

    AnthropicTransport(SimpleNamespace(messages=_Messages())).complete(body)
    assert captured == build_request(body)
    assert captured["messages"][0]["content"] == json.dumps(body, sort_keys=True)


def test_an_unserializable_payload_raises_rather_than_hashing_around_it() -> None:
    with pytest.raises(PlatformError, match="not serializable"):
        request_key({"board": object()})


# --- the store: local IO ---------------------------------------------------


def test_load_returns_none_when_never_recorded(tmp_path: Path) -> None:
    assert _store(tmp_path).load("deadbeef") is None


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    body = _payload().to_dict()
    store.save("k1", [RECORDED], payload=body)
    assert store.load("k1") == [RECORDED]


def test_the_file_is_diffable(tmp_path: Path) -> None:
    """Cassettes are read in review: sorted, indented, one trailing newline."""
    store = _store(tmp_path)
    store.save("k1", [RECORDED], payload=_payload().to_dict())
    text = store.path("k1").read_text()
    assert text.endswith("}\n")
    assert "\n  " in text
    body = json.loads(text)
    assert list(body) == sorted(body)


def test_the_file_holds_the_request_beside_the_answers(tmp_path: Path) -> None:
    """A key says nothing to a reader. The request is what makes it legible."""
    store = _store(tmp_path)
    payload = _payload().to_dict()
    store.save("k1", [RECORDED], payload=payload)
    body = json.loads(store.path("k1").read_text())
    assert body["request"] == build_request(payload)
    assert body["model"] == call_module.MODEL_ID
    assert body["key"] == "k1"


def test_a_corrupt_cassette_is_an_error_not_a_miss(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.root.mkdir(parents=True)
    store.path("k1").write_text("{not json")
    with pytest.raises(PlatformError, match="not JSON"):
        store.load("k1")


def test_a_cassette_without_samples_is_an_error(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.root.mkdir(parents=True)
    store.path("k1").write_text('{"key": "k1"}')
    with pytest.raises(PlatformError, match="no samples list"):
        store.load("k1")


# --- the transport: contract ----------------------------------------------


def test_replay_returns_the_recorded_answer(tmp_path: Path) -> None:
    store = _store(tmp_path)
    body = _payload().to_dict()
    store.save(request_key(body), [RECORDED], payload=body)
    assert CassetteTransport(store).complete(body) == RECORDED


def test_a_miss_is_an_error_and_names_the_key(tmp_path: Path) -> None:
    """A quiet live call on a miss is how an eval suite becomes a bill."""
    body = _payload().to_dict()
    with pytest.raises(PlatformError) as excinfo:
        CassetteTransport(_store(tmp_path)).complete(body)
    assert request_key(body)[:16] in excinfo.value.message
    assert "--record" in excinfo.value.message


def test_a_miss_never_reaches_the_live_transport(tmp_path: Path) -> None:
    live = StubTransport(RECORDED)
    transport = CassetteTransport(_store(tmp_path), live=live, record=False)
    with pytest.raises(PlatformError):
        transport.complete(_payload().to_dict())
    assert live.calls == []


def test_samples_are_walked_in_order(tmp_path: Path) -> None:
    store = _store(tmp_path)
    body = _payload().to_dict()
    draws = [{**RECORDED, "why": f"draw {i}"} for i in range(3)]
    store.save(request_key(body), draws, payload=body)
    transport = CassetteTransport(store)
    assert [transport.complete(body)["why"] for _ in range(3)] == [
        "draw 0",
        "draw 1",
        "draw 2",
    ]


def test_running_past_the_recorded_samples_is_an_error(tmp_path: Path) -> None:
    """Never wrap. Draw one five times is a spread that was never measured."""
    store = _store(tmp_path)
    body = _payload().to_dict()
    store.save(request_key(body), [RECORDED], payload=body)
    transport = CassetteTransport(store)
    transport.complete(body)
    with pytest.raises(PlatformError, match="has 1 sample"):
        transport.complete(body)


def test_two_payloads_do_not_share_a_cursor(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _payload().to_dict()
    second = _payload().to_dict()
    second["state"]["pick_no"] = 49
    store.save(request_key(first), [{**RECORDED, "why": "first"}], payload=first)
    store.save(request_key(second), [{**RECORDED, "why": "second"}], payload=second)
    transport = CassetteTransport(store)
    assert transport.complete(first)["why"] == "first"
    assert transport.complete(second)["why"] == "second"


def test_record_is_the_only_path_that_spends(tmp_path: Path) -> None:
    store = _store(tmp_path)
    body = _payload().to_dict()
    live = StubTransport(RECORDED)
    transport = CassetteTransport(store, live=live, record=True)
    assert transport.complete(body) == RECORDED
    assert len(live.calls) == 1
    assert store.load(request_key(body)) == [RECORDED]


def test_record_writes_after_every_call(tmp_path: Path) -> None:
    """A crash keeps what it paid for."""
    store = _store(tmp_path)
    body = _payload().to_dict()
    live = StubTransport([{**RECORDED, "why": f"draw {i}"} for i in range(3)])
    transport = CassetteTransport(store, live=live, record=True)
    for expected in range(1, 4):
        transport.complete(body)
        assert len(store.load(request_key(body)) or []) == expected


def test_record_tops_a_partial_key_up(tmp_path: Path) -> None:
    """A full key costs nothing even under record."""
    store = _store(tmp_path)
    body = _payload().to_dict()
    store.save(request_key(body), [{**RECORDED, "why": "old"}], payload=body)
    live = StubTransport({**RECORDED, "why": "new"})
    transport = CassetteTransport(store, live=live, record=True)
    assert transport.complete(body)["why"] == "old"
    assert live.calls == []
    assert transport.complete(body)["why"] == "new"
    assert len(live.calls) == 1


def test_record_without_a_live_transport_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PlatformError, match="needs a live transport"):
        CassetteTransport(_store(tmp_path), record=True)


def test_a_replayed_sample_cannot_be_mutated_by_the_caller(tmp_path: Path) -> None:
    store = _store(tmp_path)
    body = _payload().to_dict()
    store.save(request_key(body), [RECORDED], payload=body)
    transport = CassetteTransport(store)
    transport.complete(body)["player_id"] = "tampered"
    assert (store.load(request_key(body)) or [])[0]["player_id"] == "4866"


# --- the real eval path through the layer ---------------------------------


def test_recommend_replays_from_a_cassette_it_recorded(tmp_path: Path) -> None:
    """Record with the eval path, replay with the eval path. Same key."""
    store = _store(tmp_path)
    payload = _payload()
    live = StubTransport(RECORDED)
    assert recommend(payload, CassetteTransport(store, live=live, record=True))

    replay = CassetteTransport(store)
    assert recommend(payload, replay).player_id == "4866"
    assert len(live.calls) == 1


def test_run_stability_records_five_draws_and_replays_five(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _payload()
    draws = [{**RECORDED, "why": f"draw {i}"} for i in range(5)]
    live = StubTransport(draws)
    assert run_stability(payload, CassetteTransport(store, live=live, record=True))
    assert len(live.calls) == 5
    assert len(store.load(request_key(payload.to_dict())) or []) == 5

    replayed = run_stability(payload, CassetteTransport(store))
    assert replayed is not None
    assert [item.why for item in replayed] == [f"draw {i}" for i in range(5)]


def test_a_coin_flip_run_records_one_draw_and_replays_one(tmp_path: Path) -> None:
    """`run_stability` short-circuits, so the key holds one sample, not five."""
    store = _store(tmp_path)
    payload = _payload()
    live = StubTransport({**RECORDED, "coin_flip": True})
    assert (
        run_stability(payload, CassetteTransport(store, live=live, record=True)) is None
    )
    assert len(live.calls) == 1
    assert len(store.load(request_key(payload.to_dict())) or []) == 1
    assert run_stability(payload, CassetteTransport(store)) is None


def test_a_stale_cassette_stops_the_run(tmp_path: Path) -> None:
    """Edit the board, change the key. The old recording does not answer."""
    store = _store(tmp_path)
    payload = _payload()
    live = StubTransport(RECORDED)
    recommend(payload, CassetteTransport(store, live=live, record=True))

    edited = replace(payload, state=replace(payload.state, pick_no=49))
    with pytest.raises(PlatformError, match="not recorded"):
        recommend(edited, CassetteTransport(store))
