"""Ingest tests use recorded fixtures. No live network."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(*parts: str) -> Any:
    return json.loads(FIXTURES.joinpath(*parts).read_text(encoding="utf-8"))


@pytest.fixture
def projections_payload() -> Any:
    return load_fixture("fantasypros", "projections_week0.json")


@pytest.fixture
def adp_payload() -> Any:
    return load_fixture("fantasypros", "adp_ppr.json")


@pytest.fixture
def host_players() -> Any:
    return load_fixture("sleeper", "players.json")


@pytest.fixture(autouse=True)
def clear_ingest_caches() -> Iterator[None]:
    try:
        from vorpal.ingest import clear_caches
    except ImportError:
        yield
        return
    clear_caches()
    yield
    clear_caches()
