"""Model call uses stub transport. No live network in the default run."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
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
    EFFORT,
    MAX_TOKENS,
    MODEL_ID,
    AnthropicTransport,
    StubTransport,
    propose,
    recommend,
    run_stability,
)
from vorpal.model.call import FAST_MODE_BETA, SYSTEM

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


def test_system_names_the_why_forms_for_dissent_flags() -> None:
    """SPEC.md #20: SYSTEM must spell out the contains-floor form so the
    model has a chance to satisfy it, even though the floor itself is
    checked only in evals, never on the pick clock."""
    assert "hint_argmax_vols" in SYSTEM
    assert "ecr_best" in SYSTEM
    assert "is the VOLS pick" in SYSTEM
    assert "is the ECR pick" in SYSTEM
    # #57: the label is stated once, not as a repeatable header.
    assert "one time" in SYSTEM
    assert "Do not repeat" in SYSTEM


def _capturing_client(recorded: dict, captured: dict) -> SimpleNamespace:
    """A fake client whose beta.messages.create records its kwargs."""

    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(recorded))],
                stop_reason="end_turn",
            )

    client = SimpleNamespace(beta=SimpleNamespace(messages=_Messages()))
    client.with_options = lambda **kwargs: client
    return client


def test_anthropic_transport_does_not_set_temperature_or_tools() -> None:
    recorded = _recorded()
    captured: dict = {}
    transport = AnthropicTransport(
        client=_capturing_client(recorded, captured), fast=True
    )
    out = transport.complete(_payload().to_dict())
    assert out == recorded
    assert captured["model"] == MODEL_ID
    assert "temperature" not in captured
    assert captured.get("tools") is None
    assert "output_config" in captured


def test_anthropic_transport_uses_fast_mode_when_requested() -> None:
    recorded = _recorded()
    captured: dict = {}
    transport = AnthropicTransport(
        client=_capturing_client(recorded, captured), fast=True
    )
    transport.complete(_payload().to_dict())
    assert captured["speed"] == "fast"
    assert captured["betas"] == [FAST_MODE_BETA]


def test_anthropic_transport_is_standard_speed_by_default() -> None:
    recorded = _recorded()
    captured: dict = {}

    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(recorded))],
                stop_reason="end_turn",
            )

    client = SimpleNamespace(messages=_Messages())
    transport = AnthropicTransport(client=client)  # default: standard speed
    assert transport.complete(_payload().to_dict()) == recorded
    assert "speed" not in captured
    assert "betas" not in captured


def test_anthropic_transport_wraps_api_errors() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> None:
            raise RuntimeError("network down")

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
    with pytest.raises(PlatformError, match="network down"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_a_refusal_stop() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="no")],
                stop_reason="refusal",
            )

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
    with pytest.raises(PlatformError, match="refusal"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_a_response_with_no_text() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="thinking", text="")],
                stop_reason="end_turn",
            )

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
    with pytest.raises(PlatformError, match="no text"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_a_non_object_json_body() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="[1]")],
                stop_reason="end_turn",
            )

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
    with pytest.raises(PlatformError, match="object"):
        transport.complete(_payload().to_dict())


def test_anthropic_transport_rejects_unparseable_json() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="not json")],
                stop_reason="end_turn",
            )

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
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


# --- draft night: one retry, then the calculator -------------------------


def test_propose_returns_the_model_pick_when_it_validates() -> None:
    transport = StubTransport(_recorded())
    result = propose(_payload(), transport)
    assert result.degraded is False
    assert result.violations == ()
    assert result.attempts == 1
    assert result.proposal.player_id == "4866"
    assert len(transport.calls) == 1


def test_propose_retries_once_and_keeps_a_valid_second_answer() -> None:
    bad = {**_recorded(), "player_id": "ghost"}
    transport = StubTransport([bad, _recorded()])
    result = propose(_payload(), transport)
    assert result.degraded is False
    assert result.attempts == 2
    assert result.proposal.player_id == "4866"
    assert len(transport.calls) == 2


def test_propose_degrades_to_the_calculator_rather_than_exiting() -> None:
    """The operator is on a pick timer. A violation must never hand back nothing."""
    bad = {**_recorded(), "player_id": "ghost"}
    transport = StubTransport(bad)
    payload = _payload()
    result = propose(payload, transport)
    assert result.degraded is True
    assert result.attempts == 2
    assert result.proposal.player_id == payload.hint_argmax_vols
    assert result.proposal.slot_filled is Slot.RB
    assert result.proposal.coin_flip is False
    assert result.proposal.flags == ()
    assert [v.code for v in result.violations] == ["rec_off_board"]
    assert "rec_off_board" in result.proposal.why


def test_the_degraded_pick_names_alternatives_from_the_board() -> None:
    bad = {**_recorded(), "player_id": "ghost"}
    result = propose(_payload(), StubTransport(bad))
    assert result.proposal.alternatives == ("7564",)


def test_propose_degrades_on_a_semantic_violation_too() -> None:
    """A readable proposal that breaks a rule still degrades, not raises."""
    silent = {**_recorded(), "player_id": "7564", "slot_filled": "WR", "flags": []}
    result = propose(_payload(), StubTransport(silent))
    assert result.degraded is True
    assert [v.code for v in result.violations] == ["silent_vols_dissent"]


def test_propose_does_not_degrade_on_a_why_that_misses_the_contains_floor() -> None:
    """SPEC.md #20: naming the dissent pick in `why` is a §5 eval, never a
    §4 violation. A dissent that flags correctly but writes a `why` with
    no name or id must validate clean and ship in one attempt."""
    unnamed = {
        **_recorded(),
        "player_id": "7564",
        "slot_filled": "WR",
        "flags": ["VOLS_DISSENT"],
        "why": "better long-term value",
    }
    transport = StubTransport(unnamed)
    result = propose(_payload(), transport)
    assert result.degraded is False
    assert result.violations == ()
    assert result.attempts == 1
    assert result.proposal.player_id == "7564"
    assert len(transport.calls) == 1


# --- eval run: a violation is the score, never a retry -------------------


def test_recommend_raises_on_a_violation_so_evals_can_count_it() -> None:
    silent = {**_recorded(), "player_id": "7564", "slot_filled": "WR", "flags": []}
    transport = StubTransport(silent)
    with pytest.raises(PlatformError, match="silent_vols_dissent"):
        recommend(_payload(), transport)
    assert len(transport.calls) == 1


def test_recommend_raises_on_an_unreadable_response() -> None:
    with pytest.raises(PlatformError, match="did not validate"):
        recommend(_payload(), StubTransport({"player_id": "4866"}))


# --- call parameters -----------------------------------------------------


def test_stub_transport_repeats_a_single_response() -> None:
    transport = StubTransport(_recorded())
    payload = _payload()
    for _ in range(3):
        transport.complete(payload.to_dict())
    assert len(transport.calls) == 3


def test_transport_asks_for_medium_effort_and_adaptive_thinking() -> None:
    captured: dict = {}

    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(_recorded()))],
                stop_reason="end_turn",
            )

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
    transport.complete(_payload().to_dict())
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"]["effort"] == EFFORT
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["max_tokens"] == MAX_TOKENS
    # budget_tokens is a 400 on this model; effort is the depth lever.
    assert "budget_tokens" not in json.dumps(captured["thinking"])


def test_a_truncated_response_says_so_instead_of_bad_json() -> None:
    class _Messages:
        def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"player_id": "48')],
                stop_reason="max_tokens",
            )

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
    with pytest.raises(PlatformError, match="max_tokens"):
        transport.complete(_payload().to_dict())


def _rate_limit_error(message: str) -> anthropic.RateLimitError:
    """A real 429 from the SDK. The fast-mode limit arrives as this class."""
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.RateLimitError(
        message, response=httpx2.Response(429, request=request), body=None
    )


FAST_LIMIT = "rate limit of 0 fast mode input tokens per minute"


def _two_speed_client(
    recorded: dict, calls: list[dict], *, fast_error: Exception
) -> SimpleNamespace:
    """A client whose fast path always fails and whose standard path answers.

    Records one row per call so a test can see which path ran, in order, and
    with which retry setting. `with_options` returns the same object, the way
    the SDK's does for our purposes.
    """

    class _Fast:
        def create(self, **kwargs: object) -> SimpleNamespace:
            calls.append({"speed": kwargs.get("speed"), **kwargs})
            raise fast_error

    class _Standard:
        def create(self, **kwargs: object) -> SimpleNamespace:
            calls.append({"speed": kwargs.get("speed"), **kwargs})
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(recorded))],
                stop_reason="end_turn",
            )

    client = SimpleNamespace(
        beta=SimpleNamespace(messages=_Fast()), messages=_Standard()
    )
    client.options: list[dict] = []

    def with_options(**kwargs: object) -> SimpleNamespace:
        client.options.append(kwargs)
        return client

    client.with_options = with_options
    return client


def test_fast_mode_rate_limit_falls_back_to_standard_speed() -> None:
    """A delivery setting never fails the answer. #76."""
    recorded = _recorded()
    calls: list[dict] = []
    client = _two_speed_client(
        recorded, calls, fast_error=_rate_limit_error(FAST_LIMIT)
    )
    transport = AnthropicTransport(client=client, fast=True)
    assert transport.complete(_payload().to_dict()) == recorded
    assert [call["speed"] for call in calls] == ["fast", None]


def test_fast_mode_fallback_latches_off_for_the_rest_of_the_run() -> None:
    """The org limit is 0. No wait clears it, so do not probe every pick."""
    recorded = _recorded()
    calls: list[dict] = []
    client = _two_speed_client(
        recorded, calls, fast_error=_rate_limit_error(FAST_LIMIT)
    )
    transport = AnthropicTransport(client=client, fast=True)
    for _ in range(3):
        assert transport.complete(_payload().to_dict()) == recorded
    assert [call["speed"] for call in calls] == ["fast", None, None, None]


def test_the_fast_probe_does_not_burn_the_clock_on_sdk_retries() -> None:
    """`retry-after` on a 0 limit would outlast the pick. Fail and fall back."""
    recorded = _recorded()
    calls: list[dict] = []
    client = _two_speed_client(
        recorded, calls, fast_error=_rate_limit_error(FAST_LIMIT)
    )
    AnthropicTransport(client=client, fast=True).complete(_payload().to_dict())
    assert {"max_retries": 0} in client.options


def test_a_standard_speed_rate_limit_still_raises() -> None:
    """Only speed degrades. Standard is the answer path, and it raises."""

    class _Messages:
        def create(self, **kwargs: object) -> None:
            raise _rate_limit_error("rate limit of 40000 input tokens per minute")

    transport = AnthropicTransport(
        client=SimpleNamespace(messages=_Messages()), fast=False
    )
    with pytest.raises(PlatformError, match="40000 input tokens"):
        transport.complete(_payload().to_dict())


def test_a_fast_mode_failure_that_is_not_a_rate_limit_still_raises() -> None:
    """The carve-out is the limit, not every fast-path error."""
    recorded = _recorded()
    calls: list[dict] = []
    client = _two_speed_client(recorded, calls, fast_error=RuntimeError("network down"))
    transport = AnthropicTransport(client=client, fast=True)
    with pytest.raises(PlatformError, match="network down"):
        transport.complete(_payload().to_dict())
