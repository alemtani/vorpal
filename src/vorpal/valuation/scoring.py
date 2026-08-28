"""Apply a league scoring table to counting stats. Never read pts_*."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from vorpal.contracts import Host
from vorpal.platform.scoring_keys import SCORING_KEY_GROUP

FANTASY_POINT_KEYS = frozenset({"pts_ppr", "pts_std", "pts_half_ppr"})


class ScoringFamily(StrEnum):
    PASS = "pass"
    SKILL = "skill"
    KICK = "kick"
    DST = "dst"
    IDP = "idp"
    FANTASY = "fantasy"
    UNKNOWN = "unknown"


# The host table groups keys by position. Valuation needs the formula that
# scores them. One row per group, so the two never drift apart.
_GROUP_FAMILY: dict[str, ScoringFamily] = {
    "QB": ScoringFamily.PASS,
    "OFF": ScoringFamily.SKILL,
    "K": ScoringFamily.KICK,
    "DEF": ScoringFamily.DST,
    "IDP": ScoringFamily.IDP,
}

_SKILL_POSITIONS = frozenset({"RB", "WR", "TE", "FB"})


def classify_scoring_key(key: str, host: Host = Host.SLEEPER) -> ScoringFamily:
    """Family for a scoring key, from the host table. Never from a prefix.

    UNKNOWN means the table has no row. The key is reported, not scored.
    """
    if key in FANTASY_POINT_KEYS:
        return ScoringFamily.FANTASY
    group = SCORING_KEY_GROUP.get(host, {}).get(key)
    if group is None:
        return ScoringFamily.UNKNOWN
    return _GROUP_FAMILY[group]


def unmatched_scoring_keys(
    scoring: Mapping[str, float],
    columns: set[str] | frozenset[str],
    host: Host = Host.SLEEPER,
) -> tuple[str, ...]:
    """Nonzero keys with no counting column, plus fantasy-point keys.

    Callers itemize these. A zero-weight key does not need a column.
    """
    missing: list[str] = []
    for key, weight in scoring.items():
        if weight == 0.0:
            continue
        family = classify_scoring_key(key, host)
        if family is ScoringFamily.FANTASY or key not in columns:
            missing.append(key)
    return tuple(missing)


def score_skill(
    stats: Mapping[str, float],
    scoring: Mapping[str, float],
    *,
    position: str,
    host: Host = Host.SLEEPER,
) -> float:
    """One formula for RB/WR/TE: rush, rec, yards, TDs, fumbles.

    Position only changes replacement, plus premiums such as bonus_rec_te.
    """
    return _apply(stats, scoring, {ScoringFamily.SKILL}, position, host)


def score_player(
    position: str,
    stats: Mapping[str, float],
    scoring: Mapping[str, float],
    host: Host = Host.SLEEPER,
) -> float:
    """Dispatch by position. QB is pass_* plus the skill formula."""
    pos = "DEF" if position == "DST" else position
    if pos == "QB":
        families = {ScoringFamily.PASS, ScoringFamily.SKILL}
    elif pos in _SKILL_POSITIONS:
        families = {ScoringFamily.SKILL}
    elif pos == "K":
        families = {ScoringFamily.KICK}
    elif pos == "DEF":
        families = {ScoringFamily.DST}
    else:
        return 0.0
    return _apply(stats, scoring, families, pos, host)


def _apply(
    stats: Mapping[str, float],
    scoring: Mapping[str, float],
    families: set[ScoringFamily],
    position: str,
    host: Host,
) -> float:
    total = 0.0
    for key, weight in scoring.items():
        if weight == 0.0:
            continue
        family = classify_scoring_key(key, host)
        if family is ScoringFamily.FANTASY or family not in families:
            continue
        total += weight * _stat_value(key, stats, position)
    return total


def _stat_value(key: str, stats: Mapping[str, float], position: str) -> float:
    """Read one counting column. Only receptions premiums need the position.

    `bonus_rec_te` and friends are one OFF row that pays one position. The
    forecast rarely ships the bonus column, so fall back to `rec`.
    """
    if key.startswith("bonus_rec_"):
        tagged = _bonus_rec_position(key)
        if tagged is not None and tagged != position:
            return 0.0
        if key in stats:
            return float(stats[key])
        if tagged == position:
            return float(stats.get("rec", 0.0))
        return 0.0
    return float(stats.get(key, 0.0))


def _bonus_rec_position(key: str) -> str | None:
    tag = key.removeprefix("bonus_rec_").split("_", 1)[0].upper()
    if tag in {"RB", "WR", "TE"}:
        return tag
    return None
