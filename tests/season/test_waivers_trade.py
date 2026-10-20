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
    assert "FAAB left: $151" in r.lines[-2]
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
    assert r.lines[-2] == "n"


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
    assert [row[0] for row in r.tables[4].rows] == ["give", "give", "get"]


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
    assert r.tables[4].rows[1] == ("get", "ghost", "-", "", "")
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


def test_trade_shows_the_lineup_slot_by_slot_and_week_by_week(season7, sim) -> None:
    r = trade_report(season7, sim, ["rodgers"], ["allen"], "Rohan312", {})
    slots, weeks, steps, _, _ = r.tables
    assert steps.rows[0][0] == "Aaron Rodgers -> Josh Allen"
    assert steps.rows[-1][0] == "Total"
    sf = next(row for row in slots.rows if row[0] == "SUPER_FLEX")
    assert sf[1] == "Aaron Rodgers" and sf[3] == "Tanner McKee" and sf[5] == "changed"
    assert next(row for row in slots.rows if row[0] == "QB")[5] == ""
    wk7 = weeks.rows[0]
    assert wk7[0] == "7" and wk7[3] == "-3.5"  # Allen on bye: McKee for Rodgers
    assert wk7[4] == "Tanner McKee" and wk7[5] == "Aaron Rodgers"
    wk8 = weeks.rows[1]
    assert wk8[4] == "Josh Allen" and wk8[5] == "Aaron Rodgers"
    assert weeks.rows[-1][0] == "17 (playoffs)"
    assert r.lines[2].startswith("Your lineup: week 7 ")


def test_empty_slot_shows_a_dash(season7, sim) -> None:
    me = dict(season7.me, players=["maye", "pitts", "gibbs"], reserve=[])
    r = trade_report(replace(season7, me=me), sim, ["pitts"], ["swift"], "x", {})
    te = next(row for row in r.tables[0].rows if row[0] == "TE")
    assert te[1] == "Kyle Pitts" and te[3] == "-"


def test_depth_loss_is_explained(season7, sim, monkeypatch) -> None:
    import vorpal.season.trade as trade

    monkeypatch.setattr(trade, "DEPTH_GAP", -100.0)
    r = trade_report(season7, sim, ["rodgers"], ["allen"], "x", {})
    assert any(ln.startswith("Playoffs: ") for ln in r.lines)


def test_closest_call_names_the_flip_threshold(season7, sim) -> None:
    r = trade_report(season7, sim, ["pierce"], ["swift", "hubbard"], "Nuyen", {})
    assert r.subject.startswith("Trade from Nuyen: ACCEPT")
    line = next(ln for ln in r.lines if ln.startswith("Closest call:"))
    assert "Dameon Pierce. DECLINE if he averages more than" in line
    steps, flips = r.tables[2], r.tables[3]
    assert steps.rows[-1][0] == "Total"
    assert flips.header[-1] == "DECLINE if he averages over"
    assert flips.rows[0][0] == "Dameon Pierce"
    assert any(row[0].startswith("Drop ") for row in steps.rows)


def test_no_flip_line_when_the_trade_already_loses(season7, sim) -> None:
    r = trade_report(season7, sim, ["gibbs"], ["tucker"], "x", {})
    assert r.subject.startswith("Trade from x: DECLINE")
    assert not any(ln.startswith("Closest call") for ln in r.lines)
    assert r.tables[3].rows == []


def test_steps_add_up_and_name_the_open_spot(season7, sim) -> None:
    give = ["rodgers", "hall", "boston"]
    r = trade_report(season7, sim, give, ["swift", "olave"], "Nuyen", {})
    steps = r.tables[2].rows
    total = sum(float(v) for name, v in steps[:-1])
    assert float(steps[-1][1]) == pytest.approx(total, abs=0.15)
    assert any(name.startswith("Open roster spot: ") for name, _ in steps)
