"""One closed-world model call per board change. No tools. No temperature."""

from __future__ import annotations

import json
from typing import Any, Protocol

from anthropic import Anthropic

from vorpal.contracts import Flag, Payload, Proposal, Slot
from vorpal.errors import PlatformError
from vorpal.model.validate import validate_proposal

# claude-api skill current-models table (cached 2026-06-24): use this exact id.
MODEL_ID = "claude-opus-5"

SYSTEM = (
    "You recommend one pick from this draft board. The board is the world: "
    "player_id and every alternative must be a player_id on board. "
    "hint_argmax_vols is a calculator, not the answer. If you pick someone "
    "else you must set VOLS_DISSENT. If you are not the best available ECR "
    "you must set ECR_DISAGREE. Do not pick beyond ecr_best + margin "
    "(teams in the first half of the draft, two times teams after). "
    "The board is capped; do not read scarcity from its length. "
    "Wait versus take is yours. coin_flip is true only when two picks are "
    "genuinely interchangeable. flags is a closed set: "
    + ", ".join(flag.value for flag in Flag)
    + "."
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


class Transport(Protocol):
    """One request, one JSON object. Unit tests inject a stub."""

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the raw proposal object for this payload."""


class StubTransport:
    """Recorded response. Never touches the network."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        return dict(self._response)


class AnthropicTransport:
    """Claude Messages API. Do not pass temperature or tools."""

    def __init__(self, client: Anthropic | None = None) -> None:
        self._client = client if client is not None else Anthropic()

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.messages.create(
                model=MODEL_ID,
                max_tokens=4096,
                system=SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(payload, sort_keys=True),
                    }
                ],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": PROPOSAL_JSON_SCHEMA,
                    }
                },
            )
        except Exception as exc:
            raise PlatformError(f"model call failed: {exc}") from exc
        if getattr(response, "stop_reason", None) == "refusal":
            raise PlatformError("model refusal")
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


def recommend(payload: Payload, transport: Transport) -> Proposal:
    """One call. Validate before the proposal is returned."""
    return validate_proposal(payload, transport.complete(payload.to_dict()))


def run_stability(
    payload: Payload, transport: Transport
) -> tuple[Proposal, ...] | None:
    """Five identical payloads. coin_flip true skips the rest. Eval run only."""
    first = recommend(payload, transport)
    if first.coin_flip:
        return None
    rest = tuple(recommend(payload, transport) for _ in range(4))
    return (first, *rest)
