"""The regret fixtures: derived, redacted, and doing what they claim.

Three checks, in order of what they protect.

1. **Derived.** Every committed file is rebuilt from the recorded picks
   and compared byte for byte. Nobody hand-edits a record.
2. **Redacted.** No manager, no seat owner, no league. The fields are
   enumerated and the file text is searched for the shapes a leak would
   take, because "we redacted it" is a claim and this is the check.
3. **Load bearing.** A fixture where nothing was taken between our two
   picks cannot fail the regret gate and therefore measures nothing. At
   least one fixture must be able to fail it.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields

import pytest
from build import SPECS, build
from replay import FIXTURES, RegretFixture, all_fixtures, load_fixture, snake_pick

from vorpal.contracts import (
    Banner,
    DraftState,
    GateOutcome,
    LeagueConfig,
    Payload,
    Proposal,
    Slot,
)
from vorpal.evals import regret

FIXTURE_IDS = [spec["name"] for spec in SPECS]

# Sleeper NFL player ids: a number for a person, a team abbreviation for
# a defense. Anything else in these lists would be something we did not
# mean to commit.
PLAYER_ID = re.compile(r"^(\d+|[A-Z]{2,3})$")

# The shape a redacted seat owner takes in the recorded picks.
MANAGER_ID = re.compile(r"user_(\d|operator)")


# The regret gate reads the proposal and the fixture, never the board, so
# these cases run against an empty payload on purpose: a board would
# suggest the gate consults one.
_ANY = Payload(
    config=LeagueConfig(
        teams=12,
        rounds=15,
        slots=(Slot.RB,),
        scoring={},
        scoring_summary="",
        banners=(Banner(code="empty", message="no board needed"),),
    ),
    state=DraftState(pick_no=1, user_roster=(), needs={}, weekly=(), recent=()),
    replacement={},
    hint_argmax_vols="",
    board=(),
)


def _propose(player_id: str, alternatives: tuple[str, ...]) -> Proposal:
    return Proposal(
        player_id=player_id,
        alternatives=alternatives,
        slot_filled=Slot.BN,
        coin_flip=False,
        why="test",
        flags=(),
    )


def test_there_are_fixtures() -> None:
    assert len(all_fixtures()) == len(SPECS)


@pytest.mark.parametrize("fixture", build(), ids=FIXTURE_IDS)
def test_committed_file_matches_the_replay(fixture: RegretFixture) -> None:
    """Rebuild from the recorded picks and compare. No hand edits."""
    committed = (FIXTURES / f"{fixture.name}.json").read_text()
    assert committed == fixture.to_json()


@pytest.mark.parametrize("fixture", all_fixtures(), ids=FIXTURE_IDS)
def test_no_manager_and_no_league_in_the_file(fixture: RegretFixture) -> None:
    """Other people's drafts fall under the same no-commit rule as ours.

    A seat is an integer. Everything else in the file is an NFL player,
    a pick number, or prose we wrote.
    """
    body = json.loads((FIXTURES / f"{fixture.name}.json").read_text())
    assert set(body) == {field.name for field in fields(RegretFixture)}
    for key in ("picked_by", "roster_id", "metadata", "reactions", "draft_order"):
        assert key not in body
    for group in ("drafted_before", "taken_between", "universe"):
        for player_id in body[group]:
            assert PLAYER_ID.match(player_id), player_id
    assert PLAYER_ID.match(body["actually_picked"])
    assert 1 <= body["draft_slot"] <= body["teams"]
    # The recorded picks carry redacted seat owners (`user_07`,
    # `user_operator`). None of them reach a regret fixture.
    assert not MANAGER_ID.search(json.dumps(body))


@pytest.mark.parametrize("fixture", all_fixtures(), ids=FIXTURE_IDS)
def test_the_record_is_arithmetic_on_a_list(fixture: RegretFixture) -> None:
    assert fixture.pick_no == snake_pick(
        fixture.teams, fixture.draft_slot, fixture.round_no
    )
    assert fixture.next_user_pick == snake_pick(
        fixture.teams, fixture.draft_slot, fixture.round_no + 1
    )
    assert len(fixture.drafted_before) == fixture.pick_no - 1
    assert len(fixture.taken_between) == (fixture.next_user_pick - fixture.pick_no - 1)
    assert fixture.actually_picked not in fixture.drafted_before
    assert fixture.actually_picked not in fixture.taken_between
    assert set(fixture.drafted_before) <= set(fixture.universe)
    assert set(fixture.taken_between) <= set(fixture.universe)


@pytest.mark.parametrize("fixture", all_fixtures(), ids=FIXTURE_IDS)
def test_each_fixture_says_whose_market_it_is(fixture: RegretFixture) -> None:
    """Spec section 8: their board is their ADP era, not ours."""
    assert fixture.season in fixture.era
    assert "ADP" in fixture.era
    assert len(fixture.provenance.split()) >= 20


@pytest.mark.parametrize("fixture", all_fixtures(), ids=FIXTURE_IDS)
def test_our_own_pick_stays_available_in_the_counterfactual(
    fixture: RegretFixture,
) -> None:
    """We are replacing our pick, so nobody took the player we took."""
    board = set(fixture.universe)
    assert fixture.actually_picked in fixture.available_at_next(board)


@pytest.mark.parametrize("fixture", all_fixtures(), ids=FIXTURE_IDS)
def test_a_player_never_drafted_is_available_the_whole_time(
    fixture: RegretFixture,
) -> None:
    """The recorded picks are the only ids that can be gone.

    A board carries players this room never took. Filtering the board
    rather than intersecting a drafted set is what keeps them available.
    """
    board = set(fixture.universe) | {"undrafted-in-this-room"}
    assert "undrafted-in-this-room" in fixture.board_at_pick(board)
    assert "undrafted-in-this-room" in fixture.available_at_next(board)


@pytest.mark.parametrize("fixture", all_fixtures(), ids=FIXTURE_IDS)
def test_the_board_shrinks_between_our_two_turns(fixture: RegretFixture) -> None:
    board = set(fixture.universe)
    at_pick = fixture.board_at_pick(board)
    at_next = fixture.available_at_next(board)
    assert at_next < at_pick
    assert at_pick - at_next == set(fixture.taken_between)


@pytest.mark.parametrize("fixture", all_fixtures(), ids=FIXTURE_IDS)
def test_the_gate_reads_the_record(fixture: RegretFixture) -> None:
    """The three outcomes, driven by ids off the fixture itself.

    Survivor recommended while a listed alternative was taken is the
    only failure. Everything else passes, because nothing was lost.
    """
    board = set(fixture.universe)
    fixtures = fixture.gate_fixtures(board)
    survivor = fixture.actually_picked
    taken = fixture.taken_between[0]

    both_ways = _propose(survivor, (taken,))
    assert regret(_ANY, both_ways, fixtures).outcome is GateOutcome.FAIL

    right_order = _propose(taken, (survivor,))
    assert regret(_ANY, right_order, fixtures).outcome is GateOutcome.PASS

    nothing_lost = _propose(survivor, ())
    assert regret(_ANY, nothing_lost, fixtures).outcome is GateOutcome.PASS


def test_a_fixture_that_cannot_fail_measures_nothing() -> None:
    """Every fixture has picks between our two turns, so every one can fail."""
    for fixture in all_fixtures():
        assert fixture.taken_between, fixture.name


def test_replay_refuses_a_round_with_no_next_pick() -> None:
    from replay import replay

    with pytest.raises(ValueError, match="no next user pick"):
        replay(
            name="x",
            draft="snake_redraft",
            draft_slot=2,
            round_no=15,
            provenance="x",
            era="x",
        )


def test_load_fixture_round_trips() -> None:
    one = load_fixture(SPECS[0]["name"])
    assert one.name == SPECS[0]["name"]
    assert isinstance(one.drafted_before, tuple)
