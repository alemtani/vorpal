"""Process-level caches. Projections and ECR are fetched once, never polled."""

from __future__ import annotations

from typing import Any

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

projection_cache: dict[str, Any] = {}
ecr_cache: dict[tuple[str, str, bool], Any] = {}


def clear_caches() -> None:
    """Drop cached payloads. Tests call this between cases."""
    projection_cache.clear()
    ecr_cache.clear()
