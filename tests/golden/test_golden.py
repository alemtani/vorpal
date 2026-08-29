"""The golden set, checked two ways.

First that each case is well formed: the ids it forbids and requires are
really on its board, the VOLS hint really is the top row, the verdict is
written down. A case that lies about its own board measures nothing.

Second that the two golden gates agree with the human. Take the
forbidden player and the forbid gate fails; take a required player and
both gates pass. That is the gate and the case checking each other,
which is as close to a test of a hand-written verdict as we can get
without a second human.

Marked `golden`: a failure here is a claim about a board, not a bug in
the gate code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from cases import CASES, CASES_BY_NAME, SITUATIONS, GoldenCase, snake_pick

from vorpal.contracts import Flag, Gate, GateOutcome, Proposal
from vorpal.evals import argmax_vols, bye_hole, evaluate, golden_forbid, golden_require

pytestmark = pytest.mark.golden

CASE_IDS = [case.name for case in CASES]
README = Path(__file__).resolve().parent / "README.md"


def _propose(case: GoldenCase, player_id: str, *, alternatives=()) -> Proposal:
    """A proposal naming `player_id`, in the first slot that player can start."""
    rec = next(row for row in case.payload.board if row.player_id == player_id)
    return Proposal(
        player_id=player_id,
        alternatives=tuple(alternatives),
        slot_filled=rec.legal_slots[0],
        coin_flip=False,
        why="test",
        flags=(),
    )


def _outcome(results, gate: Gate) -> GateOutcome:
    return next(result.outcome for result in results if result.gate is gate)


def _not_required(case: GoldenCase) -> str:
    """Any board row the case does not require. Two late cases require or
    forbid every row they carry, so this may be a forbidden player."""
    return next(
        row.player_id for row in case.payload.board if row.player_id not in case.require
    )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_case_is_well_formed(case: GoldenCase) -> None:
    on_board = {row.player_id for row in case.payload.board}
    assert case.forbid <= on_board, "a forbidden player is not on the board"
    assert case.require <= on_board, "a required player is not on the board"
    assert not (case.forbid & case.require), "a player is both forbidden and required"
    assert case.require, "a case with an empty require set asserts nothing"
    assert case.payload.hint_argmax_vols in on_board
    assert case.situation in SITUATIONS
    assert case.why.endswith("."), "the verdict is one written sentence"
    assert len(case.why.split()) >= 15, "one sentence, but say why"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_hint_really_is_the_top_vols_row(case: GoldenCase) -> None:
    """The hint is a calculator answer, so it has to be the calculator's answer.

    If a case set a hint that is not the VOLS argmax, the `argmax_vols`
    baseline would score against a board that never existed.
    """
    top = max(case.payload.board, key=lambda row: row.vols)
    assert case.payload.hint_argmax_vols == top.player_id


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_payload_serialises(case: GoldenCase) -> None:
    body = case.payload.to_dict()
    assert set(body) == {"config", "state", "replacement", "hint_argmax_vols", "board"}
    seat_known = case.payload.config.slot is not None
    assert ("next_user_pick" in body["state"]) is seat_known


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_forbidden_picks_fail_the_forbid_gate(case: GoldenCase) -> None:
    for player_id in sorted(case.forbid):
        result = golden_forbid(case.payload, _propose(case, player_id), case.fixtures())
        assert result.outcome is GateOutcome.FAIL, player_id


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_required_picks_pass_both_golden_gates(case: GoldenCase) -> None:
    for player_id in sorted(case.require):
        proposal = _propose(case, player_id)
        results = evaluate(case.payload, proposal, case.fixtures())
        assert _outcome(results, Gate.GOLDEN_FORBID) is GateOutcome.PASS, player_id
        assert _outcome(results, Gate.GOLDEN_REQUIRE) is GateOutcome.PASS, player_id
        assert _outcome(results, Gate.SCHEMA) is GateOutcome.PASS, player_id


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_naming_nobody_required_fails_the_require_gate(case: GoldenCase) -> None:
    other = _not_required(case)
    result = golden_require(case.payload, _propose(case, other), case.fixtures())
    assert result.outcome is GateOutcome.FAIL


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_a_required_alternative_is_enough(case: GoldenCase) -> None:
    """The require gate asks what the model saw, not how it ranked it."""
    wanted = sorted(case.require)[0]
    other = _not_required(case)
    proposal = _propose(case, other, alternatives=(wanted,))
    assert golden_require(case.payload, proposal, case.fixtures()).outcome is (
        GateOutcome.PASS
    )


def test_every_sampler_hostile_shape_has_a_case() -> None:
    """The five shapes `hostile_states()` names all appear in the set."""
    covered = {case.situation for case in CASES}
    assert {
        "empty_starter_late",
        "bye_stack",
        "position_run",
        "vols_compressed",
        "seat_unknown",
    } <= covered


def test_bye_hole_gate_cannot_see_a_stack() -> None:
    """A finding, pinned as a test: `bye_hole` fails both picks in this case.

    The gate compares alternatives only in the recommendation's own bye
    week. One receiver slot is empty and one receiver is rostered, so
    whichever receiver we add, the week he is off leaves that slot empty
    and the other receiver would have filled it. The comparison is
    symmetric and the gate fails either way.

    That is why the case is in the golden set. The human verdict reads
    the whole vector: the quarterback, a running back and the rostered
    receiver are already off in week 9, so the bye-9 receiver buys a
    fourth hole in a week that is already the worst of the season, and
    the bye-5 receiver buys one hole in a week that is otherwise full.
    `bye_hole` sees one week at a time and cannot make that comparison.
    """
    case = CASES_BY_NAME["bye_stack"]
    clash = bye_hole(case.payload, _propose(case, "wr-bye-clash"))
    clear = bye_hole(case.payload, _propose(case, "wr-bye-clear"))
    assert clash.outcome is GateOutcome.FAIL
    assert clear.outcome is GateOutcome.FAIL
    assert clash.reason == clear.reason


def test_argmax_vols_does_not_pass_the_whole_set() -> None:
    """A set the calculator aces has no discriminating power (spec section 5).

    Named here rather than counted, so a case that stops separating the
    two shows up as a failure in this file instead of as a quiet drop in
    a report six months from now.
    """
    failed = set()
    for case in CASES:
        proposal = argmax_vols(case.payload)
        results = evaluate(case.payload, proposal, case.fixtures())
        forbid = _outcome(results, Gate.GOLDEN_FORBID)
        require = _outcome(results, Gate.GOLDEN_REQUIRE)
        if GateOutcome.FAIL in (forbid, require):
            failed.add(case.name)
    assert failed == {
        "third_te_while_wr_empty",
        "bye_stack",
        "empty_starter_late",
    }


def test_readme_records_the_real_size() -> None:
    """The honest count in the README is checked, not trusted."""
    text = README.read_text()
    stated = int(re.search(r"\*\*(\d+) cases\*\*", text).group(1))
    assert stated == len(CASES)
    for case in CASES:
        assert case.name in text, "every case is listed in the README"


def test_snake_pick_turns_the_seat_into_a_pick_number() -> None:
    assert snake_pick(12, 4, 1) == 4
    assert snake_pick(12, 4, 2) == 21
    assert snake_pick(12, 4, 3) == 28
    assert snake_pick(10, 8, 3) == 28


def test_flags_are_not_part_of_a_golden_verdict() -> None:
    """Golden is set membership. The flag gates are separate and stay so."""
    case = CASES_BY_NAME["kicker_round_two"]
    noisy = Proposal(
        player_id="rb-a",
        alternatives=(),
        slot_filled=case.payload.board[0].legal_slots[0],
        coin_flip=False,
        why="test",
        flags=(Flag.UPSIDE, Flag.POSITION_RUN),
    )
    results = evaluate(case.payload, noisy, case.fixtures())
    assert _outcome(results, Gate.GOLDEN_FORBID) is GateOutcome.PASS
    assert _outcome(results, Gate.GOLDEN_REQUIRE) is GateOutcome.PASS
