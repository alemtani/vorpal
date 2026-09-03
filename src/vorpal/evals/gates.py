"""The twelve gates.

A gate answers one yes/no question about one recommendation. It never
scores, ranks, or grades. Three outcomes only:

- PASS — the gate ran and the recommendation is fine.
- FAIL — the gate ran and the recommendation is wrong.
- NOT_PERFORMED — the gate could not run, because an input is missing.

NOT_PERFORMED is not a soft fail. A gate with no fixture to check against
has no opinion, and the report counts it separately so a missing file can
never look like a passing grade.

Every gate has the same signature, `(payload, proposal, fixtures)`, so
`evaluate` can run all twelve in one pass. Gates that do not need the
board ignore `payload`; gates that need nothing extra ignore `fixtures`.
"""

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

# A hypothetical third VOLS pass may move a position's replacement rank by
# this much and no more. See `vols_invariant`.
MAX_RANK_SHIFT = 2

# Stability asks the same question five times. Three is the majority.
STABILITY_RUNS = 5
STABILITY_AGREE = 3

# SYSTEM asks a dissenting `why` for "X is the VOLS pick; we are not taking X
# because …" (ECR the same way). `why_contains_floor` keeps only the label
# from that form, one per flag; the words around it are not scored.
DISSENT_LABEL: dict[Flag, str] = {
    Flag.VOLS_DISSENT: "VOLS pick",
    Flag.ECR_DISAGREE: "ECR pick",
}


def draft_margin(payload: Payload) -> int:
    """How far past the consensus best `ecr_sanity` lets a pick sit.

    One round of slack in the first half of the draft, two in the second.
    Late picks are lottery tickets and the consensus is thinner there, so
    the rule loosens rather than pretending to know better.
    """
    teams = payload.config.teams
    total_picks = teams * payload.config.rounds
    first_half = payload.state.pick_no * 2 <= total_picks
    return teams if first_half else 2 * teams


def ecr_best(payload: Payload) -> int | None:
    """Best (lowest) overall ECR still on the board, or None if nobody has one.

    Overall, not positional: the best player left at any position. This is
    the reference point both ECR gates measure against.
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
    """Is the answer even well-formed?

    The pick and every alternative must be a player who is actually still
    on the board, and the slot must be one the pick can legally start in.

    Fails on a model that recommends someone drafted two rounds ago, or
    that starts a kicker at RB. No judgment involved — the answer is
    unusable, so every later gate is measuring noise.
    """
    del fixtures
    missing = _need_proposal(Gate.SCHEMA, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    on_board = {row.player_id for row in payload.board}
    if proposal.player_id not in on_board:
        return _fail(Gate.SCHEMA, "rec not on board")
    if any(alt not in on_board for alt in proposal.alternatives):
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
    """Did it pick someone hand-marked as wrong for this board?

    The forbid set is written by a human for one fixture: a kicker in
    round 2, a third TE while a starter slot sits empty. These are picks
    nobody needs a model to rule on, so a fail here is unambiguous.
    """
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
    """Did it at least name one of the picks a human says are right?

    Naming it as an alternative counts. The gate asks whether the model
    saw the right players, not whether it ranked them the way we would.

    Example: superflex, two startable QBs left, eight teams still need
    one. Any answer that never mentions either QB missed the run.
    """
    del payload
    missing = _need_proposal(Gate.GOLDEN_REQUIRE, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    require = _fx(fixtures).require
    if require is None:
        return _skip(Gate.GOLDEN_REQUIRE, "no require set")
    named = (proposal.player_id, *proposal.alternatives)
    if any(player_id in require for player_id in named):
        return _pass(Gate.GOLDEN_REQUIRE)
    return _fail(Gate.GOLDEN_REQUIRE, "rec and alternatives miss the require set")


def vols_dissent(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    """If it walked away from our own VOLS pick, did it say so?

    Exactly one of these must be true: it picked `hint_argmax_vols`, or
    it set the VOLS_DISSENT flag. Both, or neither, is a fail.

    Disagreeing with the numbers is allowed and is most of the value we
    are paying for. Doing it silently is not: the flag is what puts the
    disagreement on the board where a human can overrule it in ten
    seconds. Flagging dissent while agreeing is the same bug pointed the
    other way — the flag stops meaning anything.
    """
    del fixtures
    missing = _need_proposal(Gate.VOLS_DISSENT, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    if payload.hint_argmax_vols == "":
        return _skip(Gate.VOLS_DISSENT, "no hint_argmax_vols")
    agreed = proposal.player_id == payload.hint_argmax_vols
    flagged = Flag.VOLS_DISSENT in proposal.flags
    if agreed ^ flagged:
        return _pass(Gate.VOLS_DISSENT)
    if agreed:
        return _fail(Gate.VOLS_DISSENT, "agreed with the hint and set VOLS_DISSENT")
    return _fail(Gate.VOLS_DISSENT, "silent VOLS dissent")


def ecr_dissent(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    """Same XOR as `vols_dissent`, against the expert consensus instead.

    Picked the best player left by ECR, or set ECR_DISAGREE. Not both,
    not neither. Passing over the consensus number one is a real call and
    belongs on the board, not buried in prose.
    """
    del fixtures
    missing = _need_proposal(Gate.ECR_DISSENT, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    best = ecr_best(payload)
    if best is None:
        return _skip(Gate.ECR_DISSENT, "no ECR on the board")
    rec = _row(payload, proposal.player_id)
    agreed = rec is not None and rec.ecr is not None and rec.ecr == best
    flagged = Flag.ECR_DISAGREE in proposal.flags
    if agreed ^ flagged:
        return _pass(Gate.ECR_DISSENT)
    if agreed:
        return _fail(Gate.ECR_DISSENT, "picked ecr_best and set ECR_DISAGREE")
    return _fail(Gate.ECR_DISSENT, "silent ECR dissent")


def ecr_sanity(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    """Is the pick a defensible reach, or is it off the map?

    A floor, not a target. `ecr_dissent` already covers *whether* it left
    the consensus; this asks how far. The pick must sit within one round
    of the best player left early, two rounds late.

    Twelve-team league, best player left is ECR 40. Taking ECR 48 is a
    reach we allow. Taking ECR 200 is not a read, it is a mistake.

    `ecr_min` is the escape hatch: if a single expert has the player much
    higher, the consensus is split rather than settled, and taking the
    optimistic side of a split is a call we let stand.
    """
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


def why_contains_floor(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    """Did `why` name the pick it dissented from, and say which pick it was?

    Eval-only floor (SPEC.md #20, section 5): plain substring checks, never
    an LLM judge. For each dissent flag set, `why` must contain the named
    player — name or id — and the matching `DISSENT_LABEL`: `VOLS_DISSENT`
    names `hint_argmax_vols` as the `VOLS pick`, `ECR_DISAGREE` names the
    board row at `ecr_best` as the `ECR pick`. A name with no label, or with
    the other flag's label, is a miss: it does not say which pick it was.
    Neither flag set is a skip, not a pass — there is nothing to check. A
    flag set with no row to check it against (empty hint, no ECR on the
    board) skips that half rather than failing a check that cannot run.

    This never touches section 4: a miss here is scored, not retried or
    degraded on the pick clock.
    """
    del fixtures
    missing = _need_proposal(Gate.WHY_CONTAINS_FLOOR, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    checks: list[tuple[str, BoardRow | None]] = []
    if Flag.VOLS_DISSENT in proposal.flags:
        hint_row = (
            _row(payload, payload.hint_argmax_vols)
            if payload.hint_argmax_vols
            else None
        )
        checks.append((DISSENT_LABEL[Flag.VOLS_DISSENT], hint_row))
    if Flag.ECR_DISAGREE in proposal.flags:
        best = ecr_best(payload)
        ecr_row = (
            next((row for row in payload.board if row.ecr == best), None)
            if best is not None
            else None
        )
        checks.append((DISSENT_LABEL[Flag.ECR_DISAGREE], ecr_row))
    if not checks:
        return _skip(Gate.WHY_CONTAINS_FLOOR, "neither flag set")
    performed = False
    misses: list[str] = []
    for label, row in checks:
        if row is None:
            continue
        performed = True
        if row.name not in proposal.why and row.player_id not in proposal.why:
            misses.append(f"why does not name the {label} ({row.name})")
        elif label not in proposal.why:
            misses.append(f"why names {row.name} but not as the {label}")
    if not performed:
        return _skip(Gate.WHY_CONTAINS_FLOOR, "no row to name for the set flags")
    if misses:
        return _fail(Gate.WHY_CONTAINS_FLOOR, "; ".join(misses))
    return _pass(Gate.WHY_CONTAINS_FLOOR)


def bye_hole(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    """Does this pick leave a starter slot empty on its own bye week?

    Say your WR starter slot is still empty and the pick is a WR on bye
    9. Come week 9 you start nobody there. Another WR on the board is on
    bye 5 and would have played that week. Same position, same slot, one
    of them costs you a zero — that is a fail.

    The comparison is always run at the pick's bye week: count the empty
    starter slots with the pick added, then with each different-bye
    alternative added instead. A slot that is empty in the first count
    and filled in the second is the hole.

    Skipped when the pick has no bye, and passed when every alternative
    shares its bye — there is nothing better to have done.
    """
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
        # Counter subtraction keeps only positive counts: slots left empty
        # by the pick that this alternative would have covered.
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
    """Ask the same question five times. Do at least three answers agree?

    `stability_ids` is one run of the model per entry, all five against a
    byte-identical payload. Five different answers means the pick is a
    dice roll, not a judgment, and a human reading the board has no way
    to tell which roll they got.

    Five and three are the cheapest honest test: an odd number, and a
    simple majority of it. The count is fixed, so a fixture that does not
    hold exactly five runs is skipped rather than scored on fewer.

    Skipped when the model declares `coin_flip`. It is saying the
    candidates are equivalent, and disagreeing with itself about a tie is
    honest rather than unstable.
    """
    del payload
    missing = _need_proposal(Gate.STABILITY, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    if proposal.coin_flip:
        return _skip(Gate.STABILITY, "coin_flip")
    ids = _fx(fixtures).stability_ids
    if ids is None or len(ids) != STABILITY_RUNS:
        return _skip(Gate.STABILITY, "need five identical-payload player_ids")
    most_agreed = max(Counter(ids).values())
    if most_agreed >= STABILITY_AGREE:
        return _pass(Gate.STABILITY)
    return _fail(Gate.STABILITY, "fewer than 3 of 5 share a player_id")


def vols_invariant(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    """Has our own VOLS number settled, or is it still moving?

    VOLS is `points - replacement.points`, and the definition is
    circular: the replacement is the worst startable player at a
    position, but who starts is decided by VOLS. We break the circle by
    ranking on raw points, picking replacements, re-ranking on that, and
    picking once more. Two passes, then stop.

    This gate checks the stopping was safe. `replacement_rank_delta` is
    how far one more hypothetical pass would move each position's
    replacement, in ranks. Superflex is where this bites: valuing QBs
    properly pushes the QB replacement from, say, QB13 to QB20, and if
    another pass would move it again by four, then every QB's VOLS is an
    artifact of where we stopped counting rather than a number.

    So: no position may move by more than two. An empty map means we
    computed the deltas and nothing moved — a real pass. A missing map
    means nobody computed them, which is a skip.

    This gate is about the tool's own arithmetic, not about the model.
    """
    del payload
    missing = _need_proposal(Gate.VOLS_INVARIANT, proposal)
    if missing is not None:
        return missing
    delta = _fx(fixtures).replacement_rank_delta
    if delta is None:
        return _skip(Gate.VOLS_INVARIANT, "no replacement-rank deltas")
    for position, move in delta.items():
        if abs(move) > MAX_RANK_SHIFT:
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
    """Could you have had both? Then you took them in the wrong order.

    You named two players you wanted. You took the one who was still
    sitting there at your next turn anyway, and the other one got
    drafted. Taking them the other way round gets you both. That is the
    only thing this gate fails.

    Everything else passes. Your pick was gone by your next turn — you
    were right to take him. Everyone survived — you lost nothing.

    No survival model and no judge: `available_at_next` is read off a
    completed public draft, replayed to your pick with the board frozen.
    Who was still there is a matter of record.

    This is the tool's only measurement of wait-versus-take, which the
    spec hands to the model outright.
    """
    del payload
    missing = _need_proposal(Gate.REGRET, proposal)
    if missing is not None:
        return missing
    assert proposal is not None
    available = _fx(fixtures).available_at_next
    if available is None:
        return _skip(Gate.REGRET, "no completed-draft fixture")
    rec_survived = proposal.player_id in available
    an_alt_was_taken = any(alt not in available for alt in proposal.alternatives)
    if rec_survived and an_alt_was_taken:
        return _fail(Gate.REGRET, "rec survived and a listed alternative did not")
    return _pass(Gate.REGRET)


def replay(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> GateResult:
    """Would the policy's roster have outscored the human's, on paper?

    Both lineups are summed with the same dated projections — what was
    knowable on draft day, not what happened. Actual season results are
    mostly luck and injuries, and scoring a draft on them rewards the
    lucky pick over the right one, so they are never an input here.
    """
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

# The registry. To add a gate: add its member to the Gate enum in
# contracts.py, write the function above, and add the pair here. The
# assert below is the whole wiring check.
GATES: tuple[tuple[Gate, GateFn], ...] = (
    (Gate.SCHEMA, schema),
    (Gate.GOLDEN_FORBID, golden_forbid),
    (Gate.GOLDEN_REQUIRE, golden_require),
    (Gate.VOLS_DISSENT, vols_dissent),
    (Gate.ECR_DISSENT, ecr_dissent),
    (Gate.ECR_SANITY, ecr_sanity),
    (Gate.WHY_CONTAINS_FLOOR, why_contains_floor),
    (Gate.BYE_HOLE, bye_hole),
    (Gate.STABILITY, stability),
    (Gate.VOLS_INVARIANT, vols_invariant),
    (Gate.REGRET, regret),
    (Gate.REPLAY, replay),
)

# The report indexes rows by Gate, so evaluate() must emit every gate,
# once, in enum order.
assert tuple(gate for gate, _fn in GATES) == tuple(Gate)


def evaluate(
    payload: Payload,
    proposal: Proposal | None,
    fixtures: GateFixtures | None = None,
) -> tuple[GateResult, ...]:
    """Run all twelve gates against one proposal, in Gate enum order."""
    return tuple(fn(payload, proposal, fixtures) for _gate, fn in GATES)


def _fx(fixtures: GateFixtures | None) -> GateFixtures:
    """No fixtures at all reads the same as fixtures with every field unset."""
    return fixtures if fixtures is not None else GateFixtures()


def _need_proposal(gate: Gate, proposal: Proposal | None) -> GateResult | None:
    """Every gate judges a proposal. No proposal, nothing to judge."""
    if proposal is None:
        return _skip(gate, "no proposal")
    return None


def _row(payload: Payload, player_id: str) -> BoardRow | None:
    for row in payload.board:
        if row.player_id == player_id:
            return row
    return None


def _empties_with(payload: Payload, added: BoardRow, week: int) -> tuple[Slot, ...]:
    """Starter slots left empty in `week` if we drafted `added` right now.

    Takes the current roster, appends the one hypothetical player, and
    fills the lineup. Only `week` matters, so a player on bye that week
    counts as absent.
    """
    roster = tuple(
        _player_legal_and_bye(player) for player in payload.state.user_roster
    )
    with_added = roster + ((added.legal_slots, added.bye),)
    return empty_startable_slots(payload.config.slots, with_added, week)


def _player_legal_and_bye(
    player: RosterPlayer,
) -> tuple[tuple[Slot, ...], int | None]:
    """Roster players carry a position; the lineup filler wants slots."""
    return legal_slots_for_position(player.position), player.bye


def _lineup_sum(player_ids: tuple[str, ...], points: dict[str, float]) -> float:
    """A player with no dated projection contributes zero, not an error."""
    return sum(points.get(player_id, 0.0) for player_id in player_ids)


def _pass(gate: Gate) -> GateResult:
    return GateResult(gate=gate, outcome=GateOutcome.PASS)


def _fail(gate: Gate, reason: str) -> GateResult:
    return GateResult(gate=gate, outcome=GateOutcome.FAIL, reason=reason)


def _skip(gate: Gate, reason: str) -> GateResult:
    return GateResult(gate=gate, outcome=GateOutcome.NOT_PERFORMED, reason=reason)
