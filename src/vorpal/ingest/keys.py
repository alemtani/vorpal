"""Counting-stat filters. Fantasy-point columns never survive."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vorpal.contracts import AdpVariant, Host

# FantasyPros wire name -> Sleeper scoring_settings key.
# None means drop (coarse field we must not invent a bucket from).
# Missing means keep the wire name.
FP_TO_SLEEPER: dict[str, str | None] = {
    "pass_yds": "pass_yd",
    "pass_tds": "pass_td",
    "pass_td": "pass_td",
    "pass_ints": "pass_int",
    "pass_int": "pass_int",
    "rush_yds": "rush_yd",
    "rush_tds": "rush_td",
    "rush_td": "rush_td",
    "rec_rec": "rec",
    "rec_yds": "rec_yd",
    "rec_tds": "rec_td",
    "rec_td": "rec_td",
    "fumbles": "fum_lost",
    "fl": "fum_lost",
    "fum_lost": "fum_lost",
    "fr": "fum_rec",
    "sacks": "sack",
    "safety": "safe",
    "def_sack": "sack",
    "def_int": "int",
    "def_td": "def_td",
    "def_ff": "ff",
    "def_fr": "fum_rec",
    "def_safety": "safe",
    "def_retd": "def_st_td",
    "def_pa_a": "pts_allow_0",
    "def_pa_b": "pts_allow_1_6",
    "def_pa_c": "pts_allow_7_13",
    "def_pa_d": "pts_allow_14_20",
    "def_pa_e": "pts_allow_21_27",
    "def_pa_f": "pts_allow_28_34",
    "def_pa_g": "pts_allow_35p",
    "xpt": "xpm",
    "xp": "xpm",
    "2pt_tds": None,
    "fg": None,
    "fga": None,
    "pa": None,
    "yds_agn": None,
}

# Per host, like resolve.SCORING_KEY_GROUP. ESPN stays empty until that
# adapter maps FantasyPros names onto ESPN scoring keys.
FP_TO_HOST: dict[Host, dict[str, str | None]] = {
    Host.SLEEPER: FP_TO_SLEEPER,
    Host.ESPN: {},
}

FANTASY_POINT_NAMES = frozenset(
    {
        "points",
        "points_ppr",
        "points_half",
        "points_half_ppr",
        "pts_ppr",
        "pts_std",
        "pts_half_ppr",
        "pts_half",
    }
)
GP_KEYS = ("gp", "games", "games_played")
_DROP_PREFIXES = ("adp",)


def is_fantasy_point_key(key: str) -> bool:
    """True for FP/Sleeper fantasy-point totals.

    DST buckets are pts_allow_* and stay as counting keys.
    """
    if key.startswith("pts_allow"):
        return False
    if key in FANTASY_POINT_NAMES:
        return True
    return key.startswith("pts_")


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    if number is None:
        return None
    return int(number)


def host_stat_key(
    key: str,
    *,
    position: str | None = None,
    host: Host = Host.SLEEPER,
) -> str | None:
    """Map a FantasyPros stat name onto this host's scoring key, or drop it.

    Drops fantasy-point totals, ADP, and gp. Keeps pts_allow_*. Sleeper
    ``int`` is pass_int except on DEF; ``td`` is def_td only on DEF.
    ESPN has no rows yet: FP names pass through. Coarse FG and
    points-allowed fields are dropped so we do not invent buckets.
    """
    name = str(key)
    if (
        not name
        or name in GP_KEYS
        or name.startswith(_DROP_PREFIXES)
        or is_fantasy_point_key(name)
    ):
        return None
    pos = (position or "").strip().upper()
    if pos in {"DST", "D/ST", "DEF"}:
        pos = "DEF"
    if host is Host.SLEEPER:
        if name == "int":
            return "int" if pos == "DEF" else "pass_int"
        if name == "td":
            return "def_td" if pos == "DEF" else None
    table = FP_TO_HOST.get(host, {})
    if name in table:
        return table[name]
    return name


def counting_stats(
    stats: Mapping[str, Any],
    *,
    position: str | None = None,
    host: Host = Host.SLEEPER,
) -> dict[str, float]:
    """Drop ADP, gp, and fantasy-point totals. Keep mapped counting keys."""
    out: dict[str, float] = {}
    for key, value in stats.items():
        mapped = host_stat_key(str(key), position=position, host=host)
        if mapped is None:
            continue
        number = as_float(value)
        if number is None:
            continue
        out[mapped] = number
    return out


def extract_gp(stats: Mapping[str, Any]) -> float | None:
    for key in GP_KEYS:
        number = as_float(stats.get(key))
        if number is not None:
            return number
    return None


def fp_adp_scoring(variant: AdpVariant, ecr_scoring: str | None = None) -> str:
    """STD / PPR / HALF query for FantasyPros ADP and projections."""
    if variant is AdpVariant.PPR:
        return "PPR"
    if variant is AdpVariant.HALF_PPR:
        return "HALF"
    if variant is AdpVariant.STD:
        return "STD"
    if ecr_scoring in {"PPR", "HALF", "STD"}:
        return ecr_scoring
    return "PPR"


def fp_adp_position(variant: AdpVariant) -> str:
    """ALL for 1QB boards. OP for superflex / 2QB."""
    if variant is AdpVariant.TWO_QB:
        return "OP"
    return "ALL"
