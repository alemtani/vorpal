"""Every SPEC.md section 4 validation failure fails the call."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from vorpal.errors import PlatformError
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


def test_recorded_response_validates() -> None:
    proposal = validate_proposal(_payload(), _recorded())
    assert proposal.player_id == "4866"
    assert proposal.alternatives == ("7564",)
    assert proposal.slot_filled is Slot.RB
    assert proposal.coin_flip is False
    assert proposal.flags == (Flag.EMPTY_STARTER,)


def test_player_id_not_on_the_board_fails_the_call() -> None:
    raw = {**_recorded(), "player_id": "not-on-board"}
    with pytest.raises(PlatformError, match="not on the board"):
        validate_proposal(_payload(), raw)


def test_alternative_not_on_the_board_fails_the_call() -> None:
    raw = {**_recorded(), "alternatives": ["not-on-board"]}
    with pytest.raises(PlatformError, match="not on the board"):
        validate_proposal(_payload(), raw)


def test_silent_vols_dissent_fails_the_call() -> None:
    raw = {**_recorded(), "player_id": "7564", "slot_filled": "WR", "flags": []}
    with pytest.raises(PlatformError, match="VOLS_DISSENT"):
        validate_proposal(_payload(), raw)


def test_vols_dissent_with_the_flag_is_accepted() -> None:
    raw = {
        **_recorded(),
        "player_id": "7564",
        "slot_filled": "WR",
        "flags": ["VOLS_DISSENT"],
    }
    proposal = validate_proposal(_payload(), raw)
    assert Flag.VOLS_DISSENT in proposal.flags


def test_rec_beyond_ecr_best_plus_margin_fails_even_with_ecr_disagree() -> None:
    # first half, T=12, ecr_best=1, rec ecr=14, ecr_min=14
    raw = {
        **_recorded(),
        "player_id": "4034",
        "flags": ["VOLS_DISSENT", "ECR_DISAGREE"],
    }
    with pytest.raises(PlatformError, match="ECR"):
        validate_proposal(_payload(pick_no=48), raw)


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
    proposal = validate_proposal(_payload(board=board), raw)
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
    with pytest.raises(PlatformError, match="ECR"):
        validate_proposal(_payload(pick_no=91, board=board), raw)
    inside = {**raw, "player_id": "late"}
    board_ok = (
        _row("4866", vols=40.0, ecr=1, ecr_min=1),
        _row("late", vols=5.0, ecr=25, ecr_min=25),
    )
    validate_proposal(_payload(pick_no=91, board=board_ok), inside)


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
    proposal = validate_proposal(_payload(board=board), raw)
    assert proposal.player_id == "noecr"


def test_unknown_flag_fails_the_call() -> None:
    raw = {**_recorded(), "flags": ["NOT_A_FLAG"]}
    with pytest.raises(PlatformError, match="flag"):
        validate_proposal(_payload(), raw)


def test_missing_required_key_fails_the_call() -> None:
    raw = _recorded()
    del raw["why"]
    with pytest.raises(PlatformError, match="why"):
        validate_proposal(_payload(), raw)


def test_extra_key_fails_the_call() -> None:
    raw = {**_recorded(), "survival": "likely"}
    with pytest.raises(PlatformError, match="key"):
        validate_proposal(_payload(), raw)


def test_illegal_slot_filled_fails_the_call() -> None:
    raw = {**_recorded(), "slot_filled": "QB"}
    with pytest.raises(PlatformError, match="slot"):
        validate_proposal(_payload(), raw)


def test_coin_flip_must_be_bool() -> None:
    raw = {**_recorded(), "coin_flip": "yes"}
    with pytest.raises(PlatformError, match="coin_flip"):
        validate_proposal(_payload(), raw)


def test_non_object_response_fails_the_call() -> None:
    with pytest.raises(PlatformError, match="object"):
        validate_proposal(_payload(), ["4866"])


def test_player_id_must_be_a_string() -> None:
    raw = {**_recorded(), "player_id": 4866}
    with pytest.raises(PlatformError, match="player_id"):
        validate_proposal(_payload(), raw)


def test_alternatives_must_be_a_list_of_ids() -> None:
    raw = {**_recorded(), "alternatives": "7564"}
    with pytest.raises(PlatformError, match="alternatives"):
        validate_proposal(_payload(), raw)


def test_unknown_slot_filled_fails_the_call() -> None:
    raw = {**_recorded(), "slot_filled": "NOPE"}
    with pytest.raises(PlatformError, match="slot"):
        validate_proposal(_payload(), raw)


def test_why_must_be_a_string() -> None:
    raw = {**_recorded(), "why": 1}
    with pytest.raises(PlatformError, match="why"):
        validate_proposal(_payload(), raw)


def test_flags_must_be_a_list() -> None:
    raw = {**_recorded(), "flags": "EMPTY_STARTER"}
    with pytest.raises(PlatformError, match="flags"):
        validate_proposal(_payload(), raw)
