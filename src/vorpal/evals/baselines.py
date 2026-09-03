"""Three dumb policies to measure the model against.

Each is a one-line rule with no judgment in it: take our VOLS pick, take
the best ADP, take the best ECR. They run against every fixture the model
does.

The point is the comparison. `argmax_vols` passes most gates by
construction, and that is intended — a gate where the model scores the
same as a one-line rule is not measuring anything the rule does not
already give us for free. See `report.NO_DISCRIMINATING_POWER`.

Flags are set mechanically here, by comparing the pick against the hint
and against ecr_best. A baseline is not reasoning about dissent; it just
never lies about it, so the XOR gates score it fairly.
"""

from __future__ import annotations

from collections.abc import Callable

from vorpal.contracts import BoardRow, Flag, Payload, Proposal, Slot
from vorpal.errors import DataRefusal
from vorpal.evals.gates import DISSENT_LABEL, ecr_best


def argmax_vols(payload: Payload) -> Proposal:
    """Take the player our own VOLS math likes best.

    Normally that is `hint_argmax_vols` straight from the payload. The
    fallback recomputes it when the hint names someone already drafted,
    breaking ties toward the later ADP — the player the room rates lower,
    whom we are therefore less likely to get back.
    """
    rows = _require_board(payload)
    chosen = next(
        (row for row in rows if row.player_id == payload.hint_argmax_vols),
        None,
    )
    if chosen is None:
        chosen = max(rows, key=lambda row: (row.vols, -row.adp, row.player_id))
    return _proposal(payload, chosen, "argmax_vols")


def adp_follow(payload: Payload) -> Proposal:
    """Take whoever the draft room rates highest. Pure herd-following."""
    rows = _require_board(payload)
    chosen = min(rows, key=lambda row: (row.adp, row.player_id))
    return _proposal(payload, chosen, "adp_follow")


def ecr_follow(payload: Payload) -> Proposal:
    """Take whoever the experts rank highest, ignoring our own math.

    Falls back to `argmax_vols` when no one left has a ranking at all,
    which happens deep in a draft.
    """
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
    """Where this player would start.

    Prefer a slot we still need filled, so a baseline does not fail the
    schema gate on a technicality. Falls back to any legal starter, then
    bench.
    """
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
        note = _dissent_note(payload, payload.hint_argmax_vols, Flag.VOLS_DISSENT)
        why = f"{why} ({note})"
    best = ecr_best(payload)
    if best is not None and (chosen.ecr is None or chosen.ecr != best):
        flags.append(Flag.ECR_DISAGREE)
        ecr_row = next((row for row in payload.board if row.ecr == best), None)
        if ecr_row is not None:
            note = _dissent_note(payload, ecr_row.player_id, Flag.ECR_DISAGREE)
            why = f"{why} ({note})"
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


def _dissent_note(payload: Payload, player_id: str, flag: Flag) -> str:
    """`why` text naming the dissented-from player, in SYSTEM's form.

    A baseline is not reasoning about the dissent, only satisfying the
    eval's contains-floor (`why_contains_floor`, #20) mechanically — id and
    name plus the label that matches the flag it set, `VOLS pick` or `ECR
    pick` — so the gate measures the model, not a dummy string on a
    one-line rule. Same spirit as the XOR flags: never claim a dissent the
    policy did not make.
    """
    row = next((row for row in payload.board if row.player_id == player_id), None)
    named = player_id if row is None else f"{row.player_id} {row.name}"
    return f"{named} is the {DISSENT_LABEL[flag]}"
