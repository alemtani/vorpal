"""Weekly forecast: model + vendors + role + status + bye."""

import pytest

from vorpal.season.forecast import forecast_week, season_points
from vorpal.season.usage import DEFAULT_RATES

SCORING = {"rec": 1.0, "rec_yd": 0.1, "rush_yd": 0.1, "rec_td": 6.0, "rush_td": 6.0}

PLAYERS = {
    "pierce": {"full_name": "Dameon Pierce", "position": "RB", "team": "PHI"},
    "saquon": {
        "full_name": "Saquon Barkley",
        "position": "RB",
        "team": "PHI",
        "injury_status": "Out",
    },
    "tuten": {"full_name": "Bhayshul Tuten", "position": "RB", "team": "JAX"},
    "maye": {"full_name": "Drake Maye", "position": "QB", "team": "NE"},
    "fa": {"full_name": "Free Agent", "position": "WR"},
    "hock": {
        "full_name": "T.J. Hockenson",
        "position": "TE",
        "team": "MIN",
        "injury_status": "IR",
    },
}
GAMES = {
    "pierce": {
        5: {"rush_att": 11, "rush_yd": 40, "rec_tgt": 5, "rec": 3, "off_snp": 30},
        6: {"rush_att": 12, "rush_yd": 50, "rec_tgt": 5, "rec": 4, "off_snp": 40},
    },
    "saquon": {1: {"rush_att": 15, "off_snp": 39}, 3: {"rush_att": 15, "off_snp": 36}},
    "tuten": {6: {"rush_att": 17, "rush_yd": 80, "off_snp": 40}},
}
VENDORS = {
    "pierce": {"sleeper": 6.32, "espn": 6.37},
    "saquon": {"sleeper": 13.77},
    "maye": {"sleeper": 21.58, "espn": 20.55},
}
PLAYING = {"PHI", "NE", "MIN"}


def _week7(**kw):
    args = dict(
        pids=list(PLAYERS),
        week=7,
        players=PLAYERS,
        games=GAMES,
        rates={"RB": DEFAULT_RATES["RB"]},
        vendors=VENDORS,
        teams_playing=PLAYING,
        scoring=SCORING,
    )
    args.update(kw)
    return forecast_week(**args)


def test_pierce_is_vendors_only_while_barkley_projects_to_play() -> None:
    f = _week7()["pierce"]
    assert f.model is not None and f.model > 10
    assert f.role_games == 0
    assert f.rate == pytest.approx(6.345)
    assert f.points == pytest.approx(6.345)


def test_pierce_keeps_his_model_when_barkley_is_not_projected() -> None:
    vendors = dict(VENDORS, saquon={"sleeper": 0.0})
    f = _week7(vendors=vendors)["pierce"]
    assert f.role_games == 2
    assert f.rate > 6.345


def test_bye_week_scores_zero_but_keeps_the_rate() -> None:
    f = _week7()["tuten"]
    assert not f.plays
    assert f.points == 0.0
    assert f.rate > 0


def test_out_scores_zero_this_week() -> None:
    f = _week7()["saquon"]
    assert f.points == 0.0
    assert f.rate == pytest.approx(13.77)


def test_qb_is_vendor_only() -> None:
    f = _week7()["maye"]
    assert f.model is None
    assert f.rate == pytest.approx((21.58 + 20.55) / 2)


def test_free_agent_without_team_or_data_is_zero() -> None:
    f = _week7()["fa"]
    assert f.rate == 0.0 and not f.plays
    assert f.name == "Free Agent"


def test_season_points_bye_rate_return_weeks() -> None:
    now = _week7()
    nxt = _week7(week=8, teams_playing={"PHI", "NE", "MIN", "JAX"})
    plays = {7: PLAYING, 8: PLAYING | {"JAX"}, 9: PLAYING | {"JAX"}, 11: {"MIN"}}
    pts = season_points(now, nxt, 7, plays)
    assert pts("tuten", 7) == 0.0
    assert pts("tuten", 8) == pytest.approx(nxt["tuten"].rate)
    assert pts("saquon", 7) == 0.0
    assert pts("saquon", 8) == pytest.approx(13.77)
    assert pts("hock", 10) == 0.0
    assert pts("hock", 11) == pytest.approx(now["hock"].rate)
    assert pts("maye", 7) == pytest.approx(now["maye"].points)
    assert pts("fa", 8) == 0.0
    assert pts("nobody", 8) == 0.0


def test_season_points_use_this_week_when_next_week_is_missing() -> None:
    now = _week7()
    plays = {8: {"JAX"}}
    pts = season_points(now, {}, 7, plays)
    assert pts("tuten", 8) == pytest.approx(now["tuten"].rate)
    only_next = season_points({}, _week7(), 7, {8: PLAYING})
    assert only_next("maye", 8) == pytest.approx(_week7()["maye"].rate)


def test_body_part_is_shown_but_does_not_change_the_return_week() -> None:
    from dataclasses import replace

    from vorpal.season.forecast import assumed_returns, return_label

    now = _week7()
    now["evans"] = replace(now["saquon"], name="Mike Evans", injury="Achilles")
    assert return_label(now["evans"], 7) == "week 8"
    assert return_label(now["maye"], 7) == "now"
    assert assumed_returns(now, ["evans", "saquon", "maye"], 7) == (
        "Mike Evans (Out, Achilles) week 8, Saquon Barkley (Out) week 8"
    )
