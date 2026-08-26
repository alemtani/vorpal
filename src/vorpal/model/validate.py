"""Validate a model response against the board before anyone sees it."""

from __future__ import annotations

from vorpal.contracts import PROPOSAL_KEYS, BoardRow, Flag, Payload, Proposal, Slot
from vorpal.errors import PlatformError


def validate_proposal(payload: Payload, raw: object) -> Proposal:
    """Fail the call on any SPEC.md section 4 validation miss."""
    if not isinstance(raw, dict):
        raise PlatformError("model response is not an object")
    keys = set(raw)
    if keys != PROPOSAL_KEYS:
        missing = PROPOSAL_KEYS - keys
        extra = keys - PROPOSAL_KEYS
        if missing:
            raise PlatformError(f"model response missing key: {sorted(missing)}")
        raise PlatformError(f"model response extra key: {sorted(extra)}")
    player_id = raw["player_id"]
    if not isinstance(player_id, str):
        raise PlatformError("player_id must be a string")
    by_id = {row.player_id: row for row in payload.board}
    if player_id not in by_id:
        raise PlatformError(f"player_id {player_id} is not on the board")
    alternatives = raw["alternatives"]
    if not isinstance(alternatives, list) or not all(
        isinstance(item, str) for item in alternatives
    ):
        raise PlatformError("alternatives must be a list of player ids")
    for alt in alternatives:
        if alt not in by_id:
            raise PlatformError(f"alternative {alt} is not on the board")
    try:
        slot_filled = Slot(raw["slot_filled"])
    except ValueError as exc:
        raise PlatformError("slot_filled is not a legal slot") from exc
    rec = by_id[player_id]
    if slot_filled not in rec.legal_slots:
        raise PlatformError(f"slot_filled {slot_filled} is not legal for rec")
    coin_flip = raw["coin_flip"]
    if not isinstance(coin_flip, bool):
        raise PlatformError("coin_flip must be a bool")
    why = raw["why"]
    if not isinstance(why, str):
        raise PlatformError("why must be a string")
    raw_flags = raw["flags"]
    if not isinstance(raw_flags, list):
        raise PlatformError("flags must be a list")
    flags: list[Flag] = []
    for item in raw_flags:
        try:
            flags.append(Flag(item))
        except ValueError as exc:
            raise PlatformError(f"unknown flag: {item}") from exc
    if player_id != payload.hint_argmax_vols and Flag.VOLS_DISSENT not in flags:
        raise PlatformError("silent VOLS_DISSENT")
    _check_ecr_floor(payload, rec)
    return Proposal(
        player_id=player_id,
        alternatives=tuple(alternatives),
        slot_filled=slot_filled,
        coin_flip=coin_flip,
        why=why,
        flags=tuple(flags),
    )


def _check_ecr_floor(payload: Payload, rec: BoardRow) -> None:
    if rec.ecr is None:
        return
    ranked = [row.ecr for row in payload.board if row.ecr is not None]
    ecr_best = min(ranked)
    total = payload.config.teams * payload.config.rounds
    first_half = payload.state.pick_no <= total // 2
    margin = payload.config.teams if first_half else 2 * payload.config.teams
    ceiling = ecr_best + margin
    if rec.ecr <= ceiling:
        return
    if rec.ecr_min is not None and rec.ecr_min <= ceiling:
        return
    raise PlatformError(
        f"rec ECR {rec.ecr} is beyond ecr_best {ecr_best} + margin {margin}"
    )
