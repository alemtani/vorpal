"""Every SPEC.md section 4 rule returns a violation. Nothing raises."""

from __future__ import annotations

import json
from pathlib import Path

from vorpal.contracts import (
    AdpVariant,
    Banner,
    BoardRow,
    DraftState,
    Flag,
    LeagueConfig,
    Need,
    Payload,
    RecentPick,
    Replacement,
    RosterPlayer,
    Slot,
    WeeklyCell,
)
from vorpal.model import validate_proposal

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "recorded_proposal.json"


def _row(
    player_id: str,
    *,
    position: str = "RB",
    vols: float,
    ecr: int | None = None,
    ecr_min: int | None = None,
    legal_slots: tuple[Slot, ...] | None = None,
) -> BoardRow:
    if legal_slots is None:
        legal_slots = (Slot.RB, Slot.FLEX) if position == "RB" else (Slot[position],)
    return BoardRow(
        player_id=player_id,
        name=player_id,
        position=position,
        points=vols + 100.0,
        vols=vols,
        delta_starter_points=1.0,
        adp=10.0,
        legal_slots=legal_slots,
        ecr=ecr,
        ecr_min=ecr_min,
        ecr_max=ecr,
        ecr_std=1.0 if ecr is not None else None,
    )


def _payload(
    *,
    pick_no: int = 48,
    teams: int = 12,
    rounds: int = 15,
    hint: str = "4866",
    board: tuple[BoardRow, ...] | None = None,
) -> Payload:
    if board is None:
        board = (
            _row("4866", vols=40.0, ecr=1, ecr_min=1),
            _row("7564", position="WR", vols=30.0, ecr=4, ecr_min=2),
            _row("4034", vols=20.0, ecr=20, ecr_min=18),
        )
    return Payload(
        config=LeagueConfig(
            teams=teams,
            rounds=rounds,
            slots=(Slot.QB, Slot.RB, Slot.WR, Slot.TE, Slot.FLEX, Slot.BN),
            scoring={"rec": 1.0},
            scoring_summary="PPR",
            banners=(Banner(code="board_capped", message="board is capped"),),
            slot=2,
            adp_variant=AdpVariant.PPR,
        ),
        state=DraftState(
            pick_no=pick_no,
            user_roster=(
                RosterPlayer(player_id="1", name="held", position="RB", bye=9),
            ),
            needs={"RB": Need(filled=0, required=2)},
            weekly=(WeeklyCell(week=1, starter_points=0.0, empty=(Slot.RB,)),),
            recent=(RecentPick(player_id="x", position="WR", pick_no=pick_no - 1),),
            next_user_pick=pick_no + 1,
            picks_until_next=1,
            between=(),
        ),
        replacement={"RB": Replacement(player_id="999", points=100.0)},
        hint_argmax_vols=hint,
        board=board,
    )


def _recorded() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _codes(payload_raw: object, payload=None) -> tuple[str, ...]:
    """Violation codes for a raw response against the default payload."""
    _, violations = validate_proposal(payload or _payload(), payload_raw)
    return tuple(violation.code for violation in violations)


def test_recorded_response_validates() -> None:
    proposal, violations = validate_proposal(_payload(), _recorded())
    assert violations == ()
    assert proposal is not None
    assert proposal.player_id == "4866"
    assert proposal.alternatives == ("7564",)
    assert proposal.slot_filled is Slot.RB
    assert proposal.coin_flip is False
    assert proposal.flags == (Flag.EMPTY_STARTER,)


def test_player_id_not_on_the_board_is_a_violation_with_no_proposal() -> None:
    raw = {**_recorded(), "player_id": "not-on-board"}
    proposal, violations = validate_proposal(_payload(), raw)
    assert proposal is None
    assert [v.code for v in violations] == ["rec_off_board"]
    assert "not on the board" in violations[0].message


def test_alternative_not_on_the_board_keeps_the_proposal() -> None:
    raw = {**_recorded(), "alternatives": ["not-on-board"]}
    proposal, violations = validate_proposal(_payload(), raw)
    assert proposal is not None
    assert proposal.player_id == "4866"
    assert [v.code for v in violations] == ["alt_off_board"]


def test_silent_vols_dissent_is_a_violation() -> None:
    raw = {**_recorded(), "player_id": "7564", "slot_filled": "WR", "flags": []}
    proposal, violations = validate_proposal(_payload(), raw)
    assert proposal is not None
    assert [v.code for v in violations] == ["silent_vols_dissent"]


def test_vols_dissent_with_the_flag_is_accepted() -> None:
    raw = {
        **_recorded(),
        "player_id": "7564",
        "slot_filled": "WR",
        "flags": ["VOLS_DISSENT"],
    }
    proposal, violations = validate_proposal(_payload(), raw)
    assert violations == ()
    assert proposal is not None
    assert Flag.VOLS_DISSENT in proposal.flags


def test_rec_beyond_ecr_best_plus_margin_violates_even_with_ecr_disagree() -> None:
    # first half, T=12, ecr_best=1, rec ecr=20, ecr_min=18
    raw = {
        **_recorded(),
        "player_id": "4034",
        "flags": ["VOLS_DISSENT", "ECR_DISAGREE"],
    }
    proposal, violations = validate_proposal(_payload(pick_no=48), raw)
    assert proposal is not None
    assert "ecr_beyond_margin" in [v.code for v in violations]


def test_ecr_min_escape_keeps_a_rec_inside_the_floor() -> None:
    board = (
        _row("4866", vols=40.0, ecr=1, ecr_min=1),
        _row("4034", vols=20.0, ecr=14, ecr_min=10),
    )
    raw = {
        **_recorded(),
        "player_id": "4034",
        "alternatives": [],
        "flags": ["VOLS_DISSENT", "ECR_DISAGREE"],
    }
    proposal, violations = validate_proposal(_payload(board=board), raw)
    assert violations == ()
    assert proposal is not None
    assert proposal.player_id == "4034"


def test_second_half_margin_is_two_rounds() -> None:
    board = (
        _row("4866", vols=40.0, ecr=1, ecr_min=1),
        _row("late", vols=5.0, ecr=26, ecr_min=26),
    )
    raw = {
        **_recorded(),
        "player_id": "late",
        "alternatives": [],
        "flags": ["VOLS_DISSENT", "ECR_DISAGREE"],
    }
    _, violations = validate_proposal(_payload(pick_no=91, board=board), raw)
    assert [v.code for v in violations] == ["ecr_beyond_margin"]
    board_ok = (
        _row("4866", vols=40.0, ecr=1, ecr_min=1),
        _row("late", vols=5.0, ecr=25, ecr_min=25),
    )
    _, inside = validate_proposal(_payload(pick_no=91, board=board_ok), raw)
    assert inside == ()


def test_missing_ecr_on_rec_skips_the_sanity_floor() -> None:
    board = (
        _row("4866", vols=40.0, ecr=1, ecr_min=1),
        _row("noecr", vols=10.0, ecr=None),
    )
    raw = {
        **_recorded(),
        "player_id": "noecr",
        "alternatives": [],
        "flags": ["VOLS_DISSENT"],
    }
    proposal, violations = validate_proposal(_payload(board=board), raw)
    assert violations == ()
    assert proposal is not None
    assert proposal.player_id == "noecr"


def test_why_missing_the_dissent_name_is_not_a_violation() -> None:
    """SPEC.md #20: `why` naming the dissent pick is a §5 eval-only
    contains-floor, never a section 4 violation. A miss must not retry or
    degrade draft night."""
    raw = {
        **_recorded(),
        "player_id": "7564",
        "slot_filled": "WR",
        "flags": ["VOLS_DISSENT", "ECR_DISAGREE"],
        "why": "better long-term value",
    }
    proposal, violations = validate_proposal(_payload(), raw)
    assert violations == ()
    assert proposal is not None
    assert proposal.why == "better long-term value"


def test_illegal_slot_filled_keeps_the_proposal() -> None:
    raw = {**_recorded(), "slot_filled": "QB"}
    proposal, violations = validate_proposal(_payload(), raw)
    assert proposal is not None
    assert [v.code for v in violations] == ["illegal_slot"]


def test_unreadable_responses_return_no_proposal() -> None:
    recorded = _recorded()
    missing = _recorded()
    del missing["why"]
    cases = {
        "not_an_object": ["4866"],
        "missing_key": missing,
        "extra_key": {**recorded, "survival": "likely"},
        "bad_player_id": {**recorded, "player_id": 4866},
        "bad_alternatives": {**recorded, "alternatives": "7564"},
        "bad_slot": {**recorded, "slot_filled": "NOPE"},
        "bad_coin_flip": {**recorded, "coin_flip": "yes"},
        "bad_why": {**recorded, "why": 1},
        "bad_flags": {**recorded, "flags": "EMPTY_STARTER"},
        "unknown_flag": {**recorded, "flags": ["NOT_A_FLAG"]},
    }
    for code, raw in cases.items():
        proposal, violations = validate_proposal(_payload(), raw)
        assert proposal is None, code
        assert [v.code for v in violations] == [code]


def test_alternatives_with_a_non_string_member_is_unreadable() -> None:
    raw = {**_recorded(), "alternatives": ["7564", 4034]}
    assert _codes(raw) == ("bad_alternatives",)


def test_violation_serialises_to_code_and_message() -> None:
    _, violations = validate_proposal(_payload(), ["4866"])
    assert violations[0].to_dict() == {
        "code": "not_an_object",
        "message": "model response is not an object",
    }


def test_one_response_can_carry_several_violations() -> None:
    raw = {
        **_recorded(),
        "player_id": "7564",
        "slot_filled": "QB",
        "alternatives": ["ghost"],
        "flags": [],
    }
    assert set(_codes(raw)) == {"alt_off_board", "illegal_slot", "silent_vols_dissent"}
