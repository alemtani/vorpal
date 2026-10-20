"""Vendor projections: Sleeper and ESPN stat lines, scored with league scoring."""

import pytest

from vorpal.season.blend import MODEL_WEIGHT, blend, status_factor
from vorpal.season.vendors import (
    PlayerIndex,
    espn_lines,
    normalize_name,
    sleeper_lines,
    vendor_points,
)

PLAYERS = {
    "100": {"full_name": "Drake London", "position": "WR", "espn_id": 4426502},
    "200": {"full_name": "Kenneth Walker III", "position": "RB"},
    "300": {"full_name": "Travis Kelce", "position": "TE", "team": "KC"},
    "301": {"full_name": "Travis Kelce", "position": "TE"},
    "400": {"full_name": "No Position"},
}


def _espn(pid, name, pos_id, stats, season=2026, period=7, source=1):
    return {
        "player": {
            "id": pid,
            "fullName": name,
            "defaultPositionId": pos_id,
            "stats": [
                {
                    "seasonId": season,
                    "scoringPeriodId": period,
                    "statSourceId": source,
                    "stats": stats,
                }
            ],
        }
    }


def test_normalize_name_drops_suffix_and_punctuation() -> None:
    assert normalize_name("Kenneth Walker III") == "kennethwalker"
    assert normalize_name("D'Andre Swift") == "dandreswift"
    assert normalize_name("Marvin Harrison Jr.") == "marvinharrison"


def test_index_joins_by_espn_id_then_name() -> None:
    idx = PlayerIndex(PLAYERS)
    assert idx.find(espn_id=4426502, name="x", position="WR") == "100"
    assert idx.find(espn_id=1, name="Kenneth Walker", position="RB") == "200"
    assert idx.find(espn_id=None, name="Travis Kelce", position="TE") == "300"
    assert idx.find(espn_id=None, name="Nobody", position="WR") is None


def test_index_refuses_an_ambiguous_name() -> None:
    players = {
        "1": {"full_name": "Mike Williams", "position": "WR", "team": "NYJ"},
        "2": {"full_name": "Mike Williams", "position": "WR", "team": "PIT"},
    }
    assert PlayerIndex(players).find(None, "Mike Williams", "WR") is None


def test_sleeper_lines_keep_stats_by_player() -> None:
    rows = [
        {"player_id": "100", "stats": {"rec": 6.0}},
        {"player_id": "200", "stats": None},
    ]
    assert sleeper_lines(rows) == {"100": {"rec": 6.0}}


def test_espn_lines_map_stat_ids_and_filter_the_week() -> None:
    payload = {
        "players": [
            _espn(4426502, "Drake London", 3, {"53": 6.18, "42": 90.17, "43": 0.31}),
            _espn(9, "Kenneth Walker", 2, {"23": 15, "24": 70.0}, period=6),
            _espn(8, "Brandon Aubrey", 5, {"80": 2}),
            _espn(7, "Unknown Guy", 3, {"53": 3}),
            _espn(6, "Travis Kelce", 4, {"53": 5}, source=0),
        ]
    }
    lines = espn_lines(payload, PlayerIndex(PLAYERS), season=2026, week=7)
    assert lines == {"100": {"rec": 6.18, "rec_yd": 90.17, "rec_td": 0.31}}


def test_vendor_points_score_each_vendor() -> None:
    scoring = {"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0}
    vendors = {
        "sleeper": {"100": {"rec": 6.0, "rec_yd": 80.0, "rec_td": 0.5}},
        "espn": {"100": {"rec": 6.18, "rec_yd": 90.17, "rec_td": 0.31}},
    }
    pts = vendor_points(vendors, scoring, {"100": "WR"})
    assert pts["100"]["sleeper"] == pytest.approx(17.0)
    assert pts["100"]["espn"] == pytest.approx(17.057, abs=1e-3)


def test_blend_quarter_model_three_quarters_vendors() -> None:
    assert MODEL_WEIGHT == 0.25
    got = blend(14.64, {"sleeper": 17.11, "espn": 17.16}, role_games=6)
    assert got == pytest.approx(0.25 * 14.64 + 0.75 * 17.135)


def test_blend_drops_the_model_without_role_games() -> None:
    pierce = blend(13.4, {"sleeper": 6.32, "espn": 6.37}, role_games=0)
    assert pierce == pytest.approx(6.345)
    two = blend(13.4, {"sleeper": 6.3}, role_games=2, weight=0.5)
    assert two == pytest.approx(0.5 * 2 / 3 * 13.4 + (1 - 1 / 3) * 6.3)


def test_blend_falls_back_to_whatever_exists() -> None:
    assert blend(None, {"sleeper": 20.0}, role_games=0) == 20.0
    assert blend(9.0, {}, role_games=1) == 9.0
    assert blend(None, {}, role_games=0) is None


@pytest.mark.parametrize(
    ("status", "factor"),
    [
        (None, 1.0),
        ("", 1.0),
        ("Questionable", 0.85),
        ("Doubtful", 0.25),
        ("Out", 0.0),
        ("IR", 0.0),
        ("Sus", 0.0),
        ("PUP", 0.0),
    ],
)
def test_status_factor(status, factor) -> None:
    assert status_factor(status) == factor
