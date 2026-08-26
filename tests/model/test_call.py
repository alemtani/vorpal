"""Model call uses stub transport. No live network in the default run."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vorpal.contracts import (
    AdpVariant,
    Banner,
    BoardRow,
    DraftState,
    Flag,
    LeagueConfig,
    Need,
    Payload,
    RecentPick,
    Replacement,
    Slot,
)
from vorpal.errors import PlatformError
from vorpal.model import (
    MODEL_ID,
    AnthropicTransport,
    StubTransport,
    recommend,
    run_stability,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "recorded_proposal.json"


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
            pick_no=48,
            user_roster=(),
            needs={"RB": Need(filled=0, required=1)},
            weekly=(),
            recent=(RecentPick(player_id="x", position="WR", pick_no=47),),
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


def _recorded() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_recommend_uses_the_stub_and_recorded_response() -> None:
    proposal = recommend(_payload(), StubTransport(_recorded()))
    assert proposal.player_id == "4866"
    assert Flag.EMPTY_STARTER in proposal.flags


def test_recommend_sends_the_serialised_payload_once() -> None:
    transport = StubTransport(_recorded())
    payload = _payload()
    recommend(payload, transport)
    assert transport.calls == [payload.to_dict()]


def test_stability_sends_five_identical_payloads() -> None:
    transport = StubTransport(_recorded())
    payload = _payload()
    results = run_stability(payload, transport)
    assert results is not None
    assert len(results) == 5
    assert len(transport.calls) == 5
    assert all(call == payload.to_dict() for call in transport.calls)
    assert {item.player_id for item in results} == {"4866"}


def test_stability_skips_when_coin_flip_is_true() -> None:
    raw = {**_recorded(), "coin_flip": True}
    transport = StubTransport(raw)
    results = run_stability(_payload(), transport)
    assert results is None
    assert len(transport.calls) == 1


def test_model_id_matches_the_claude_api_skill() -> None:
    assert MODEL_ID == "claude-opus-5"


def test_anthropic_transport_does_not_set_temperature_or_tools() -> None:
    recorded = _recorded()
    captured: dict = {}

    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            text = json.dumps(recorded)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=text)],
                stop_reason="end_turn",
            )

    client = SimpleNamespace(messages=_Messages())
    transport = AnthropicTransport(client=client)
    out = transport.complete(_payload().to_dict())
    assert out == recorded
    assert captured["model"] == MODEL_ID
    assert "temperature" not in captured
    assert "tools" not in captured
    assert captured.get("tools") is None
    assert "output_config" in captured


def test_anthropic_transport_wraps_api_errors() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> None:
            raise RuntimeError("network down")

    transport = AnthropicTransport(client=SimpleNamespace(messages=_Messages()))
    with pytest.raises(PlatformError, match="network down"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_a_refusal_stop() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="no")],
                stop_reason="refusal",
            )

    transport = AnthropicTransport(client=SimpleNamespace(messages=_Messages()))
    with pytest.raises(PlatformError, match="refusal"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_a_response_with_no_text() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="thinking", text="")],
                stop_reason="end_turn",
            )

    transport = AnthropicTransport(client=SimpleNamespace(messages=_Messages()))
    with pytest.raises(PlatformError, match="no text"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_a_non_object_json_body() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="[1]")],
                stop_reason="end_turn",
            )

    transport = AnthropicTransport(client=SimpleNamespace(messages=_Messages()))
    with pytest.raises(PlatformError, match="object"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_unparseable_json() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="not json")],
                stop_reason="end_turn",
            )

    transport = AnthropicTransport(client=SimpleNamespace(messages=_Messages()))
    with pytest.raises(PlatformError, match="JSON"):
        transport.complete(_payload().to_dict())


def test_default_anthropic_client_is_constructed_when_none_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _recorded()
    captured: dict = {}

    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(recorded))],
                stop_reason="end_turn",
            )

    fake = SimpleNamespace(messages=_Messages())
    monkeypatch.setattr("vorpal.model.call.Anthropic", lambda: fake)
    transport = AnthropicTransport()
    assert transport.complete(_payload().to_dict()) == recorded
    assert captured["model"] == MODEL_ID
