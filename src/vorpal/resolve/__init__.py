"""Resolve slots, scoring source, seat, and market variant. No network."""

from vorpal.resolve.core import Resolved, resolve
from vorpal.resolve.eligibility import ELIGIBLE, eligible_positions, legal_slots
from vorpal.resolve.keys import SCORING_KEY_GROUP, classify_key

__all__ = [
    "ELIGIBLE",
    "SCORING_KEY_GROUP",
    "Resolved",
    "classify_key",
    "eligible_positions",
    "legal_slots",
    "resolve",
]
