"""State assembly: snake arithmetic, roster, needs, weekly, recent, between."""

from __future__ import annotations

import pytest

from vorpal.contracts import Need, Pick, Seat, Slot
from vorpal.payload import build_state, next_pick_for_slot, slot_on_the_clock
from vorpal.valuation import ScoredPlayer

TEAMS = 12
ROUNDS = 3
SLOTS = (Slot.QB, Slot.RB, Slot.RB, Slot.WR, Slot.FLEX, Slot.BN)


def _pick(pick_no: int, player_id: str, *, position: str = "RB") -> Pick:
    round_ = (pick_no - 1) // TEAMS + 1
    slot = slot_on_the_clock(pick_no, TEAMS)
    return Pick(
        draft_id="D",
        player_id=player_id,
        picked_by="",
        roster_id=None,
        round=round_,
        draft_slot=slot,
        pick_no=pick_no,
        is_keeper=None,
        position=position,
        team=None,
        first_name=None,
        last_name=None,
    )


def _player(player_id: str, *, position: str = "RB", points: float = 200.0) -> ScoredPlayer:
    return ScoredPlayer(
        player_id=player_id,
        position=position,
        points=points,
        bye=7,
        name=f"Player {player_id}",
    )


def test_snake_slot_on_the_clock_reverses_each_round() -> None:
    assert slot_on_the_clock(1, TEAMS) == 1
    assert slot_on_the_clock(12, TEAMS) == 12
    assert slot_on_the_clock(13, TEAMS) == 12
    assert slot_on_the_clock(24, TEAMS) == 1
    assert slot_on_the_clock(25, TEAMS) == 1


def test_next_pick_for_slot_walks_the_snake() -> None:
    assert next_pick_for_slot(pick_no=1, slot=3, teams=TEAMS, rounds=ROUNDS) == 3
    assert next_pick_for_slot(pick_no=4, slot=3, teams=TEAMS, rounds=ROUNDS) == 22
    assert next_pick_for_slot(pick_no=23, slot=3, teams=TEAMS, rounds=ROUNDS) == 27


def test_next_pick_for_slot_is_none_past_the_last_round() -> None:
    assert next_pick_for_slot(pick_no=37, slot=3, teams=TEAMS, rounds=ROUNDS) is None


def test_build_state_collects_the_operator_roster_and_needs() -> None:
    picks = (
        _pick(1, "a", position="QB"),
        _pick(2, "b"),
        _pick(3, "c"),
    )
    pool = {
        "a": _player("a", position="QB", points=300.0),
        "b": _player("b", points=250.0),
        "c": _player("c", points=240.0),
    }
    state = build_state(
        pick_no=4,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=Seat(user_id="u", slot=1, roster_id=None),
        picks=picks,
        pool=pool,
    )
    assert [row.player_id for row in state.user_roster] == ["a"]
    assert state.user_roster[0].position == "QB"
    assert state.user_roster[0].bye == 7
    assert state.needs["QB"] == Need(filled=1, required=1)
    assert state.needs["RB"] == Need(filled=0, required=2)
    assert "BN" not in state.needs


def test_build_state_weekly_zeroes_the_bye_and_reports_empty_slots() -> None:
    state = build_state(
        pick_no=2,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=Seat(user_id="u", slot=1, roster_id=None),
        picks=(_pick(1, "a", position="QB"),),
        pool={"a": _player("a", position="QB", points=340.0)},
    )
    assert len(state.weekly) == 18
    week7 = state.weekly[6]
    assert week7.starter_points == 0.0
    assert Slot.QB in week7.empty
    assert Slot.BN not in week7.empty
    assert state.weekly[0].starter_points == pytest.approx(20.0)


def test_build_state_recent_is_the_last_five_picks_in_order() -> None:
    picks = tuple(_pick(n, f"p{n}") for n in range(1, 9))
    state = build_state(
        pick_no=9,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=None,
        picks=picks,
        pool={},
    )
    assert [row.pick_no for row in state.recent] == [4, 5, 6, 7, 8]
    assert state.recent[0].position == "RB"


def test_build_state_omits_the_seat_fields_when_the_seat_is_unknown() -> None:
    state = build_state(
        pick_no=4,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=None,
        picks=(_pick(1, "a"),),
        pool={},
    )
    assert state.user_roster == ()
    assert state.next_user_pick is None
    assert state.picks_until_next is None
    assert state.between is None


def test_build_state_between_lists_the_teams_that_pick_first() -> None:
    picks = (_pick(1, "a", position="QB"), _pick(2, "b"))
    state = build_state(
        pick_no=3,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=Seat(user_id="u", slot=6, roster_id=None),
        picks=picks,
        pool={"a": _player("a", position="QB"), "b": _player("b")},
    )
    assert state.next_user_pick == 6
    assert state.picks_until_next == 3
    assert state.between is not None
    assert [team.slot for team in state.between] == [3, 4, 5]


def test_build_state_between_carries_each_teams_roster_and_needs() -> None:
    picks = (_pick(1, "a", position="QB"), _pick(2, "b"))
    state = build_state(
        pick_no=3,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=Seat(user_id="u", slot=4, roster_id=None),
        picks=picks,
        pool={"a": _player("a", position="QB"), "b": _player("b")},
    )
    assert state.between is not None
    assert [team.slot for team in state.between] == [3]
    # Slot 1 already took a QB, but slot 3 has nobody yet.
    assert state.between[0].roster == {}
    assert state.between[0].needs["QB"] == Need(filled=0, required=1)


def test_build_state_between_is_empty_when_the_operator_is_on_the_clock() -> None:
    state = build_state(
        pick_no=1,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=Seat(user_id="u", slot=1, roster_id=None),
        picks=(),
        pool={},
    )
    assert state.next_user_pick == 1
    assert state.picks_until_next == 0
    assert state.between == ()


def test_build_state_falls_back_to_the_pick_position_when_the_pool_misses() -> None:
    state = build_state(
        pick_no=2,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=Seat(user_id="u", slot=1, roster_id=None),
        picks=(_pick(1, "ghost", position="WR"),),
        pool={},
    )
    assert state.user_roster[0].position == "WR"
    assert state.user_roster[0].name == "ghost"
    assert state.needs["WR"] == Need(filled=1, required=1)


def test_build_state_drops_the_seat_fields_past_the_last_round() -> None:
    state = build_state(
        pick_no=36,
        slots=SLOTS,
        teams=TEAMS,
        rounds=ROUNDS,
        seat=Seat(user_id="u", slot=1, roster_id=None),
        picks=(),
        pool={},
    )
    assert state.next_user_pick is None
    assert state.picks_until_next is None
    assert state.between is None
