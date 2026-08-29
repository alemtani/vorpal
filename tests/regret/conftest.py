"""`tests/` is not a package (S0). Put this directory on the path so
`replay` and `build` import by bare name."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
