"""SampleRecorder buffers samples and per-call latency. No live call."""

from __future__ import annotations

from typing import Any


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
