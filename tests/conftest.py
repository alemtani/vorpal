"""Import the package so coverage always sees `vorpal`."""

import pytest

import vorpal as _vorpal

__all__ = ["_vorpal"]


@pytest.fixture(autouse=True)
def _no_live_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stray key in the shell must not fire a live sink during tests."""

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
