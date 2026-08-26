"""Apply a league scoring table to counting stats. Never read pts_*."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

FANTASY_POINT_KEYS = frozenset({"pts_ppr", "pts_std", "pts_half_ppr"})


class ScoringFamily(StrEnum):
    PASS = "pass"
    SKILL = "skill"
    KICK = "kick"
    DST = "dst"
    IDP = "idp"
    FANTASY = "fantasy"
    UNKNOWN = "unknown"


_EXACT: dict[str, ScoringFamily] = {
    "rec": ScoringFamily.SKILL,
    "int": ScoringFamily.DST,
    "sack": ScoringFamily.DST,
    "sack_yd": ScoringFamily.DST,
    "safe": ScoringFamily.DST,
    "ff": ScoringFamily.DST,
    "blk_kick": ScoringFamily.DST,
    "blk_kick_ret_yd": ScoringFamily.DST,
    "fum": ScoringFamily.SKILL,
    "fum_lost": ScoringFamily.SKILL,
    "fum_rec": ScoringFamily.DST,
    "fum_rec_td": ScoringFamily.SKILL,
    "fum_ret_yd": ScoringFamily.DST,
    "tkl": ScoringFamily.DST,
    "tkl_solo": ScoringFamily.DST,
    "tkl_ast": ScoringFamily.DST,
    "tfl": ScoringFamily.DST,
    "qb_hit": ScoringFamily.DST,
    "pass_def": ScoringFamily.DST,
}

# Longer prefix wins: pass_int is PASS, int is DST; fgmiss before fgm.
_PREFIXES: tuple[tuple[str, ScoringFamily], ...] = tuple(
    sorted(
        (
            ("bonus_rush_", ScoringFamily.SKILL),
            ("bonus_pass_", ScoringFamily.PASS),
            ("bonus_rec_", ScoringFamily.SKILL),
            ("pts_allow_", ScoringFamily.DST),
            ("yds_allow_", ScoringFamily.DST),
            ("fgmiss", ScoringFamily.KICK),
            ("xpmiss", ScoringFamily.KICK),
            ("pass_", ScoringFamily.PASS),
            ("rush_", ScoringFamily.SKILL),
            ("idp_", ScoringFamily.IDP),
            ("def_", ScoringFamily.DST),
            ("rec_", ScoringFamily.SKILL),
            ("st_", ScoringFamily.DST),
            ("fgm", ScoringFamily.KICK),
            ("xpm", ScoringFamily.KICK),
            ("kr_", ScoringFamily.SKILL),
            ("pr_", ScoringFamily.SKILL),
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)


def classify_scoring_key(key: str) -> ScoringFamily:
    """Family for a scoring key. Longer prefix wins."""
    if key in FANTASY_POINT_KEYS:
        return ScoringFamily.FANTASY
    exact = _EXACT.get(key)
    if exact is not None:
        return exact
    for prefix, family in _PREFIXES:
        if key.startswith(prefix):
            return family
    return ScoringFamily.UNKNOWN


def unmatched_scoring_keys(
    scoring: Mapping[str, float],
    columns: set[str] | frozenset[str],
) -> tuple[str, ...]:
    """Nonzero keys with no counting column, plus fantasy-point keys.

    Callers itemize these. A zero-weight key does not need a column.
    """
    missing: list[str] = []
    for key, weight in scoring.items():
        if weight == 0.0:
            continue
        family = classify_scoring_key(key)
        if family is ScoringFamily.FANTASY or key not in columns:
            missing.append(key)
    return tuple(missing)


def score_skill(
    stats: Mapping[str, float],
    scoring: Mapping[str, float],
    *,
    position: str,
) -> float:
    """One formula for RB/WR/TE: rush, rec, yards, TDs, fumbles.

    Position only changes replacement, plus premiums such as bonus_rec_te.
    """
    return _apply(stats, scoring, {ScoringFamily.SKILL}, position)


def score_player(
    position: str,
    stats: Mapping[str, float],
    scoring: Mapping[str, float],
) -> float:
    """Dispatch by position. QB is pass_* plus the skill formula."""
    pos = "DEF" if position == "DST" else position
    if pos == "QB":
        families = {ScoringFamily.PASS, ScoringFamily.SKILL}
    elif pos in {"RB", "WR", "TE", "FB"}:
        families = {ScoringFamily.SKILL}
    elif pos == "K":
        families = {ScoringFamily.KICK}
    elif pos == "DEF":
        families = {ScoringFamily.DST}
    else:
        return 0.0
    return _apply(stats, scoring, families, pos)


def _apply(
    stats: Mapping[str, float],
    scoring: Mapping[str, float],
    families: set[ScoringFamily],
    position: str,
) -> float:
    total = 0.0
    for key, weight in scoring.items():
        if weight == 0.0:
            continue
        family = classify_scoring_key(key)
        if family is ScoringFamily.FANTASY or family not in families:
            continue
        total += weight * _stat_value(key, stats, position)
    return total


def _stat_value(key: str, stats: Mapping[str, float], position: str) -> float:
    if key.startswith("bonus_rec_"):
        tagged = _bonus_rec_position(key)
        if tagged is not None and tagged != position:
            return 0.0
        if key in stats:
            return float(stats[key])
        if tagged == position:
            return float(stats.get("rec", 0.0))
        return 0.0
    if key == "bonus_rush_td_qb" and position != "QB":
        return 0.0
    return float(stats.get(key, 0.0))


def _bonus_rec_position(key: str) -> str | None:
    tag = key.removeprefix("bonus_rec_").split("_", 1)[0].upper()
    if tag in {"RB", "WR", "TE"}:
        return tag
    return None
