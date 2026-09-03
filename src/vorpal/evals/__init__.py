"""Does the model earn its tokens? This package answers that and nothing else.

Twelve gates, each a yes/no question about one recommendation:

| Gate | Asks |
|---|---|
| `schema` | Is the answer even well-formed — real players, legal slot? |
| `golden_forbid` | Did it make a pick a human marked as plainly wrong? |
| `golden_require` | Did it at least name one of the picks a human says are right? |
| `vols_dissent` | If it left our VOLS pick, did it flag that it was doing so? |
| `ecr_dissent` | Same question against the expert consensus. |
| `ecr_sanity` | Is the pick a defensible reach, or off the map entirely? |
| `why_contains_floor` | If it dissented, did `why` name and label the pick it left? |
| `bye_hole` | Does the pick leave a starter slot empty on its own bye week? |
| `stability` | Same board five times — do at least three answers agree? |
| `vols_invariant` | Has our own VOLS arithmetic settled? (About us, not the model.) |
| `regret` | Could we have had both names? Then we took them in the wrong order. |
| `replay` | Would this roster have outscored the human's, on draft-day numbers? |

Each returns PASS, FAIL, or NOT_PERFORMED. Missing input is
NOT_PERFORMED, never a fail.

`baselines` runs the same fixtures through three one-line rules, and
`report` prints the four pass rates side by side. A gate where the model
matches `argmax_vols` is not measuring anything.

Pure functions. Zero network. No LLM-as-judge: nothing here asks a model
whether a model was right.

Read `gates.py` for the reasoning behind each rule.
"""

from vorpal.evals.baselines import BASELINES, adp_follow, argmax_vols, ecr_follow
from vorpal.evals.gates import (
    bye_hole,
    draft_margin,
    ecr_best,
    ecr_dissent,
    ecr_sanity,
    evaluate,
    golden_forbid,
    golden_require,
    regret,
    replay,
    schema,
    stability,
    vols_dissent,
    vols_invariant,
    why_contains_floor,
)
from vorpal.evals.report import (
    NO_DISCRIMINATING_POWER,
    POLICY_ORDER,
    GateScore,
    render_report,
    score_results,
)
from vorpal.evals.sampler import (
    hostile_states,
    remaining_board,
    sample_adp_order,
    sample_board_states,
)
from vorpal.evals.types import GateFixtures

__all__ = [
    "BASELINES",
    "NO_DISCRIMINATING_POWER",
    "POLICY_ORDER",
    "GateFixtures",
    "GateScore",
    "adp_follow",
    "argmax_vols",
    "bye_hole",
    "draft_margin",
    "ecr_best",
    "ecr_dissent",
    "ecr_follow",
    "ecr_sanity",
    "evaluate",
    "golden_forbid",
    "golden_require",
    "hostile_states",
    "regret",
    "remaining_board",
    "render_report",
    "replay",
    "sample_adp_order",
    "sample_board_states",
    "schema",
    "score_results",
    "stability",
    "vols_dissent",
    "vols_invariant",
    "why_contains_floor",
]
