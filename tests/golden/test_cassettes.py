"""The recorded model answers, scored on the golden boards.

`test_golden.py` checks that the cases are well-formed. This file is the
model's answer: replay the committed cassette and fail the build on any
gate in `ENFORCED`. The live runner is not imported.

Seven of the twelve gates are enforced. The other five are not blocked on
the model — they are blocked on something this set does not carry, and
`NOT_ENFORCED` says which, so a skip can never read as a pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cases import CASES, GoldenCase

from vorpal.contracts import Flag, Gate, GateOutcome, Proposal
from vorpal.evals import evaluate
from vorpal.model import CassetteStore, CassetteTransport, recommend, request_key

pytestmark = pytest.mark.golden

# #57: the label the SYSTEM form asks for, per dissent flag. The model must
# state each label once. Twice is the doubling bug we saw live.
DISSENT_LABEL: dict[Flag, str] = {
    Flag.VOLS_DISSENT: "VOLS pick",
    Flag.ECR_DISAGREE: "ECR pick",
}

CASSETTES = Path(__file__).resolve().parents[2] / "evals" / "cassettes"
CASE_IDS = [case.name for case in CASES]

# The gates the recorded answers clear on this set, and how many of the cases
# each one actually runs on. A gate here fails the build.
#
# The count is pinned, not derived. A gate whose inputs quietly disappear
# starts returning NOT_PERFORMED on every case and stays green forever —
# `_gates_still_run_on_as_many_cases` is what stops that from being silent.
# `why_contains_floor` runs on 4 because only four recorded answers set a
# dissent flag; with no flag there is nothing for it to check.
ENFORCED: dict[Gate, int] = {
    Gate.SCHEMA: 12,
    Gate.GOLDEN_FORBID: 12,
    Gate.GOLDEN_REQUIRE: 12,
    Gate.VOLS_DISSENT: 12,
    Gate.ECR_DISSENT: 12,
    Gate.ECR_SANITY: 12,
    Gate.WHY_CONTAINS_FLOOR: 4,
}

# Why each remaining gate is not a build failure. These are missing inputs and
# one known gate bug, never a model verdict we chose to look away from.
NOT_ENFORCED: dict[Gate, str] = {
    # The gate compares alternatives inside the rec's own bye week only, so a
    # symmetric board fails whichever player you take. It fails all 12 cases
    # here, including the ones the human calls correct.
    Gate.BYE_HOLE: "gate bug, #31",
    # Five runs against a byte-identical payload. The cassette holds one.
    Gate.STABILITY: "no five-run fixture on a golden board",
    # Needs the two-pass replacement-rank deltas; a hand-built board has no pool.
    Gate.VOLS_INVARIANT: "no full pool on a golden board",
    # Needs a completed public draft replayed to this seat.
    Gate.REGRET: "no completed-draft fixture on a golden board",
    # Needs a dated projections file. S9 shipped none.
    Gate.REPLAY: "no dated projections file",
}


def _recorded(case: GoldenCase) -> Proposal:
    """The first committed sample, through the eval path.

    A miss names the case, not only the key. Re-record with
    `uv run python -m evals.run --only golden --record`.
    """
    key = request_key(case.payload.to_dict())
    path = CASSETTES / f"{key}.json"
    assert path.exists(), (
        f"{case.name} cassette {key} not recorded; "
        "re-record with `uv run python -m evals.run --only golden --record`"
    )
    return recommend(case.payload, CassetteTransport(CassetteStore(CASSETTES)))


def _outcome(results, gate: Gate) -> GateOutcome:
    return next(result.outcome for result in results if result.gate is gate)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_recorded_model_fails_no_enforced_gate(case: GoldenCase) -> None:
    """No enforced gate may FAIL on a recorded answer.

    FAIL, not "must PASS": a gate that cannot run on a case has no opinion
    about it, and calling that a failure would score a missing input as a
    wrong pick. The count of cases each gate really runs on is pinned
    separately, so a skip still cannot pass for a pass.
    """
    proposal = _recorded(case)
    results = evaluate(case.payload, proposal, case.fixtures())
    failed = {
        result.gate.name.lower(): result.reason
        for result in results
        if result.gate in ENFORCED and result.outcome is GateOutcome.FAIL
    }
    assert not failed, f"{case.name}: {failed}"


def test_every_gate_is_either_enforced_or_has_a_reason() -> None:
    """No gate falls off the list unnoticed.

    Adding a gate to the enum without deciding whether the golden set can
    block on it is the failure this catches. There is no third bucket.
    """
    assert set(ENFORCED) | set(NOT_ENFORCED) == set(Gate)
    assert not set(ENFORCED) & set(NOT_ENFORCED)


def test_enforced_gates_still_run_on_as_many_cases() -> None:
    """Pin how many cases each enforced gate performs on.

    A gate whose input disappears returns NOT_PERFORMED everywhere and keeps
    the build green while measuring nothing. That is the failure mode this
    file exists to prevent, so the number is written down and checked.

    A drop is a regression. A rise means the set got stronger — update the
    number in the same PR that earned it.
    """
    performed = dict.fromkeys(ENFORCED, 0)
    for case in CASES:
        results = evaluate(case.payload, _recorded(case), case.fixtures())
        for result in results:
            if result.gate in ENFORCED and result.outcome is not (
                GateOutcome.NOT_PERFORMED
            ):
                performed[result.gate] += 1
    assert performed == ENFORCED


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_recorded_why_states_each_dissent_label_once(case: GoldenCase) -> None:
    """#57: a dissenting `why` names its label exactly once.

    The #20 floor only needs the label present (a substring). The doubling
    bug satisfied that floor while reading twice. This gate is the fix's
    proof: for each dissent flag the recorded proposal sets, the label
    appears once, never repeated as a header plus a restated reason.
    """
    proposal = _recorded(case)
    for flag, label in DISSENT_LABEL.items():
        if flag in proposal.flags:
            assert proposal.why.count(label) == 1, (
                f"{case.name}: '{label}' appears "
                f"{proposal.why.count(label)}x in why: {proposal.why!r}"
            )
