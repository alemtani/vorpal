"""The recorded model answers, scored on the golden boards.

`test_golden.py` checks that the cases are well-formed. This file is the
model's answer: replay the committed cassette, fail the build on
`golden_forbid` or `golden_require`. `bye_hole` is not a gate here
until #31 is settled. The live runner is not imported.
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
def test_recorded_model_passes_golden_gates(case: GoldenCase) -> None:
    proposal = _recorded(case)
    results = evaluate(case.payload, proposal, case.fixtures())
    assert _outcome(results, Gate.GOLDEN_FORBID) is GateOutcome.PASS
    assert _outcome(results, Gate.GOLDEN_REQUIRE) is GateOutcome.PASS


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
