"""Trace plumbing for the draft-night ``propose`` call.

``SampleRecorder`` is a ``Transport`` wrapper. It buffers each raw sample and
its per-call latency, then hands the pairs back at ``take``. It imports no
sink and talks to no network. ``propose`` cannot tell it from the real
transport. The LangSmith sink is a separate piece (see the tracing spec) and
does not live here yet.
"""

from __future__ import annotations

import time
from typing import Any


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
