"""Pytest fixtures for eval tests.

`tests/` is not a package (S0). Prepend this directory so test modules can
`import builders` without a root `tests/__init__.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from builders import make_payload

from vorpal.contracts import Payload


@pytest.fixture
def payload() -> Payload:
    return make_payload()
