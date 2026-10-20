"""Best lineup and the injury simulation."""

import pytest

from vorpal.season.sim import SeasonSim, best_lineup, lineup_slots

ROSTER_POSITIONS = [
    "QB",
    "RB",
    "RB",
    "WR",
    "WR",
    "TE",
    "FLEX",
    "FLEX",
    "SUPER_FLEX",
    "BN",
    "BN",
]


def test_lineup_slots_drop_bench_and_put_specific_slots_first() -> None:
    assert lineup_slots(ROSTER_POSITIONS) == [
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "TE",
        "FLEX",
        "FLEX",
        "SUPER_FLEX",
    ]


def test_lineup_slots_refuse_an_unknown_slot() -> None:
    with pytest.raises(ValueError, match="K"):
        lineup_slots(["QB", "K"])


def test_best_lineup_week_7() -> None:
    pos = {
        "maye": "QB",
        "rodgers": "QB",
        "mckee": "QB",
        "gibbs": "RB",
        "pierce": "RB",
        "tuten": "RB",
        "london": "WR",
        "jwill": "WR",
        "vele": "WR",
        "boston": "WR",
        "evans": "WR",
        "pat": "TE",
        "pitts": "TE",
    }
    pts = {
        "maye": 20.9,
        "rodgers": 18.2,
        "mckee": 14.5,
        "gibbs": 26.8,
        "pierce": 6.2,
        "tuten": 0.0,
        "london": 15.8,
        "jwill": 10.9,
        "vele": 10.6,
        "boston": 10.5,
        "evans": 0.0,
        "pat": 9.4,
        "pitts": 9.1,
    }
    total, starters = best_lineup(pts, pos, lineup_slots(ROSTER_POSITIONS))
    assert total == pytest.approx(129.3 - 6.2 + 9.1 + 6.2 - 9.1, abs=0.01)
    assert dict(starters)["SUPER_FLEX"] == "rodgers"
    assert ("RB", "gibbs") in starters and ("RB", "pierce") in starters
    flex = sorted(p for s, p in starters if s == "FLEX")
    assert flex == ["boston", "vele"]


def test_best_lineup_leaves_a_slot_empty_when_nobody_fits() -> None:
    total, starters = best_lineup({"a": 5.0}, {"a": "QB"}, ["QB", "TE"])
    assert total == 5.0
    assert starters == [("QB", "a")]


def _flat(points):
    return lambda pid, week: points[pid]


def test_sim_without_injuries_is_the_plain_sum() -> None:
    sim = SeasonSim(weeks=range(7, 18), playoff_start=15, n=3, p_miss=0.0)
    pos = {"a": "QB", "b": "QB"}
    v = sim.value(["a", "b"], _flat({"a": 20.0, "b": 10.0}), pos, ["QB"])
    assert v.regular == pytest.approx(8 * 20.0)
    assert v.playoffs == pytest.approx(3 * 20.0)
    assert v.total == pytest.approx(8 * 20.0 + 1.5 * 3 * 20.0)


def test_bench_has_value_once_starters_get_hurt() -> None:
    sim = SeasonSim(weeks=range(7, 18), playoff_start=15, n=400, p_miss=0.08)
    pos = {"a": "QB", "b": "QB"}
    pts = _flat({"a": 20.0, "b": 10.0})
    with_b = sim.value(["a", "b"], pts, pos, ["QB"])
    without = sim.value(["a"], pts, pos, ["QB"])
    assert with_b.total > without.total
    assert sim.value(["a"], pts, pos, ["QB"]) == without  # same draws every call


def test_draws_belong_to_the_player_not_the_roster() -> None:
    sim = SeasonSim(weeks=range(1, 4), playoff_start=99, n=50, p_miss=0.3)
    pos = {"a": "WR", "z": "RB"}
    pts = _flat({"a": 10.0, "z": 0.0})
    alone = sim.value(["a"], pts, pos, ["WR"])
    paired = sim.value(["z", "a"], pts, pos, ["WR"])
    assert alone.regular == paired.regular
