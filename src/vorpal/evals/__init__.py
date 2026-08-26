"""Eval gates, baseline policies, sampler, and the four-column report.

Pure functions. Zero network. No LLM-as-judge.
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
]
