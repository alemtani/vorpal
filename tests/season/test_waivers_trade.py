"""Waiver adds and trade verdicts on the fake week 7 league."""

from dataclasses import replace

import pytest

from vorpal.season.trade import trade_report, verdict
from vorpal.season.waivers import (
    DEFAULT_MEDIAN_BID,
    faab_bid,
    median_winning_bid,
    waiver_report,
)


@pytest.fixture(scope="module")
def sim(season7):
    return season7.sim(n=150)


def test_median_winning_bid(make_source) -> None:
    src = make_source()
    assert median_winning_bid(src.transactions("L", 3)) == 20.0
    assert median_winning_bid([]) == DEFAULT_MEDIAN_BID


def test_faab_bid_scales_and_caps() -> None:
    assert faab_bid(12.6, 20.0, 151) == 13
    assert faab_bid(500.0, 20.0, 151) == 60
    assert faab_bid(0.1, 20.0, 151) == 1
    assert faab_bid(-3.0, 20.0, 151) == 0
    assert faab_bid(5.0, 20.0, 0) == 0


def test_waivers_add_an_rb_and_never_drop_rising_pitts(season7, sim) -> None:
    r = waiver_report(season7, sim, 20.0)
    adds, drops = r.tables
    assert r.subject.startswith("Waivers: add RJ Harvey")
    assert "Kyle Pitts" not in r.subject
    assert "Hold: Kyle Pitts (rising: snaps and touches up 2 weeks)." in r.lines
    assert all(row[3] != "Kyle Pitts" for row in adds.rows)
    pitts = next(row for row in drops.rows if row[0] == "Kyle Pitts")
    assert pitts[2] == "hold (rising)"
    assert "FAAB left: $151" in r.lines[-1]
    assert "Assumed back: Breece Hall (Out) week 8, Mike Evans (Out) week 8." in r.lines
    assert r.key.startswith("harvey|")


def test_waivers_no_move_when_nothing_helps(season7, sim) -> None:
    now = {
        p: replace(f, rate=0.1, points=0.1) if p in season7.free_agents() else f
        for p, f in season7.now.items()
    }
    nxt = {
        p: replace(f, rate=0.1) if p in season7.free_agents() else f
        for p, f in season7.nxt.items()
    }
    r = waiver_report(replace(season7, now=now, nxt=nxt, notes=["n"]), sim, 20.0)
    assert r.subject == "Waivers: no move this week"
    assert r.lines[0].startswith("No add beats 3.0 points. Best:")
    assert r.lines[-1] == "n"


def test_waivers_with_an_empty_pool(season7, sim) -> None:
    rosters = [dict(r) for r in season7.rosters]
    rosters.append({"roster_id": 99, "players": ["harvey", "geno", "tucker"]})
    r = waiver_report(replace(season7, rosters=rosters), sim, 20.0)
    assert r.lines[0] == "No add beats 3.0 points."
    assert r.key == ""


@pytest.mark.parametrize(
    ("regular", "playoffs", "call"),
    [
        (-0.1, 9.0, "DECLINE"),
        (5.1, 0.0, "ACCEPT"),
        (3.7, 4.3, "CLOSE CALL"),
        (9.0, -1.0, "CLOSE CALL"),
    ],
)
def test_verdict(regular, playoffs, call) -> None:
    assert verdict(regular, playoffs) == call


def test_trade_jacobs_for_hall_and_pitts_is_declined(season7, sim) -> None:
    market = {"jacobs": 2733, "hall": 2834, "pitts": 680}
    r = trade_report(season7, sim, ["hall", "pitts"], ["jacobs"], "Rohan312", market)
    assert r.subject.startswith("Trade from Rohan312: DECLINE")
    assert (
        r.lines[0]
        == "Rohan312 offers Josh Jacobs for Breece Hall + Kyle Pitts. DECLINE."
    )
    assert "Market (FantasyCalc): you give 3514, get 2733." in r.lines
    assert "Trade deadline: week 9." in r.lines
    assert "Assumed back: Breece Hall (Out) week 8." in r.lines
    assert [row[0] for row in r.tables[0].rows] == ["give", "give", "get"]


def test_two_for_one_forces_a_drop(season7, sim) -> None:
    r = trade_report(season7, sim, ["pierce"], ["swift", "hubbard"], "Nuyen", {})
    assert any(ln.startswith("You must drop") for ln in r.lines)
    assert r.subject.startswith("Trade from Nuyen: ACCEPT")


def test_trade_refuses_players_you_do_not_own(season7, sim) -> None:
    with pytest.raises(ValueError, match="Josh Jacobs"):
        trade_report(season7, sim, ["jacobs"], ["pierce"], "x", {})


def test_trade_row_for_an_unknown_player_and_no_deadline(season7, sim) -> None:
    league = dict(season7.league, settings={})
    s = replace(season7, league=league)
    r = trade_report(s, sim, ["pierce"], ["ghost"], "x", {})
    assert r.tables[0].rows[1] == ("get", "ghost", "-", "", "")
    assert not any(ln.startswith("Trade deadline") for ln in r.lines)


def test_three_for_two_fills_the_open_spot_from_free_agency(season7, sim) -> None:
    give = ["rodgers", "hall", "boston"]
    r = trade_report(season7, sim, give, ["swift", "olave"], "Nuyen", {})
    assert "Counts adding Geno Smith from free agency to the open spot." in r.lines


def test_open_spot_stays_open_without_free_agents(season7, sim) -> None:
    rosters = [dict(r) for r in season7.rosters]
    rosters.append({"roster_id": 99, "players": ["harvey", "geno", "tucker"]})
    s = replace(season7, rosters=rosters)
    r = trade_report(s, sim, ["rodgers", "hall"], ["swift"], "Nuyen", {})
    assert not any(ln.startswith("Counts adding") for ln in r.lines)
