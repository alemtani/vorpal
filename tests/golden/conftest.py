"""`tests/` is not a package (S0). Put this directory on the path so the
case modules import by bare name, the same way `tests/evals` does."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
