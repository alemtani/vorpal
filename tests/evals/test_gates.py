"""Each gate is binary. Missing input is NOT_PERFORMED, not a fail."""

from __future__ import annotations

from dataclasses import replace

from builders import board_row, make_payload, make_proposal, make_state

from vorpal.contracts import (
    Flag,
    Gate,
    GateOutcome,
    Payload,
    RosterPlayer,
    Slot,
)
from vorpal.evals import (
    GateFixtures,
    bye_hole,
    draft_margin,
    ecr_best,
    ecr_dissent,
    ecr_sanity,
    evaluate,
    golden_forbid,
    golden_require,
    regret,
    replay,
    schema,
    stability,
    vols_dissent,
    vols_invariant,
)


def _outcome(result, expected: GateOutcome) -> None:
    assert result.outcome is expected
    if expected is not GateOutcome.PASS:
        assert result.reason


class TestSchema:
    def test_pass(self, payload: Payload) -> None:
        result = schema(payload, make_proposal("rb1", alternatives=("wr1",)))
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.SCHEMA

    def test_fail_rec_not_on_board(self, payload: Payload) -> None:
        result = schema(payload, make_proposal("ghost"))
        _outcome(result, GateOutcome.FAIL)

    def test_fail_alt_not_on_board(self, payload: Payload) -> None:
        result = schema(payload, make_proposal("rb1", alternatives=("ghost",)))
        _outcome(result, GateOutcome.FAIL)

    def test_fail_illegal_slot(self, payload: Payload) -> None:
        result = schema(payload, make_proposal("rb1", slot_filled=Slot.QB))
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_without_proposal(self, payload: Payload) -> None:
        result = schema(payload, None)
        _outcome(result, GateOutcome.NOT_PERFORMED)


class TestGoldenForbid:
    def test_pass(self, payload: Payload) -> None:
        fixtures = GateFixtures(forbid=frozenset({"k1"}))
        result = golden_forbid(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.GOLDEN_FORBID

    def test_fail(self, payload: Payload) -> None:
        fixtures = GateFixtures(forbid=frozenset({"k1"}))
        rec = make_proposal("k1", slot_filled=Slot.K)
        result = golden_forbid(payload, rec, fixtures)
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_without_forbid_set(self, payload: Payload) -> None:
        result = golden_forbid(payload, make_proposal("rb1"), GateFixtures())
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_empty_forbid_set_is_performed_and_passes(self, payload: Payload) -> None:
        result = golden_forbid(
            payload, make_proposal("rb1"), GateFixtures(forbid=frozenset())
        )
        _outcome(result, GateOutcome.PASS)


class TestGoldenRequire:
    def test_pass_rec_in_require(self, payload: Payload) -> None:
        fixtures = GateFixtures(require=frozenset({"rb1", "wr1"}))
        result = golden_require(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.GOLDEN_REQUIRE

    def test_pass_alternative_in_require(self, payload: Payload) -> None:
        fixtures = GateFixtures(require=frozenset({"wr1"}))
        result = golden_require(
            payload, make_proposal("rb2", alternatives=("wr1",)), fixtures
        )
        _outcome(result, GateOutcome.PASS)

    def test_fail(self, payload: Payload) -> None:
        fixtures = GateFixtures(require=frozenset({"wr1"}))
        result = golden_require(
            payload, make_proposal("rb2", alternatives=("te1",)), fixtures
        )
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_without_require_set(self, payload: Payload) -> None:
        result = golden_require(payload, make_proposal("rb1"), None)
        _outcome(result, GateOutcome.NOT_PERFORMED)


class TestVolsDissent:
    def test_pass_agree_without_flag(self, payload: Payload) -> None:
        result = vols_dissent(payload, make_proposal("rb1"))
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.VOLS_DISSENT

    def test_pass_dissent_with_flag(self, payload: Payload) -> None:
        result = vols_dissent(payload, make_proposal("wr1", flags=(Flag.VOLS_DISSENT,)))
        _outcome(result, GateOutcome.PASS)

    def test_fail_agreeing_and_flagged(self, payload: Payload) -> None:
        result = vols_dissent(payload, make_proposal("rb1", flags=(Flag.VOLS_DISSENT,)))
        _outcome(result, GateOutcome.FAIL)

    def test_fail_silent_dissent(self, payload: Payload) -> None:
        result = vols_dissent(payload, make_proposal("wr1"))
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_without_hint(self, payload: Payload) -> None:
        result = vols_dissent(replace(payload, hint_argmax_vols=""), make_proposal())
        _outcome(result, GateOutcome.NOT_PERFORMED)


class TestEcrDissent:
    def test_pass_ecr_best_without_flag(self, payload: Payload) -> None:
        result = ecr_dissent(payload, make_proposal("rb1"))
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.ECR_DISSENT

    def test_pass_not_best_with_flag(self, payload: Payload) -> None:
        result = ecr_dissent(payload, make_proposal("wr1", flags=(Flag.ECR_DISAGREE,)))
        _outcome(result, GateOutcome.PASS)

    def test_fail_best_and_flagged(self, payload: Payload) -> None:
        result = ecr_dissent(payload, make_proposal("rb1", flags=(Flag.ECR_DISAGREE,)))
        _outcome(result, GateOutcome.FAIL)

    def test_fail_silent_disagree(self, payload: Payload) -> None:
        result = ecr_dissent(payload, make_proposal("wr1"))
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_when_no_board_ecr(self) -> None:
        board = (
            board_row("rb1", ecr=None, ecr_min=None, ecr_max=None, ecr_std=None),
            board_row(
                "wr1",
                position="WR",
                ecr=None,
                ecr_min=None,
                ecr_max=None,
                ecr_std=None,
            ),
        )
        payload = make_payload(board=board)
        result = ecr_dissent(payload, make_proposal("rb1"))
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_rec_without_ecr_is_not_ecr_best(self) -> None:
        board = (
            board_row("rb1", ecr=None, ecr_min=None),
            board_row("wr1", position="WR", ecr=5, ecr_min=3, vols=60.0),
        )
        payload = make_payload(board=board, hint_argmax_vols="wr1")
        silent = ecr_dissent(payload, make_proposal("rb1"))
        _outcome(silent, GateOutcome.FAIL)
        flagged = ecr_dissent(payload, make_proposal("rb1", flags=(Flag.ECR_DISAGREE,)))
        _outcome(flagged, GateOutcome.PASS)


class TestEcrSanity:
    def test_pass_within_margin(self, payload: Payload) -> None:
        # ecr_best=1, first-half margin=12, wr1 ecr=5
        result = ecr_sanity(payload, make_proposal("wr1"))
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.ECR_SANITY

    def test_pass_via_ecr_min_escape(self) -> None:
        board = (
            board_row("rb1", ecr=1, ecr_min=1),
            board_row(
                "wr1",
                position="WR",
                ecr=40,
                ecr_min=8,
                vols=60.0,
            ),
        )
        payload = make_payload(board=board)
        # ecr 40 > 1+12, but ecr_min 8 <= 13
        result = ecr_sanity(payload, make_proposal("wr1"))
        _outcome(result, GateOutcome.PASS)

    def test_fail_past_margin_and_min(self) -> None:
        board = (
            board_row("rb1", ecr=1, ecr_min=1),
            board_row(
                "k1",
                position="K",
                ecr=40,
                ecr_min=30,
                vols=5.0,
                legal_slots=(Slot.K, Slot.BN),
            ),
        )
        payload = make_payload(board=board)
        result = ecr_sanity(payload, make_proposal("k1", slot_filled=Slot.K))
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_when_rec_has_no_ecr(self) -> None:
        board = (
            board_row("rb1", ecr=1, ecr_min=1),
            board_row("wr1", position="WR", ecr=None, ecr_min=None, vols=60.0),
        )
        payload = make_payload(board=board)
        result = ecr_sanity(payload, make_proposal("wr1"))
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_margin_doubles_after_first_half(self) -> None:
        board = (
            board_row("rb1", ecr=1, ecr_min=1),
            board_row(
                "wr1",
                position="WR",
                ecr=20,
                ecr_min=20,
                vols=60.0,
            ),
        )
        early = make_payload(board=board, state=make_state(pick_no=90))
        late = make_payload(board=board, state=make_state(pick_no=91))
        # teams=12, rounds=15, half at pick 90. Early margin=12, late=24.
        # ecr 20 <= 1+12 is false; 20 <= 1+24 is true. ecr_min does not save early.
        _outcome(ecr_sanity(early, make_proposal("wr1")), GateOutcome.FAIL)
        _outcome(ecr_sanity(late, make_proposal("wr1")), GateOutcome.PASS)


class TestByeHole:
    def test_pass_when_rec_does_not_open_a_hole(self, payload: Payload) -> None:
        # Roster already has an RB; adding another RB with a covered bye does
        # not open a new empty startable slot versus a different-bye alt.
        rostered = (
            RosterPlayer(player_id="qb0", name="qb", position="QB", bye=10),
            RosterPlayer(player_id="rb0", name="rb", position="RB", bye=7),
            RosterPlayer(player_id="rbh", name="rb2", position="RB", bye=4),
            RosterPlayer(player_id="wr0", name="wr", position="WR", bye=6),
            RosterPlayer(player_id="wrh", name="wr2", position="WR", bye=8),
            RosterPlayer(player_id="wrf", name="wr3", position="WR", bye=3),
            RosterPlayer(player_id="te0", name="te", position="TE", bye=11),
            RosterPlayer(player_id="k0", name="k", position="K", bye=14),
            RosterPlayer(player_id="def0", name="d", position="DEF", bye=13),
        )
        payload = make_payload(state=make_state(user_roster=rostered))
        result = bye_hole(payload, make_proposal("wr1"))
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.BYE_HOLE

    def test_fail_when_rec_bye_opens_a_slot_an_alt_would_fill(self) -> None:
        # Empty WR starter. Rec is a WR on bye 9. wr1 (bye 5) would play week 9.
        payload = make_payload(
            state=make_state(
                user_roster=(
                    RosterPlayer(player_id="rb0", name="held-rb", position="RB", bye=7),
                )
            )
        )
        rec = board_row(
            "wr-bye9",
            position="WR",
            vols=55.0,
            adp=6.0,
            ecr=7,
            ecr_min=4,
            bye=9,
        )
        payload = replace(payload, board=payload.board + (rec,))
        result = bye_hole(
            payload,
            make_proposal("wr-bye9", alternatives=("wr1",), slot_filled=Slot.WR),
        )
        _outcome(result, GateOutcome.FAIL)

    def test_pass_when_no_different_bye_alternative_exists(self) -> None:
        board = (
            board_row("wr-a", position="WR", bye=9, ecr=5, vols=50.0),
            board_row("wr-b", position="WR", bye=9, ecr=8, vols=40.0, adp=10.0),
        )
        payload = make_payload(
            board=board,
            hint_argmax_vols="wr-a",
            state=make_state(user_roster=()),
        )
        result = bye_hole(
            payload, make_proposal("wr-a", alternatives=("wr-b",), slot_filled=Slot.WR)
        )
        _outcome(result, GateOutcome.PASS)

    def test_not_performed_when_rec_has_no_bye(self) -> None:
        board = (
            board_row("rb1", bye=None, ecr=1),
            board_row("wr1", position="WR", bye=5, ecr=5, vols=60.0),
        )
        payload = make_payload(board=board)
        result = bye_hole(payload, make_proposal("rb1"))
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_not_performed_when_rec_not_on_board(self, payload: Payload) -> None:
        result = bye_hole(payload, make_proposal("ghost"))
        _outcome(result, GateOutcome.NOT_PERFORMED)


class TestStability:
    def test_pass_three_of_five_match(self, payload: Payload) -> None:
        fixtures = GateFixtures(stability_ids=("rb1", "rb1", "wr1", "rb1", "te1"))
        result = stability(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.STABILITY

    def test_fail_when_no_id_reaches_three(self, payload: Payload) -> None:
        fixtures = GateFixtures(stability_ids=("rb1", "wr1", "rb2", "te1", "k1"))
        result = stability(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_on_coin_flip(self, payload: Payload) -> None:
        fixtures = GateFixtures(stability_ids=("rb1", "rb1", "rb1", "rb1", "rb1"))
        result = stability(payload, make_proposal("rb1", coin_flip=True), fixtures)
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_not_performed_without_five_ids(self, payload: Payload) -> None:
        fixtures = GateFixtures(stability_ids=("rb1", "rb1", "rb1"))
        result = stability(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_not_performed_without_fixture(self, payload: Payload) -> None:
        result = stability(payload, make_proposal("rb1"), None)
        _outcome(result, GateOutcome.NOT_PERFORMED)


class TestVolsInvariant:
    def test_pass_within_two_ranks(self, payload: Payload) -> None:
        fixtures = GateFixtures(replacement_rank_delta={"RB": 2, "WR": 0, "QB": -1})
        result = vols_invariant(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.VOLS_INVARIANT

    def test_fail_when_a_position_moves_more_than_two(self, payload: Payload) -> None:
        fixtures = GateFixtures(replacement_rank_delta={"RB": 3})
        result = vols_invariant(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.FAIL)

    def test_fail_on_negative_move_past_two(self, payload: Payload) -> None:
        fixtures = GateFixtures(replacement_rank_delta={"TE": -4})
        result = vols_invariant(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_without_deltas(self, payload: Payload) -> None:
        result = vols_invariant(payload, make_proposal("rb1"), GateFixtures())
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_empty_delta_map_is_performed_and_passes(self, payload: Payload) -> None:
        result = vols_invariant(
            payload, make_proposal("rb1"), GateFixtures(replacement_rank_delta={})
        )
        _outcome(result, GateOutcome.PASS)


class TestRegret:
    def test_pass_when_rec_was_gone_by_next_pick(self, payload: Payload) -> None:
        fixtures = GateFixtures(available_at_next=frozenset({"wr1", "te1"}))
        result = regret(payload, make_proposal("rb1", alternatives=("wr1",)), fixtures)
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.REGRET

    def test_pass_when_rec_and_alts_all_survived(self, payload: Payload) -> None:
        fixtures = GateFixtures(available_at_next=frozenset({"rb1", "wr1"}))
        result = regret(payload, make_proposal("rb1", alternatives=("wr1",)), fixtures)
        _outcome(result, GateOutcome.PASS)

    def test_fail_when_rec_survived_and_an_alt_did_not(self, payload: Payload) -> None:
        fixtures = GateFixtures(available_at_next=frozenset({"rb1", "te1"}))
        result = regret(payload, make_proposal("rb1", alternatives=("wr1",)), fixtures)
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_without_completed_draft(self, payload: Payload) -> None:
        result = regret(payload, make_proposal("rb1"), None)
        _outcome(result, GateOutcome.NOT_PERFORMED)


class TestReplay:
    def test_pass_when_policy_lineup_meets_user(self, payload: Payload) -> None:
        fixtures = GateFixtures(
            dated_points={"rb1": 200.0, "wr1": 180.0, "rb0": 150.0},
            user_lineup=("rb0", "wr1"),
            policy_lineup=("rb1", "wr1"),
        )
        result = replay(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.PASS)
        assert result.gate is Gate.REPLAY

    def test_pass_on_equal_sums(self, payload: Payload) -> None:
        fixtures = GateFixtures(
            dated_points={"a": 10.0, "b": 10.0},
            user_lineup=("a",),
            policy_lineup=("b",),
        )
        result = replay(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.PASS)

    def test_fail_when_policy_lineup_is_worse(self, payload: Payload) -> None:
        fixtures = GateFixtures(
            dated_points={"rb1": 100.0, "wr1": 180.0, "rb0": 150.0},
            user_lineup=("wr1", "rb0"),
            policy_lineup=("rb1",),
        )
        result = replay(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.FAIL)

    def test_not_performed_without_dated_file(self, payload: Payload) -> None:
        result = replay(payload, make_proposal("rb1"), GateFixtures())
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_not_performed_when_a_lineup_is_missing(self, payload: Payload) -> None:
        fixtures = GateFixtures(
            dated_points={"rb1": 10.0},
            user_lineup=("rb1",),
            policy_lineup=None,
        )
        result = replay(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.NOT_PERFORMED)

    def test_missing_dated_player_counts_as_zero(self, payload: Payload) -> None:
        fixtures = GateFixtures(
            dated_points={"rb1": 50.0},
            user_lineup=("ghost",),
            policy_lineup=("rb1",),
        )
        result = replay(payload, make_proposal("rb1"), fixtures)
        _outcome(result, GateOutcome.PASS)


class TestEvaluateAndHelpers:
    def test_evaluate_runs_all_eleven_gates(self) -> None:
        rostered = (
            RosterPlayer(player_id="qb0", name="qb", position="QB", bye=10),
            RosterPlayer(player_id="rb0", name="rb", position="RB", bye=7),
            RosterPlayer(player_id="rbh", name="rb2", position="RB", bye=4),
            RosterPlayer(player_id="wr0", name="wr", position="WR", bye=6),
            RosterPlayer(player_id="wrh", name="wr2", position="WR", bye=8),
            RosterPlayer(player_id="wrf", name="wr3", position="WR", bye=3),
            RosterPlayer(player_id="te0", name="te", position="TE", bye=11),
            RosterPlayer(player_id="k0", name="k", position="K", bye=14),
            RosterPlayer(player_id="def0", name="d", position="DEF", bye=13),
        )
        payload = make_payload(state=make_state(user_roster=rostered))
        fixtures = GateFixtures(
            forbid=frozenset({"k1"}),
            require=frozenset({"rb1"}),
            stability_ids=("rb1", "rb1", "rb1", "wr1", "te1"),
            replacement_rank_delta={"RB": 0},
            available_at_next=frozenset({"wr1"}),
            dated_points={"rb1": 10.0, "held": 1.0},
            user_lineup=("held",),
            policy_lineup=("rb1",),
        )
        results = evaluate(payload, make_proposal("rb1"), fixtures)
        assert len(results) == 11
        assert [row.gate for row in results] == list(Gate)
        assert all(row.outcome is GateOutcome.PASS for row in results)

    def test_evaluate_skips_every_gate_without_a_proposal(
        self, payload: Payload
    ) -> None:
        results = evaluate(payload, None)
        assert len(results) == 11
        assert all(row.outcome is GateOutcome.NOT_PERFORMED for row in results)

    def test_ecr_best_is_min_across_positions_not_positional(self) -> None:
        board = (
            board_row("wr-a", position="WR", ecr=5, vols=50.0),
            board_row("wr-b", position="WR", ecr=8, vols=40.0, adp=12.0),
            board_row("rb-a", position="RB", ecr=3, vols=45.0, adp=6.0),
        )
        payload = make_payload(board=board, hint_argmax_vols="wr-a")
        assert ecr_best(payload) == 3

    def test_draft_margin_is_teams_then_two_teams(self) -> None:
        early = make_payload(state=make_state(pick_no=1))
        late = make_payload(state=make_state(pick_no=180))
        midpoint = make_payload(state=make_state(pick_no=90))
        after = make_payload(state=make_state(pick_no=91))
        assert draft_margin(early) == 12
        assert draft_margin(midpoint) == 12
        assert draft_margin(after) == 24
        assert draft_margin(late) == 24

    def test_ecr_best_none_when_board_has_no_ranks(self) -> None:
        board = (board_row("rb1", ecr=None, ecr_min=None),)
        assert ecr_best(make_payload(board=board)) is None
