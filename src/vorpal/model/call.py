"""One closed-world model call per board change, plus one `detail` round trip.

The board ships lean. The model calls `detail(player_ids)` for the players it is
deciding between, and the transport answers once from the same board — a pure
function of the payload, so stability survives. No temperature. See SPEC.md §4.
"""

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
from vorpal.model.detail import lean_view, resolve_detail
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

# Fast mode: same model, same effort, ~2.5x output tokens/second at premium
# pricing. The pick clock is 30s and adaptive thinking eats most of it, so the
# operator needs the rec sooner, not cheaper. It is a delivery setting, not part
# of the answer, so it stays out of `build_request` and out of the cassette key
# (toggling it never invalidates a recording). Fast mode needs the beta
# endpoint and a top-level `speed`, and is Claude API only.
FAST_MODE_BETA = "fast-mode-2026-02-01"

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
    + ". When you set VOLS_DISSENT, name hint_argmax_vols's player once in why "
    'as "<player> is the VOLS pick", then say why you pass. When you set '
    'ECR_DISAGREE, name ecr_best\'s player once as "<player> is the ECR pick", '
    "then say why you pass. Write each label one time. Do not repeat the "
    "phrase or restate the pick you passed on. "
    "The board is lean. Call detail(player_ids) once for the players you are "
    "deciding between to read delta_starter_points, the ECR spread "
    "(ecr_min/max/std), gp, points, and bye. Batch every id into that one call. "
    "Ids must be on the board."
)

# `detail` is the one tool. A pure function of the board: it returns columns the
# payload already holds for ids already on it. SPEC.md §4 admits this kind at
# draft; a changing-world tool (news, search) stays refused.
DETAIL_TOOL: dict[str, Any] = {
    "name": "detail",
    "description": (
        "Heavier per-player columns for the players you are deciding between: "
        "delta_starter_points, the ECR spread (ecr_min/max/std), gp, points, "
        "bye. Batch every id into one call. Ids must be on the board."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "player_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["player_ids"],
        "additionalProperties": False,
    },
}

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
    """The first Messages request for this payload, as a plain dict.

    The message carries the **lean** board — what the model reads first. The
    `detail` columns ride behind the tool, so they are not here; the cassette
    key folds the full payload back in (see `cassette.request_key`) so identity
    still covers what the tool can surface. Transport settings (retries,
    deadlines, fast mode) are not here: they cannot change the answer.
    """
    return {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "thinking": {"type": "adaptive"},
        "tools": [DETAIL_TOOL],
        "messages": [
            {"role": "user", "content": json.dumps(lean_view(payload), sort_keys=True)}
        ],
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
    """Claude Messages API. One tool: `detail`. No temperature.

    The model may call `detail` for its shortlist. The transport answers once
    from the same board, then re-asks with the tool removed so the next turn is
    the proposal — one round trip, per SPEC.md §4. Worst case is two model turns;
    most picks are one.

    ``fast`` opts into fast mode: quicker rec, premium rate. It is off by
    default so no path bills the premium unasked. The CLI turns it on with
    ``--fast`` for a short mock clock.
    """

    def __init__(self, client: Anthropic | None = None, *, fast: bool = False) -> None:
        self._client = client if client is not None else Anthropic()
        self._fast = fast

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = build_request(payload)
        messages = list(base["messages"])
        offer_tools = True
        while True:
            request = {**base, "messages": messages}
            if not offer_tools:
                request.pop("tools", None)
            response = self._create(request)
            self._check_stop(response)
            if offer_tools and getattr(response, "stop_reason", None) == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {"role": "user", "content": self._answer_tools(response, payload)}
                )
                offer_tools = False  # one detail round trip, then finalize
                continue
            return self._read_proposal(response)

    def _create(self, request: dict[str, Any]) -> Any:
        """One Messages call, fast or standard. Wraps transport faults."""
        try:
            if self._fast:
                return self._client.beta.messages.create(
                    **request, betas=[FAST_MODE_BETA], speed="fast"
                )
            return self._client.messages.create(**request)
        except Exception as exc:
            raise PlatformError(f"model call failed: {exc}") from exc

    @staticmethod
    def _check_stop(response: Any) -> None:
        """A refusal or a truncation is the host failing, not a proposal."""
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            raise PlatformError("model refusal")
        if stop_reason == "max_tokens":
            raise PlatformError(
                f"model response hit max_tokens ({MAX_TOKENS}); raise the cap"
            )

    @staticmethod
    def _answer_tools(response: Any, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """One `tool_result` per `tool_use` block. `detail` is answered from the
        board; any other tool gets an error result so the turn can still close.
        """
        results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == "detail":
                ids = block.input.get("player_ids", [])
                content = json.dumps(resolve_detail(payload, ids), sort_keys=True)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                    }
                )
            else:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"unknown tool: {block.name}",
                        "is_error": True,
                    }
                )
        return results

    @staticmethod
    def _read_proposal(response: Any) -> dict[str, Any]:
        """The terminal turn: one text block, the schema-constrained proposal."""
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
