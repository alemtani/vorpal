"""Trace plumbing for the draft-night ``propose`` call.

``SampleRecorder`` is a ``Transport`` wrapper. It buffers each raw sample and
its per-call latency, then hands the pairs back at ``take``. It imports no
sink and talks to no network. ``propose`` cannot tell it from the real
transport.

``TraceSink`` is the LangSmith emitter. Construction reads the gate once.
When tracing is off, every method is a no-op. ``log`` returns immediately
and submits on a background thread.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from vorpal.contracts import IDENTITY_KEYS, Recommendation
from vorpal.model.call import EFFORT, MODEL_ID

# Drafter and league identity. Player-name keys stay: a trace is human-read.
TRACE_DROP = IDENTITY_KEYS - {"name", "first_name", "last_name"}
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_DEFAULT_PROJECT = "vorpal-draft"
_JOIN_TIMEOUT_S = 2.0


def _gate_on(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def _load_langsmith_client() -> Any:
    from langsmith import Client

    return Client()


def trace_redact(value: object) -> object:
    """Drop drafter identity. Keep player names and ids."""

    if isinstance(value, dict):
        return {
            key: trace_redact(item)
            for key, item in value.items()
            if key not in TRACE_DROP
        }
    if isinstance(value, list):
        return [trace_redact(item) for item in value]
    return value


def _payload_dict(payload: Any) -> dict[str, Any]:
    blob = payload.to_dict() if hasattr(payload, "to_dict") else payload
    return blob if isinstance(blob, dict) else {}


class SampleRecorder:
    """Wraps a transport. Records ``(sample, latency_ms)`` per ``complete``.

    The inner transport is the one that talks (or a stub). The response is
    returned unchanged, so a caller sees the raw sample and nothing else.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._samples: list[tuple[dict[str, Any], float]] = []

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = time.perf_counter()
        raw = dict(self._inner.complete(payload))
        latency_ms = (time.perf_counter() - start) * 1000.0
        self._samples.append((raw, latency_ms))
        return raw

    def take(self) -> list[tuple[dict[str, Any], float]]:
        """Return and clear the buffered ``(sample, latency_ms)`` pairs."""

        samples = self._samples
        self._samples = []
        return samples


class TraceSink:
    """LangSmith emitter for one draft-night process.

    ``enabled()`` is true only when ``VORPAL_TRACING`` is on, a key is set,
    and ``langsmith`` imports — unless a client is injected (tests).
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        draft_session: str | None = None,
    ) -> None:
        env = os.environ if environ is None else environ
        self.draft_session = draft_session or uuid.uuid4().hex
        project = env.get("LANGSMITH_PROJECT")
        self._project = project or _DEFAULT_PROJECT
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._run_ids: dict[int, uuid.UUID] = {}
        self._outputs: dict[int, dict[str, Any]] = {}
        self._client: Any | None = None
        self._enabled = False
        if client is not None:
            self._client = client
            self._enabled = True
            return
        if not _gate_on(env.get("VORPAL_TRACING")):
            return
        key = env.get("LANGSMITH_API_KEY")
        if not (key or "").strip():
            return
        try:
            self._client = _load_langsmith_client()
            self._enabled = True
        except Exception as exc:
            print(f"langsmith: {exc}", file=sys.stderr)

    def enabled(self) -> bool:
        return self._enabled

    def log(
        self,
        pick_no: int,
        payload: Any,
        recommendation: Recommendation,
        samples: Sequence[tuple[dict[str, Any], float]],
        latency_ms: float,
    ) -> None:
        if not self._enabled or self._client is None:
            return
        parent_id = uuid.uuid4()
        outputs = {
            "attempts": recommendation.attempts,
            "degraded": recommendation.degraded,
            "latency_ms": latency_ms,
            "proposal": trace_redact(recommendation.proposal.to_dict()),
            "violations": [
                {"code": item.code, "message": item.message}
                for item in recommendation.violations
            ],
        }
        with self._lock:
            self._run_ids[pick_no] = parent_id
            self._outputs[pick_no] = outputs
        payload_blob = dict(_payload_dict(payload))
        sample_pairs = list(samples)
        thread = threading.Thread(
            target=self._submit,
            args=(pick_no, parent_id, payload_blob, outputs, sample_pairs),
            daemon=True,
        )
        with self._lock:
            self._threads.append(thread)
        thread.start()

    def _submit(
        self,
        pick_no: int,
        parent_id: uuid.UUID,
        payload: dict[str, Any],
        outputs: dict[str, Any],
        samples: list[tuple[dict[str, Any], float]],
    ) -> None:
        try:
            self._client.create_run(
                name="propose",
                inputs={"payload": trace_redact(payload), "pick_no": pick_no},
                run_type="chain",
                extra={
                    "metadata": {
                        "draft_session": self.draft_session,
                        "pick_no": pick_no,
                    }
                },
                id=parent_id,
                outputs=outputs,
                project_name=self._project,
                tags=[self.draft_session],
            )
            for index, (sample, child_latency) in enumerate(samples):
                self._client.create_run(
                    name="complete",
                    inputs={"attempt": index + 1},
                    run_type="llm",
                    extra={"metadata": {"draft_session": self.draft_session}},
                    id=uuid.uuid4(),
                    outputs={
                        "effort": EFFORT,
                        "latency_ms": child_latency,
                        "model": MODEL_ID,
                        "proposal": sample,
                    },
                    parent_run_id=parent_id,
                    project_name=self._project,
                    tags=[self.draft_session],
                )
        except Exception as exc:
            print(f"langsmith: {exc}", file=sys.stderr)

    def flush(self) -> None:
        if not self._enabled:
            return
        try:
            with self._lock:
                threads = list(self._threads)
            for thread in threads:
                thread.join(timeout=_JOIN_TIMEOUT_S)
            with self._lock:
                self._threads = [
                    thread for thread in self._threads if thread.is_alive()
                ]
            flush = getattr(self._client, "flush", None)
            if flush is not None:
                flush()
        except Exception as exc:
            print(f"langsmith: {exc}", file=sys.stderr)

    def patch_human_pick(self, pick_no: int, human_pick: str) -> None:
        if not self._enabled or self._client is None:
            return
        try:
            self.flush()
            with self._lock:
                run_id = self._run_ids.get(pick_no)
                outputs = dict(self._outputs.get(pick_no, {}))
            if run_id is None:
                return
            outputs["human_pick"] = human_pick
            self._client.update_run(run_id, outputs=outputs)
        except Exception as exc:
            print(f"langsmith: {exc}", file=sys.stderr)
