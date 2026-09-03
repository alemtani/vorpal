"""One closed-world model call per board change. No tools. No temperature."""

from __future__ import annotations

import json
from typing import Any, Protocol

from anthropic import Anthropic

from vorpal.contracts import (
    Banner,
    Flag,
    Payload,
    Proposal,
    Recommendation,
    Slot,
    Violation,
)
from vorpal.errors import PlatformError
from vorpal.model.validate import validate_proposal

# claude-api skill current-models table (cached 2026-06-24): use this exact id.
MODEL_ID = "claude-opus-5"

# Thinking is on by default on this model; the explicit adaptive setting says so
# rather than leaving it to a default that differed one generation ago.
# `budget_tokens` is rejected with a 400 here — effort is the depth lever, and
# medium is the pick-clock setting (the default is high).
EFFORT = "medium"

# Thinking tokens count against max_tokens. A capped board plus adaptive
# thinking runs past 4096, and a truncated body reads as bad JSON rather than
# as running out of room.
MAX_TOKENS = 16000

DEGRADED = Banner(
    code="model_degraded",
    message="model proposal did not validate; showing the calculator pick",
)

SYSTEM = (
    "You recommend one pick from this draft board. The board is the world: "
    "player_id and every alternative must be a player_id on board. "
    "hint_argmax_vols is a calculator, not the answer. If you pick someone "
    "else you must set VOLS_DISSENT. If you are not the best available ECR "
    "you must set ECR_DISAGREE, and do not pick beyond ecr_best + margin. "
    "The board is capped; do not read scarcity from its length. "
    "Wait versus take is yours. Set coin_flip when a rerun of this same board "
    "could reasonably name a different player. flags is a closed set: "
    + ", ".join(flag.value for flag in Flag)
    + ". When you set VOLS_DISSENT, why must name hint_argmax_vols's player "
    'by id or name, in the form: "X is the VOLS pick; we are not taking X '
    "because …\". When you set ECR_DISAGREE, why must name ecr_best's player "
    'the same way: "X is the ECR pick; we are not taking X because …".'
)

PROPOSAL_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "player_id": {"type": "string"},
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "slot_filled": {"type": "string", "enum": [slot.value for slot in Slot]},
        "coin_flip": {"type": "boolean"},
        "why": {"type": "string"},
        "flags": {
            "type": "array",
            "items": {"type": "string", "enum": [flag.value for flag in Flag]},
        },
    },
    "required": [
        "player_id",
        "alternatives",
        "slot_filled",
        "coin_flip",
        "why",
        "flags",
    ],
    "additionalProperties": False,
}


def build_request(payload: dict[str, Any]) -> dict[str, Any]:
    """The exact Messages request for this payload, as a plain dict.

    One place assembles the request, so the cassette key can hash the same
    object the transport sends. A key built from a request nobody sends is
    a key that misses forever. Transport settings (retries, deadlines) are
    not here: they cannot change the answer.
    """
    return {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "thinking": {"type": "adaptive"},
        "messages": [{"role": "user", "content": json.dumps(payload, sort_keys=True)}],
        "output_config": {
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": PROPOSAL_JSON_SCHEMA},
        },
    }


class Transport(Protocol):
    """One request, one JSON object. Unit tests inject a stub."""

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the raw proposal object for this payload."""


class StubTransport:
    """Recorded responses. Never touches the network.

    Give one response to repeat, or a list to walk once per call — a list is how
    a test drives the retry path.
    """

    def __init__(self, response: dict[str, Any] | list[dict[str, Any]]) -> None:
        self._responses = (
            [dict(item) for item in response]
            if isinstance(response, list)
            else [dict(response)]
        )
        self.calls: list[dict[str, Any]] = []

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return dict(self._responses[index])


class AnthropicTransport:
    """Claude Messages API. Do not pass temperature or tools."""

    def __init__(self, client: Anthropic | None = None) -> None:
        self._client = client if client is not None else Anthropic()

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.messages.create(**build_request(payload))
        except Exception as exc:
            raise PlatformError(f"model call failed: {exc}") from exc
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            raise PlatformError("model refusal")
        if stop_reason == "max_tokens":
            raise PlatformError(
                f"model response hit max_tokens ({MAX_TOKENS}); raise the cap"
            )
        text = next(
            (
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ),
            None,
        )
        if text is None:
            raise PlatformError("model response has no text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PlatformError(f"model response is not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise PlatformError("model response is not an object")
        return data


def propose(payload: Payload, transport: Transport) -> Recommendation:
    """One call, one retry, then the calculator. What draft night reads.

    A violation never exits: the operator is on a pick timer. A transport
    failure still raises `PlatformError` — that is the host being broken rather
    than the model being wrong.
    """
    attempts = 0
    violations: tuple[Violation, ...] = ()
    for _ in range(2):
        attempts += 1
        proposal, violations = validate_proposal(
            payload, transport.complete(payload.to_dict())
        )
        if proposal is not None and not violations:
            return Recommendation(
                proposal=proposal,
                violations=(),
                degraded=False,
                attempts=attempts,
            )
    return Recommendation(
        proposal=_calculator_pick(payload, violations),
        violations=violations,
        degraded=True,
        attempts=attempts,
    )


def _calculator_pick(payload: Payload, violations: tuple[Violation, ...]) -> Proposal:
    """`hint_argmax_vols` as a proposal. The fallback, not the answer."""
    rec = next(
        row for row in payload.board if row.player_id == payload.hint_argmax_vols
    )
    codes = ", ".join(violation.code for violation in violations)
    return Proposal(
        player_id=rec.player_id,
        alternatives=tuple(
            row.player_id
            for row in payload.board[1:3]
            if row.player_id != rec.player_id
        ),
        slot_filled=rec.legal_slots[0],
        coin_flip=False,
        why=f"{DEGRADED.message} ({codes})",
        flags=(),
    )


def recommend(payload: Payload, transport: Transport) -> Proposal:
    """Strict single call. The eval path: a violation is the score, not a retry."""
    proposal, violations = validate_proposal(
        payload, transport.complete(payload.to_dict())
    )
    if proposal is None or violations:
        codes = ", ".join(violation.code for violation in violations)
        raise PlatformError(f"proposal did not validate: {codes}")
    return proposal


def run_stability(
    payload: Payload, transport: Transport
) -> tuple[Proposal, ...] | None:
    """Five identical payloads. coin_flip true skips the rest. Eval run only."""
    first = recommend(payload, transport)
    if first.coin_flip:
        return None
    rest = tuple(recommend(payload, transport) for _ in range(4))
    return (first, *rest)
