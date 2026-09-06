"""Import the package so coverage always sees `vorpal`."""

import pytest

import vorpal as _vorpal

__all__ = ["_vorpal"]


@pytest.fixture(autouse=True)
def _no_live_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stray key in the shell must not fire a live sink during tests."""

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_live_github(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test must never file a real issue.

    `finish` opens a GitHub issue on any completed draft that has a skip. A
    test that does not inject an opener falls through to `gh issue create`,
    and a local run filed one issue per pytest invocation. The opener is
    injected everywhere it matters; this is the backstop.
    """

    def refuse(title: str, body: str) -> str:
        raise AssertionError("gh issue create ran under pytest")

    monkeypatch.setattr("vorpal.cli.gh_issue_create", refuse)
