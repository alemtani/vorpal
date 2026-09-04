"""Pytest fixtures for eval tests.

`tests/` is not a package (S0). Prepend this directory so test modules can
`import builders` without a root `tests/__init__.py`. Prepend the repo root
too, so a test can import the harness package `evals/` that lives beside
`src/` and is not installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from builders import make_payload

from vorpal.contracts import Payload


@pytest.fixture
def payload() -> Payload:
    return make_payload()
