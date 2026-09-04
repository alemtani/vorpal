"""The rehearsal harness must pass the operator's flags through to the CLI.

A flag the harness cannot forward is a flag the dress rehearsal cannot cover.
These tests never call a model, a host, or a clock: `main` and the transport
are fakes, and the report goes to a temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals import rehearse


class _FakeTransport:
    def __init__(self, *, fast: bool = False) -> None:
        self.fast = fast


class _FakeClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def close(self) -> None:
        return None


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    """Run `main_argv` with no network. Records what the CLI would have seen."""

    seen: dict = {}

    def fake_main(argv, **kwargs) -> int:
        seen["argv"] = list(argv)
        seen["transport"] = kwargs.get("transport")
        return 0

    def fake_transport(**kwargs) -> _FakeTransport:
        seen["transport_kwargs"] = dict(kwargs)
        return _FakeTransport(**kwargs)

    monkeypatch.setattr(rehearse, "main", fake_main)
    monkeypatch.setattr(rehearse, "AnthropicTransport", fake_transport)
    monkeypatch.setattr(rehearse, "SleeperClient", _FakeClient)
    monkeypatch.setattr(rehearse, "OUT_DIR", tmp_path)
    seen["out_dir"] = tmp_path
    return seen


BASE = ["--draft-id", "draft_1", "--operator", "operator_1"]


def test_defaults_forward_none_of_the_new_flags(harness: dict) -> None:
    assert rehearse.main_argv(BASE) == 0
    argv = harness["argv"]
    assert "--fast" not in argv
    assert "--trace" not in argv
    assert "--scoring" not in argv
    assert harness["transport_kwargs"] == {"fast": False}


def test_fast_reaches_both_the_cli_and_the_transport(harness: dict) -> None:
    assert rehearse.main_argv([*BASE, "--fast"]) == 0
    assert "--fast" in harness["argv"]
    assert harness["transport_kwargs"] == {"fast": True}


def test_fast_transport_stays_wrapped_for_timing(harness: dict) -> None:
    rehearse.main_argv([*BASE, "--fast"])
    transport = harness["transport"]
    assert isinstance(transport, rehearse.TimedTransport)
    assert transport.inner.fast is True


def test_trace_reaches_the_cli(harness: dict) -> None:
    rehearse.main_argv([*BASE, "--trace"])
    assert "--trace" in harness["argv"]


def test_scoring_preset_reaches_the_cli(harness: dict) -> None:
    rehearse.main_argv([*BASE, "--scoring", "ppr"])
    argv = harness["argv"]
    assert argv[argv.index("--scoring") + 1] == "ppr"
    assert "--scoring-league-id" not in argv


def test_scoring_preset_choices_match_the_cli(harness: dict) -> None:
    with pytest.raises(SystemExit) as exc:
        rehearse.main_argv([*BASE, "--scoring", "not_a_preset"])
    assert exc.value.code == 2


def test_scoring_preset_and_league_id_are_mutually_exclusive(harness: dict) -> None:
    with pytest.raises(SystemExit) as exc:
        rehearse.main_argv(
            [*BASE, "--scoring", "ppr", "--scoring-league-id", "league_1"]
        )
    assert exc.value.code == 2


def test_scoring_league_id_still_reaches_the_cli(harness: dict) -> None:
    rehearse.main_argv([*BASE, "--scoring-league-id", "league_1"])
    argv = harness["argv"]
    assert argv[argv.index("--scoring-league-id") + 1] == "league_1"


def test_report_never_records_a_league_id(harness: dict) -> None:
    rehearse.main_argv([*BASE, "--scoring-league-id", "league_1"])
    report = (harness["out_dir"] / "events.json").read_text()
    assert "league_1" not in report
    assert json.loads(report)[-1]["kind"] == "done"
