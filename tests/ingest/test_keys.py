"""FP stat names map onto host scoring keys. Fantasy points never survive."""

from __future__ import annotations

from vorpal.contracts import AdpVariant, Host
from vorpal.ingest.keys import (
    FP_TO_HOST,
    counting_stats,
    extract_gp,
    fp_adp_position,
    fp_adp_scoring,
    host_stat_key,
    is_fantasy_point_key,
)


def test_fantasy_point_columns_are_detected() -> None:
    assert is_fantasy_point_key("points")
    assert is_fantasy_point_key("points_ppr")
    assert is_fantasy_point_key("points_half")
    assert is_fantasy_point_key("pts_ppr")
    assert is_fantasy_point_key("pts_std")
    assert not is_fantasy_point_key("pts_allow_0")
    assert not is_fantasy_point_key("pass_yd")


def test_pass_and_rec_names_map_onto_host_keys() -> None:
    stats = counting_stats(
        {
            "pass_yds": 4200,
            "pass_tds": 32,
            "pass_ints": 12,
            "rec_rec": 80,
            "rec_yds": 1000,
            "rec_tds": 6,
            "rush_yds": 40,
            "rush_tds": 1,
            "points": 300,
            "points_ppr": 380,
            "gp": 17,
        },
        position="QB",
    )
    assert stats == {
        "pass_yd": 4200.0,
        "pass_td": 32.0,
        "pass_int": 12.0,
        "rec": 80.0,
        "rec_yd": 1000.0,
        "rec_td": 6.0,
        "rush_yd": 40.0,
        "rush_td": 1.0,
    }


def test_dst_int_and_td_stay_defensive() -> None:
    stats = counting_stats(
        {"int": 12, "td": 3, "sack": 40, "fr": 8, "safety": 1, "pa": 320, "fg": 0},
        position="DST",
    )
    assert stats["int"] == 12.0
    assert stats["def_td"] == 3.0
    assert stats["sack"] == 40.0
    assert stats["fum_rec"] == 8.0
    assert stats["safe"] == 1.0
    assert "pa" not in stats
    assert "fg" not in stats


def test_fp_def_prefix_maps_onto_host_dst_keys() -> None:
    stats = counting_stats(
        {
            "def_sack": 40,
            "def_int": 12,
            "def_td": 3,
            "def_ff": 8,
            "def_fr": 5,
            "def_safety": 1,
            "def_retd": 2,
            "def_pa_a": 1,
            "def_pa_g": 4,
            "points": 99,
        },
        position="DST",
    )
    assert stats["sack"] == 40.0
    assert stats["int"] == 12.0
    assert stats["def_td"] == 3.0
    assert stats["ff"] == 8.0
    assert stats["fum_rec"] == 5.0
    assert stats["safe"] == 1.0
    assert stats["def_st_td"] == 2.0
    assert stats["pts_allow_0"] == 1.0
    assert stats["pts_allow_35p"] == 4.0
    assert "points" not in stats


def test_qb_int_is_pass_int() -> None:
    assert host_stat_key("int", position="QB") == "pass_int"
    assert counting_stats({"int": 10}, position="QB") == {"pass_int": 10.0}


def test_espn_map_is_empty_and_does_not_apply_sleeper_names() -> None:
    assert FP_TO_HOST[Host.ESPN] == {}
    stats = counting_stats(
        {"pass_yds": 4200, "rec_rec": 80, "points_ppr": 300},
        position="QB",
        host=Host.ESPN,
    )
    assert stats == {"pass_yds": 4200.0, "rec_rec": 80.0}
    assert "pass_yd" not in stats
    assert host_stat_key("int", position="QB", host=Host.ESPN) == "int"


def test_coarse_kicker_fields_are_not_invented_as_distance_buckets() -> None:
    stats = counting_stats(
        {"fg": 28, "fga": 33, "xpt": 45, "points": 130}, position="K"
    )
    assert stats == {"xpm": 45.0}
    assert "fgm_40_49" not in stats


def test_pts_allow_buckets_stay() -> None:
    stats = counting_stats({"pts_allow_0": 2, "pts_ppr": 9})
    assert stats == {"pts_allow_0": 2.0}


def test_gp_from_games_or_games_played() -> None:
    assert extract_gp({"gp": 17}) == 17.0
    assert extract_gp({"games": 16}) == 16.0
    assert extract_gp({"games_played": 15}) == 15.0
    assert extract_gp({}) is None


def test_adp_variant_maps_onto_fp_query() -> None:
    assert fp_adp_scoring(AdpVariant.PPR) == "PPR"
    assert fp_adp_scoring(AdpVariant.HALF_PPR) == "HALF"
    assert fp_adp_scoring(AdpVariant.STD) == "STD"
    assert fp_adp_scoring(AdpVariant.TWO_QB, "HALF") == "HALF"
    assert fp_adp_position(AdpVariant.TWO_QB) == "OP"
    assert fp_adp_position(AdpVariant.PPR) == "ALL"
