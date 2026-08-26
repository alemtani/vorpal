"""Fixed policies. Flags are set mechanically so the XOR gates can fire."""

from __future__ import annotations

from collections.abc import Callable

from vorpal.contracts import BoardRow, Flag, Payload, Proposal, Slot
from vorpal.errors import DataRefusal
from vorpal.evals.gates import ecr_best


def argmax_vols(payload: Payload) -> Proposal:
    """Pick `hint_argmax_vols`. Fall back to max vols if the hint is off the board."""
    rows = _require_board(payload)
    chosen = next(
        (row for row in rows if row.player_id == payload.hint_argmax_vols),
        None,
    )
    if chosen is None:
        chosen = max(rows, key=lambda row: (row.vols, -row.adp, row.player_id))
    return _proposal(payload, chosen, "argmax_vols")


def adp_follow(payload: Payload) -> Proposal:
    """Best available ADP (lowest number)."""
    rows = _require_board(payload)
    chosen = min(rows, key=lambda row: (row.adp, row.player_id))
    return _proposal(payload, chosen, "adp_follow")


def ecr_follow(payload: Payload) -> Proposal:
    """Best available overall ECR (lowest number). No ECR → argmax_vols."""
    rows = _require_board(payload)
    ranked = [row for row in rows if row.ecr is not None]
    if not ranked:
        return argmax_vols(payload)
    chosen = min(ranked, key=lambda row: (row.ecr, row.player_id))
    return _proposal(payload, chosen, "ecr_follow")


BASELINES: dict[str, Callable[[Payload], Proposal]] = {
    "argmax_vols": argmax_vols,
    "adp_follow": adp_follow,
    "ecr_follow": ecr_follow,
}


def choose_slot(row: BoardRow, payload: Payload) -> Slot:
    """First legal starter that still has a need, else first legal starter."""
    starters = [slot for slot in payload.config.slots if slot is not Slot.BN]
    legal = [slot for slot in starters if slot in row.legal_slots]
    for slot in legal:
        need = payload.state.needs.get(slot.value)
        if need is not None and need.filled < need.required:
            return slot
    if legal:
        return legal[0]
    if row.legal_slots:
        return row.legal_slots[0]
    return Slot.BN


def _require_board(payload: Payload) -> tuple[BoardRow, ...]:
    if not payload.board:
        raise DataRefusal("board is empty")
    return payload.board


def _proposal(payload: Payload, chosen: BoardRow, why: str) -> Proposal:
    flags: list[Flag] = []
    if payload.hint_argmax_vols and chosen.player_id != payload.hint_argmax_vols:
        flags.append(Flag.VOLS_DISSENT)
    best = ecr_best(payload)
    if best is not None and (chosen.ecr is None or chosen.ecr != best):
        flags.append(Flag.ECR_DISAGREE)
    rest = tuple(
        row.player_id for row in payload.board if row.player_id != chosen.player_id
    )
    return Proposal(
        player_id=chosen.player_id,
        alternatives=rest[:1],
        slot_filled=choose_slot(chosen, payload),
        coin_flip=False,
        why=why,
        flags=tuple(flags),
    )
