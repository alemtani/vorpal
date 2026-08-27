"""Classify scoring keys from a per-host map. Never guess from a prefix."""

from __future__ import annotations

from vorpal.contracts import Banner, Host, Slot

_STARTABLE: dict[str, frozenset[Slot]] = {
    "QB": frozenset({Slot.QB, Slot.SUPER_FLEX, Slot.OP}),
    "OFF": frozenset(
        {
            Slot.RB,
            Slot.WR,
            Slot.TE,
            Slot.FLEX,
            Slot.SUPER_FLEX,
            Slot.OP,
            Slot.WRRB_FLEX,
            Slot.REC_FLEX,
        }
    ),
    "K": frozenset({Slot.K}),
    "DEF": frozenset({Slot.DEF}),
    "IDP": frozenset({Slot.DL, Slot.LB, Slot.DB, Slot.IDP_FLEX}),
}

_GROUP_ORDER = ("QB", "OFF", "K", "DEF", "IDP")


def _group(group: str, *keys: str) -> dict[str, str]:
    return {key: group for key in keys}


# Wire scoring key -> position group. Hosts differ. A missing key is
# unclassified: itemise it if it has no stat column. Do not infer from prefix.
# ESPN stays empty until that adapter maps its scoring names.
SLEEPER_SCORING_KEY_GROUP: dict[str, str] = {
    **_group(
        "QB",
        "pass_yd",
        "pass_td",
        "pass_int",
        "pass_2pt",
        "pass_cmp",
        "pass_inc",
        "pass_att",
        "pass_sack",
        "pass_cmp_40p",
        "pass_td_40p",
        "pass_int_td",
        "bonus_pass_yd_300",
        "bonus_pass_yd_400",
        "bonus_pass_cmp_25",
        "bonus_rush_td_qb",
    ),
    **_group(
        "OFF",
        "rush_yd",
        "rush_td",
        "rush_2pt",
        "rush_att",
        "rush_fd",
        "bonus_rush_yd_100",
        "bonus_rush_yd_200",
        "rec",
        "rec_yd",
        "rec_td",
        "rec_2pt",
        "rec_fd",
        "rec_0_4",
        "rec_5_9",
        "rec_10_19",
        "rec_20_29",
        "rec_30_39",
        "rec_40p",
        "bonus_rec_te",
        "bonus_rec_wr",
        "bonus_rec_rb",
        "bonus_rec_yd_100",
        "bonus_rec_yd_200",
        "fum",
        "fum_lost",
    ),
    **_group(
        "K",
        "fgm",
        "fgm_0_19",
        "fgm_20_29",
        "fgm_30_39",
        "fgm_40_49",
        "fgm_50p",
        "fgm_60p",
        "fgm_yds",
        "fgm_yd",
        "fgmiss",
        "fgmiss_0_19",
        "fgmiss_20_29",
        "fgmiss_30_39",
        "fgmiss_40_49",
        "fgmiss_50p",
        "fgmiss_60p",
        "xpm",
        "xpmiss",
    ),
    **_group(
        "DEF",
        "sack",
        "int",
        "int_td",
        "fum_rec",
        "fum_rec_td",
        "def_td",
        "def_fum_td",
        "def_kr_td",
        "def_pr_td",
        "st_td",
        "st_ff",
        "st_fum_rec",
        "def_st_td",
        "def_st_ff",
        "def_st_fum_rec",
        "ff",
        "safe",
        "blk_kick",
        "blk_kick_td",
        "kr_td",
        "pr_td",
        "tkl_loss",
        "qb_hit",
        "pts_allow_0",
        "pts_allow_1_6",
        "pts_allow_7_13",
        "pts_allow_14_20",
        "pts_allow_21_27",
        "pts_allow_28_34",
        "pts_allow_35p",
        "yds_allow_0_100",
        "yds_allow_100_199",
        "yds_allow_200_299",
        "yds_allow_300_349",
        "yds_allow_350_399",
        "yds_allow_400_449",
        "yds_allow_450_499",
        "yds_allow_500_549",
        "yds_allow_550p",
    ),
    **_group(
        "IDP",
        "idp_tkl",
        "idp_tkl_solo",
        "idp_tkl_ast",
        "idp_sack",
        "idp_qb_hit",
        "idp_tkl_loss",
        "idp_pass_def",
        "idp_int",
        "idp_ff",
        "idp_fum_rec",
        "idp_blk_kick",
        "idp_safe",
        "idp_def_td",
    ),
}

SCORING_KEY_GROUP: dict[Host, dict[str, str]] = {
    Host.SLEEPER: SLEEPER_SCORING_KEY_GROUP,
    Host.ESPN: {},
}


def classify_key(key: str, host: Host = Host.SLEEPER) -> str | None:
    """Look up a host scoring key. None if that host has no row for it."""
    return SCORING_KEY_GROUP.get(host, {}).get(key)


def scoring_key_banners(
    scoring: dict[str, float],
    slots: tuple[Slot, ...],
    stat_columns: frozenset[str] | None,
    host: Host = Host.SLEEPER,
) -> tuple[Banner, ...]:
    """Itemise unknown nonzero keys. One line for classified keys with no slot."""
    banners: list[Banner] = []
    if stat_columns is not None:
        unknown = sorted(
            key
            for key, weight in scoring.items()
            if weight != 0 and key not in stat_columns
        )
        if unknown:
            listed = ", ".join(unknown)
            banners.append(
                Banner(
                    code="unknown_scoring_keys",
                    message=(
                        f"Nonzero scoring keys with no matching stat column: "
                        f"{listed}. Those keys score as 0 unless you supply "
                        f"an override."
                    ),
                )
            )
    startable = {slot for slot in slots if slot is not Slot.BN}
    seen: set[str] = set()
    for key, weight in scoring.items():
        if weight == 0:
            continue
        group = classify_key(key, host)
        if group is None or group in seen:
            continue
        if not (_STARTABLE[group] & startable):
            seen.add(group)
    missing = [group for group in _GROUP_ORDER if group in seen]
    if missing:
        names = ", ".join(missing)
        banners.append(
            Banner(
                code="unstartable_scoring",
                message=(
                    f"Scoring includes {names} keys but the roster has no "
                    f"startable {names} slot. Those keys score as 0 unless "
                    f"you supply an override."
                ),
            )
        )
    return tuple(banners)
