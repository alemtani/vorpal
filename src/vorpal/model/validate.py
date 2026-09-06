"""Validate a model response against the board before anyone sees it.

Nothing here raises. A rule the model broke is a `Violation`, and the caller
decides what it costs: the eval run scores it, draft night retries once and then
falls back to the calculator. The operator is on a pick timer — a validator that
exits 2 hands them nothing at the one moment they cannot recover.

A `Proposal` of None means the response could not be read as a proposal at all.
Anything else returns the proposal *and* whatever it violated.
"""

from __future__ import annotations

from vorpal.contracts import (
    PROPOSAL_KEYS,
    BoardRow,
    Flag,
    Payload,
    Proposal,
    Slot,
    Violation,
)


def validate_proposal(
    payload: Payload, raw: object
) -> tuple[Proposal | None, tuple[Violation, ...]]:
    """Read a raw model response. Never raises. See SPEC.md section 4."""
    if not isinstance(raw, dict):
        return None, (Violation("not_an_object", "model response is not an object"),)
    keys = set(raw)
    if keys != PROPOSAL_KEYS:
        missing = sorted(PROPOSAL_KEYS - keys)
        extra = sorted(keys - PROPOSAL_KEYS)
        if missing:
            return None, (
                Violation("missing_key", f"model response missing key: {missing}"),
            )
        return None, (Violation("extra_key", f"model response extra key: {extra}"),)

    violations: list[Violation] = []
    by_id = {row.player_id: row for row in payload.board}

    player_id = raw["player_id"]
    if not isinstance(player_id, str):
        return None, (Violation("bad_player_id", "player_id must be a string"),)
    rec = by_id.get(player_id)
    if rec is None:
        # Without a board row there is nothing left to check the rec against.
        return None, (
            Violation("rec_off_board", f"player_id {player_id} is not on the board"),
        )

    alternatives = raw["alternatives"]
    if not isinstance(alternatives, list) or not all(
        isinstance(item, str) for item in alternatives
    ):
        return None, (
            Violation("bad_alternatives", "alternatives must be a list of player ids"),
        )
    for alt in alternatives:
        if alt not in by_id:
            violations.append(
                Violation("alt_off_board", f"alternative {alt} is not on the board")
            )

    try:
        slot_filled = Slot(raw["slot_filled"])
    except ValueError:
        return None, (Violation("bad_slot", "slot_filled is not a legal slot"),)
    if slot_filled not in rec.legal_slots:
        violations.append(
            Violation("illegal_slot", f"slot_filled {slot_filled} is not legal for rec")
        )

    coin_flip = raw["coin_flip"]
    if not isinstance(coin_flip, bool):
        return None, (Violation("bad_coin_flip", "coin_flip must be a bool"),)
    why = raw["why"]
    if not isinstance(why, str):
        return None, (Violation("bad_why", "why must be a string"),)

    raw_flags = raw["flags"]
    if not isinstance(raw_flags, list):
        return None, (Violation("bad_flags", "flags must be a list"),)
    flags: list[Flag] = []
    for item in raw_flags:
        try:
            flags.append(Flag(item))
        except ValueError:
            return None, (Violation("unknown_flag", f"unknown flag: {item}"),)

    if player_id != payload.hint_argmax_vols and Flag.VOLS_DISSENT not in flags:
        violations.append(
            Violation(
                "silent_vols_dissent",
                "rec is not hint_argmax_vols and VOLS_DISSENT is not set",
            )
        )
    if Flag.ECR_DISAGREE not in flags:
        violations.extend(_check_ecr_floor(payload, rec))

    proposal = Proposal(
        player_id=player_id,
        alternatives=tuple(alternatives),
        slot_filled=slot_filled,
        coin_flip=coin_flip,
        why=why,
        flags=tuple(flags),
    )
    return proposal, tuple(violations)


def _check_ecr_floor(payload: Payload, rec: BoardRow) -> tuple[Violation, ...]:
    """Is the rec inside `ecr_best + margin`? SPEC.md section 4.

    The margin is one round of picks in the first half of the draft and two
    rounds after it, measured off the best ECR still on the board. It exists to
    catch a rec no expert would make.

    Skipped entirely when the model sets `ECR_DISAGREE` (checked by the caller).
    Consensus can be wrong about a specific room, not just a specific player —
    a table that is genuinely ignoring a position sitting on real value is a live
    signal no static CSV carries. The margin still catches *silent* deviation:
    a model that reaches this far without naming the disagreement gets no pass.

    Two escapes, both deliberate. A rec with no ECR is not checked at all —
    FantasyPros can be down, and SPEC says a missing ECR skips the ECR rule
    rather than failing it. And a rec whose `ecr_min` lands inside the ceiling
    passes on that instead: `ecr` is the consensus *median*, so a wide-spread
    player sits far outside the ceiling on the median while some experts rank
    him well inside it. That spread is the upside signal, and a floor that read
    only the median would throw out exactly the picks it is meant to surface.
    """
    if rec.ecr is None:
        return ()
    ranked = [row.ecr for row in payload.board if row.ecr is not None]
    ecr_best = min(ranked)
    total = payload.config.teams * payload.config.rounds
    first_half = payload.state.pick_no <= total // 2
    margin = payload.config.teams if first_half else 2 * payload.config.teams
    ceiling = ecr_best + margin
    if rec.ecr <= ceiling:
        return ()
    if rec.ecr_min is not None and rec.ecr_min <= ceiling:
        return ()
    return (
        Violation(
            "ecr_beyond_margin",
            f"rec ECR {rec.ecr} is beyond ecr_best {ecr_best} + margin {margin}",
        ),
    )
