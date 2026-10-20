"""Opportunity model. Real 2026 lines, weeks 1-6."""

import pytest

from vorpal.season.usage import (
    DEFAULT_RATES,
    Params,
    Rates,
    expected_line,
    position_rates,
    rising,
    role_games,
    score_line,
)

PPR = {
    "rec": 1.0,
    "rec_yd": 0.1,
    "rush_yd": 0.1,
    "rec_td": 6.0,
    "rush_td": 6.0,
    "fum_lost": -2.0,
}

LONDON = {
    1: {"rec_tgt": 5, "rec": 2, "rec_yd": 29, "rush_att": 1, "rush_yd": 6},
    2: {"rec_tgt": 5, "rec": 4, "rec_yd": 51, "rush_att": 1, "rush_yd": -2},
    3: {"rec_tgt": 10, "rec": 9, "rec_yd": 194},
    4: {"rec_tgt": 6, "rec": 5, "rec_yd": 96},
    5: {"rec_tgt": 11, "rec": 7, "rec_yd": 118},
    6: {"rec_tgt": 10, "rec": 4, "rec_yd": 62, "rec_rz_tgt": 2},
}
for _w, _line in LONDON.items():
    _line.update(off_snp=60, tm_off_snp=64)

WR = Rates(catch=0.621, ypt=8.05, ypc=5.08)


def _snaps(tgts, snaps):
    return {
        w: {"rec_tgt": t, "off_snp": s, "tm_off_snp": 100}
        for w, (t, s) in enumerate(zip(tgts, snaps, strict=True), start=1)
    }


def test_london_week_7_is_14_6() -> None:
    line = expected_line(LONDON, 7, WR, Params())
    assert line is not None
    assert line.targets == pytest.approx(8.378, abs=1e-3)
    assert line.rz_targets == pytest.approx(0.493, abs=1e-3)
    assert line.expected_td == pytest.approx(0.243, abs=1e-3)
    assert score_line(line.stats, PPR, "WR") == pytest.approx(14.64, abs=0.01)


def test_only_games_before_the_week_count() -> None:
    early = expected_line(LONDON, 3, WR, Params())
    assert early is not None
    assert early.targets == pytest.approx(5.0)
    assert early.games == 2


def test_no_games_means_no_line() -> None:
    assert expected_line({}, 7, WR, Params()) is None
    assert expected_line(LONDON, 1, WR, Params()) is None


def test_actual_tds_count_a_quarter() -> None:
    lucky = {w: dict(line, rec_td=1) for w, line in LONDON.items()}
    base = expected_line(LONDON, 7, WR, Params())
    hot = expected_line(lucky, 7, WR, Params())
    assert base is not None and hot is not None
    assert hot.stats["rec_td"] - base.stats["rec_td"] == pytest.approx(0.25)


def test_rushing_tds_split_from_receiving() -> None:
    rb = {1: {"rush_att": 20, "rush_rz_att": 4, "rush_yd": 80, "rush_td": 1}}
    line = expected_line(rb, 2, DEFAULT_RATES["RB"], Params())
    assert line is not None
    assert line.stats["rush_td"] == pytest.approx(0.75 * (4 * 0.19 + 16 * 0.005) + 0.25)
    assert line.stats["rec_td"] == 0.0


def test_score_line_adds_position_bonus() -> None:
    scoring = {"rec": 1.0, "bonus_rec_te": 0.5}
    assert score_line({"rec": 4}, scoring, "TE") == 6.0
    assert score_line({"rec": 4}, scoring, "WR") == 4.0


def test_position_rates_from_season_lines() -> None:
    lines = [
        ("WR", {"rec_tgt": 10, "rec": 6, "rec_yd": 80}),
        ("WR", {"rec_tgt": 10, "rec": 7, "rec_yd": 90, "rush_att": 2, "rush_yd": 10}),
        ("QB", {"rec_tgt": 1}),
    ]
    rates = position_rates(lines)
    assert rates["WR"] == Rates(catch=0.65, ypt=8.5, ypc=5.0)
    assert rates["RB"] == DEFAULT_RATES["RB"]
    assert "QB" not in rates


def test_position_rates_keep_default_when_volume_is_missing() -> None:
    rates = position_rates([("TE", {"rec_tgt": 0})])
    assert rates["TE"] == DEFAULT_RATES["TE"]


def test_pitts_is_rising() -> None:
    pitts = _snaps([1, 3, 2, 3, 6, 7], [63, 38, 59, 51, 67, 78])
    assert rising(pitts, 7)


def test_freiermuth_is_not_rising() -> None:
    pat = _snaps([5, 5, 4, 5, 7, 3], [73, 66, 60, 75, 68, 72])
    assert not rising(pat, 7)


def test_rising_needs_three_games() -> None:
    assert not rising(_snaps([1, 2], [10, 20]), 3)


def test_role_games_skip_games_without_this_weeks_teammates() -> None:
    pierce = {5: {"rush_att": 11}, 6: {"rush_att": 12}}
    barkley = {1: {"off_snp": 39}, 2: {"off_snp": 12}, 4: {"off_snp": 4}}
    assert role_games(pierce, 7, [barkley]) == 0
    assert role_games(pierce, 7, []) == 2
    back = {**barkley, 6: {"off_snp": 30}}
    assert role_games(pierce, 7, [back]) == 1
