"""The league snapshot built from a source."""

import pytest

from vorpal.errors import UserRefusal
from vorpal.season.context import LAST_WEEK, build_season


def test_snapshot_week_7(season7) -> None:
    s = season7
    assert (s.season, s.week, s.playoff_start) == (2026, 7, 15)
    assert s.me["roster_id"] == 7
    assert s.owners == {7: "alemtani", 8: "Nuyen", 10: "Rohan312"}
    assert s.slots[-1] == "SUPER_FLEX"
    assert "JAX" not in s.plays[7]
    assert s.dates["SF", 7] == "2026-10-26"
    assert s.name("gibbs") == "Jahmyr Gibbs"
    assert s.name("ghost") == "ghost"
    assert "kicker" not in s.now


def test_active_skips_reserve(season7) -> None:
    assert "hock" not in season7.active(season7.me)
    assert len(season7.active(season7.me)) == 14


def test_free_agents_are_unrostered_with_a_team_and_a_rate(season7) -> None:
    assert sorted(season7.free_agents()) == ["geno", "harvey", "tucker"]


def test_owner_lookup(season7) -> None:
    assert season7.owner_of("swift")["roster_id"] == 8
    assert season7.owner_of("harvey") is None
    assert season7.roster(10)["players"][0] == "jacobs"


def test_forecasts_this_week_and_next(season7) -> None:
    assert season7.now["tuten"].points == 0.0
    assert season7.nxt["tuten"].plays
    assert season7.now["pierce"].role_games == 0
    assert season7.now["pitts"].rising


def test_value_runs_the_sim(season7) -> None:
    sim = season7.sim(n=20)
    assert list(sim.weeks) == list(range(7, LAST_WEEK + 1))
    v = season7.value(season7.active(season7.me), sim)
    assert v.regular > 0 and v.playoffs > 0


def test_espn_outage_is_a_note_not_a_crash(make_source) -> None:
    s = build_season(make_source(espn_fails=True), "L", "me")
    assert any("ESPN" in n for n in s.notes)


def test_last_week_has_no_next_week(make_source) -> None:
    s = build_season(make_source(week=LAST_WEEK), "L", "me", week=LAST_WEEK)
    assert s.nxt == {}


def test_unknown_user_is_refused(make_source) -> None:
    with pytest.raises(UserRefusal):
        build_season(make_source(), "L", "stranger")


def test_co_owner_finds_the_roster(make_source) -> None:
    src = make_source()
    src.rosters_data[2]["co_owners"] = ["friend"]
    assert build_season(src, "L", "friend").me["roster_id"] == 10
