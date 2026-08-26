"""Resolve slots, scoring source, seat, and market variant. No network."""

from vorpal.resolve.core import Resolved, resolve
from vorpal.resolve.eligibility import ELIGIBLE, eligible_positions, legal_slots
from vorpal.resolve.keys import classify_key

__all__ = [
    "ELIGIBLE",
    "Resolved",
    "classify_key",
    "eligible_positions",
    "legal_slots",
    "resolve",
]
