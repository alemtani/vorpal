"""Baseline policies produce Proposals with XOR flags set mechanically."""

from __future__ import annotations

from dataclasses import replace

from builders import board_row, default_board, make_payload, make_state

from vorpal.contracts import Flag, GateOutcome, Payload, Slot
from vorpal.errors import DataRefusal
from vorpal.evals import (
    BASELINES,
    adp_follow,
    argmax_vols,
    ecr_dissent,
    ecr_follow,
    schema,
    vols_dissent,
)
from vorpal.evals.baselines import choose_slot


def test_argmax_vols_picks_the_hint_and_does_not_dissent() -> None:
    payload = make_payload()
    proposal = argmax_vols(payload)
    assert proposal.player_id == "rb1"
    assert Flag.VOLS_DISSENT not in proposal.flags
    assert Flag.ECR_DISAGREE not in proposal.flags
    assert proposal.coin_flip is False
    assert schema(payload, proposal).outcome is GateOutcome.PASS
    assert vols_dissent(payload, proposal).outcome is GateOutcome.PASS
    assert ecr_dissent(payload, proposal).outcome is GateOutcome.PASS


def test_adp_follow_picks_lowest_adp() -> None:
    board = default_board()
    # wr1 has better ADP than the hint if we raise rb1's ADP.
    shuffled = (
        replace(board[0], adp=50.0),
        board[1],  # wr1 adp=3.0, best
        *board[2:],
    )
    payload = make_payload(board=shuffled, hint_argmax_vols="rb1")
    proposal = adp_follow(payload)
    assert proposal.player_id == "wr1"
    assert Flag.VOLS_DISSENT in proposal.flags
    assert Flag.ECR_DISAGREE in proposal.flags
    assert schema(payload, proposal).outcome is GateOutcome.PASS
    assert vols_dissent(payload, proposal).outcome is GateOutcome.PASS
    assert ecr_dissent(payload, proposal).outcome is GateOutcome.PASS


def test_ecr_follow_picks_lowest_ecr_across_positions() -> None:
    board = (
        board_row("wr-a", position="WR", ecr=5, vols=80.0, adp=2.0),
        board_row("rb-a", position="RB", ecr=3, vols=40.0, adp=6.0),
        board_row("wr-b", position="WR", ecr=8, vols=30.0, adp=12.0),
    )
    payload = make_payload(board=board, hint_argmax_vols="wr-a")
    proposal = ecr_follow(payload)
    assert proposal.player_id == "rb-a"
    assert Flag.VOLS_DISSENT in proposal.flags
    assert Flag.ECR_DISAGREE not in proposal.flags
    assert schema(payload, proposal).outcome is GateOutcome.PASS
    assert vols_dissent(payload, proposal).outcome is GateOutcome.PASS
    assert ecr_dissent(payload, proposal).outcome is GateOutcome.PASS


def test_ecr_follow_falls_back_when_no_board_ecr() -> None:
    board = (
        board_row("rb1", ecr=None, ecr_min=None, vols=80.0, adp=1.5),
        board_row("wr1", position="WR", ecr=None, ecr_min=None, vols=40.0, adp=3.0),
    )
    payload = make_payload(board=board)
    proposal = ecr_follow(payload)
    assert proposal.player_id == "rb1"
    assert Flag.ECR_DISAGREE not in proposal.flags


def test_argmax_vols_falls_back_to_max_vols_when_hint_is_off_board() -> None:
    payload = make_payload(hint_argmax_vols="ghost")
    proposal = argmax_vols(payload)
    assert proposal.player_id == "rb1"


def test_baselines_produce_valid_proposals_on_the_default_board() -> None:
    payload = make_payload()
    assert set(BASELINES) == {"argmax_vols", "adp_follow", "ecr_follow"}
    for name, policy in BASELINES.items():
        proposal = policy(payload)
        assert schema(payload, proposal).outcome is GateOutcome.PASS, name
        assert vols_dissent(payload, proposal).outcome is GateOutcome.PASS, name
        assert ecr_dissent(payload, proposal).outcome is GateOutcome.PASS, name
        assert proposal.alternatives
        assert all(
            alt in {row.player_id for row in payload.board}
            for alt in proposal.alternatives
        )


def test_empty_board_is_a_data_refusal() -> None:
    payload = make_payload(board=())
    for policy in BASELINES.values():
        try:
            policy(payload)
        except DataRefusal:
            continue
        raise AssertionError("expected DataRefusal on an empty board")


def test_choose_slot_prefers_an_unfilled_need() -> None:
    row = board_row("rb1")
    payload = make_payload(
        state=make_state(),
    )
    assert choose_slot(row, payload) is Slot.RB


def test_choose_slot_falls_back_to_first_legal_starter() -> None:
    row = board_row("k1", position="K", legal_slots=(Slot.K, Slot.BN))
    payload = make_payload()
    assert choose_slot(row, payload) is Slot.K


def test_choose_slot_uses_bn_when_nothing_else_is_legal() -> None:
    row = board_row("x", position="RB", legal_slots=(Slot.BN,))
    payload = make_payload()
    assert choose_slot(row, payload) is Slot.BN


def test_choose_slot_uses_bn_when_legal_slots_are_empty() -> None:
    row = board_row("x", position="RB", legal_slots=())
    payload = make_payload()
    assert choose_slot(row, payload) is Slot.BN


def test_choose_slot_falls_back_when_needs_are_filled() -> None:
    from vorpal.contracts import Need

    row = board_row("rb1")
    payload = make_payload(
        state=make_state(needs={"RB": Need(filled=2, required=2)}),
    )
    assert choose_slot(row, payload) is Slot.RB


def test_alternatives_omit_the_pick_and_stay_on_the_board() -> None:
    payload = make_payload()
    proposal = argmax_vols(payload)
    assert proposal.player_id not in proposal.alternatives
    board_ids = {row.player_id for row in payload.board}
    assert set(proposal.alternatives) <= board_ids


def test_adp_follow_breaks_ties_on_player_id(payload: Payload) -> None:
    board = (
        board_row("b", position="WR", adp=5.0, vols=10.0, ecr=8),
        board_row("a", position="RB", adp=5.0, vols=10.0, ecr=8),
    )
    tied = make_payload(board=board, hint_argmax_vols="b")
    assert adp_follow(tied).player_id == "a"
