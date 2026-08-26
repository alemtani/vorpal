"""The eleven gates. Each is binary. A missing input is NOT_PERFORMED."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from vorpal.contracts import (
    BoardRow,
    Flag,
    Gate,
    GateOutcome,
    GateResult,
    Payload,
    Proposal,
    RosterPlayer,
    Slot,
)
from vorpal.evals._lineup import empty_startable_slots, legal_slots_for_position
from vorpal.evals.types import GateFixtures


def draft_margin(payload: Payload) -> int:
    """Teams in the first half of the draft, else two times teams.

    First half is `pick_no * 2 <= teams * rounds`. One round of slack
    early, two late.
    """
    teams = payload.config.teams
    total = teams * payload.config.rounds
    if payload.state.pick_no * 2 <= total:
        return teams
    return 2 * teams


def ecr_best(payload: Payload) -> int | None:
    """Minimum overall ECR among board players that have one.

    Not a positional list: min across every row, whatever position.
    """
    ranks = [row.ecr for row in payload.board if row.ecr is not None]
    if not ranks:
        return None
    return min(ranks)


def schema(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del fixtures
    missing = _need_proposal(Gate.SCHEMA, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    ids = {row.player_id for row in payload.board}
    if proposal.player_id not in ids:
        return _fail(Gate.SCHEMA, "rec not on board")
    if any(alt not in ids for alt in proposal.alternatives):
        return _fail(Gate.SCHEMA, "alternative not on board")
    rec = _row(payload, proposal.player_id)
    assert rec is not None
    if proposal.slot_filled not in rec.legal_slots:
        return _fail(Gate.SCHEMA, "slot_filled is not legal for rec")
    return _pass(Gate.SCHEMA)


def golden_forbid(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del payload
    missing = _need_proposal(Gate.GOLDEN_FORBID, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    forbid = _fx(fixtures).forbid
    if forbid is None:
        return _skip(Gate.GOLDEN_FORBID, "no forbid set")
    if proposal.player_id in forbid:
        return _fail(Gate.GOLDEN_FORBID, "rec is in the forbid set")
    return _pass(Gate.GOLDEN_FORBID)


def golden_require(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del payload
    missing = _need_proposal(Gate.GOLDEN_REQUIRE, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    require = _fx(fixtures).require
    if require is None:
        return _skip(Gate.GOLDEN_REQUIRE, "no require set")
    candidates = (proposal.player_id, *proposal.alternatives)
    if any(player_id in require for player_id in candidates):
        return _pass(Gate.GOLDEN_REQUIRE)
    return _fail(Gate.GOLDEN_REQUIRE, "rec and alternatives miss the require set")


def vols_dissent(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del fixtures
    missing = _need_proposal(Gate.VOLS_DISSENT, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    if payload.hint_argmax_vols == "":
        return _skip(Gate.VOLS_DISSENT, "no hint_argmax_vols")
    agree = proposal.player_id == payload.hint_argmax_vols
    flagged = Flag.VOLS_DISSENT in proposal.flags
    if agree ^ flagged:
        return _pass(Gate.VOLS_DISSENT)
    if agree:
        return _fail(Gate.VOLS_DISSENT, "agreed with the hint and set VOLS_DISSENT")
    return _fail(Gate.VOLS_DISSENT, "silent VOLS dissent")


def ecr_dissent(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del fixtures
    missing = _need_proposal(Gate.ECR_DISSENT, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    best = ecr_best(payload)
    if best is None:
        return _skip(Gate.ECR_DISSENT, "no ECR on the board")
    rec = _row(payload, proposal.player_id)
    agree = rec is not None and rec.ecr is not None and rec.ecr == best
    flagged = Flag.ECR_DISAGREE in proposal.flags
    if agree ^ flagged:
        return _pass(Gate.ECR_DISSENT)
    if agree:
        return _fail(Gate.ECR_DISSENT, "picked ecr_best and set ECR_DISAGREE")
    return _fail(Gate.ECR_DISSENT, "silent ECR dissent")


def ecr_sanity(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del fixtures
    missing = _need_proposal(Gate.ECR_SANITY, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    rec = _row(payload, proposal.player_id)
    if rec is None or rec.ecr is None:
        return _skip(Gate.ECR_SANITY, "no ECR on rec")
    best = ecr_best(payload)
    assert best is not None
    limit = best + draft_margin(payload)
    if rec.ecr <= limit:
        return _pass(Gate.ECR_SANITY)
    if rec.ecr_min is not None and rec.ecr_min <= limit:
        return _pass(Gate.ECR_SANITY)
    return _fail(Gate.ECR_SANITY, "rec is past ecr_best + margin")


def bye_hole(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del fixtures
    missing = _need_proposal(Gate.BYE_HOLE, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    rec = _row(payload, proposal.player_id)
    if rec is None:
        return _skip(Gate.BYE_HOLE, "rec not on board")
    if rec.bye is None:
        return _skip(Gate.BYE_HOLE, "rec has no bye")
    alts = tuple(
        row
        for row in payload.board
        if row.player_id != rec.player_id and row.bye is not None and row.bye != rec.bye
    )
    if not alts:
        return _pass(Gate.BYE_HOLE)
    rec_empty = Counter(_empties_with(payload, rec, rec.bye))
    for alt in alts:
        alt_empty = Counter(_empties_with(payload, alt, rec.bye))
        if rec_empty - alt_empty:
            return _fail(
                Gate.BYE_HOLE,
                "rec opens an empty startable slot an alt would fill",
            )
    return _pass(Gate.BYE_HOLE)


def stability(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del payload
    missing = _need_proposal(Gate.STABILITY, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    if proposal.coin_flip:
        return _skip(Gate.STABILITY, "coin_flip")
    ids = _fx(fixtures).stability_ids
    if ids is None or len(ids) != 5:
        return _skip(Gate.STABILITY, "need five identical-payload player_ids")
    top = max(Counter(ids).values())
    if top >= 3:
        return _pass(Gate.STABILITY)
    return _fail(Gate.STABILITY, "fewer than 3 of 5 share a player_id")


def vols_invariant(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del payload
    missing = _need_proposal(Gate.VOLS_INVARIANT, proposal)
    if missing is not None:
        return missing
    delta = _fx(fixtures).replacement_rank_delta
    if delta is None:
        return _skip(Gate.VOLS_INVARIANT, "no replacement-rank deltas")
    for position, move in delta.items():
        if abs(move) > 2:
            return _fail(
                Gate.VOLS_INVARIANT,
                f"{position} replacement rank moved by {move}",
            )
    return _pass(Gate.VOLS_INVARIANT)


def regret(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del payload
    missing = _need_proposal(Gate.REGRET, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    available = _fx(fixtures).available_at_next
    if available is None:
        return _skip(Gate.REGRET, "no completed-draft fixture")
    if proposal.player_id in available and any(
        alt not in available for alt in proposal.alternatives
    ):
        return _fail(Gate.REGRET, "rec survived and a listed alternative did not")
    return _pass(Gate.REGRET)


def replay(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    del payload
    missing = _need_proposal(Gate.REPLAY, proposal)
    if missing is not None:
        return missing
    fx = _fx(fixtures)
    if fx.dated_points is None or fx.user_lineup is None or fx.policy_lineup is None:
        return _skip(Gate.REPLAY, "no dated file")
    policy_sum = _lineup_sum(fx.policy_lineup, fx.dated_points)
    user_sum = _lineup_sum(fx.user_lineup, fx.dated_points)
    if policy_sum >= user_sum:
        return _pass(Gate.REPLAY)
    return _fail(Gate.REPLAY, "policy projected-lineup sum is below the user's")


GateFn = Callable[[Payload, Proposal | None, GateFixtures | None], GateResult]
GATE_FNS: tuple[GateFn, ...] = (
    schema,
    golden_forbid,
    golden_require,
    vols_dissent,
    ecr_dissent,
    ecr_sanity,
    bye_hole,
    stability,
    vols_invariant,
    regret,
    replay,
)


def evaluate(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> tuple[GateResult, ...]:
    """Run every gate in Gate enum order against one proposal."""
    return tuple(fn(payload, proposal, fixtures) for fn in GATE_FNS)


def _fx(fixtures: GateFixtures | None) -> GateFixtures:
    return fixtures if fixtures is not None else GateFixtures()


def _need_proposal(gate: Gate, proposal: Proposal | None) -> GateResult | None:
    if proposal is None:
        return _skip(gate, "no proposal")
    return None


def _row(payload: Payload, player_id: str) -> BoardRow | None:
    for row in payload.board:
        if row.player_id == player_id:
            return row
    return None


def _empties_with(payload: Payload, added: BoardRow, week: int) -> tuple[Slot, ...]:
    players = tuple(
        _player_legal_and_bye(player) for player in payload.state.user_roster
    ) + ((added.legal_slots, added.bye),)
    return empty_startable_slots(payload.config.slots, players, week)


def _player_legal_and_bye(
    player: RosterPlayer,
) -> tuple[tuple[Slot, ...], int | None]:
    return legal_slots_for_position(player.position), player.bye


def _lineup_sum(player_ids: tuple[str, ...], points: dict[str, float]) -> float:
    return sum(points.get(player_id, 0.0) for player_id in player_ids)


def _pass(gate: Gate) -> GateResult:
    return GateResult(gate=gate, outcome=GateOutcome.PASS)


def _fail(gate: Gate, reason: str) -> GateResult:
    return GateResult(gate=gate, outcome=GateOutcome.FAIL, reason=reason)


def _skip(gate: Gate, reason: str) -> GateResult:
    return GateResult(gate=gate, outcome=GateOutcome.NOT_PERFORMED, reason=reason)
