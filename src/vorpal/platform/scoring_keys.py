"""Host scoring keys, one table per host. The only place wire names live.

Every layer reads this: `resolve` for slot banners, `valuation` for which
formula scores a key. Nothing infers meaning from a prefix, and nothing
hardcodes a host's vocabulary of its own. Onboarding a host is adding a
table here.

Groups are positional, not families: QB, OFF, K, DEF, IDP. A caller maps a
group onto whatever it needs. A key with no row is unclassified — report it,
never score it as zero.
"""

from __future__ import annotations

from vorpal.contracts import Host


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
