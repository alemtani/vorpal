"""The scoreboard: one row per gate, four pass rates side by side.

Reading a row: the model's rate is only interesting next to
`argmax_vols`. If they match, the gate did not distinguish the model from
a one-line rule, and we mark the row NO DISCRIMINATING POWER. That is a
verdict on the gate or the fixtures, not on the model — a gate nothing
can fail teaches us nothing.

Skips are counted apart from the rate and printed as `s=N`. A gate that
ran twice and passed twice reads 1.00 the same as one that ran two
hundred times, so the skip count is how you catch a rate resting on
almost no evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vorpal.contracts import Gate, GateOutcome, GateResult

POLICY_ORDER: tuple[str, ...] = (
    "model",
    "argmax_vols",
    "adp_follow",
    "ecr_follow",
)
NO_DISCRIMINATING_POWER = "NO DISCRIMINATING POWER"

_COL = 16


@dataclass(frozen=True, slots=True)
class GateScore:
    """One gate's counts, per policy. `counts` maps policy to (pass, fail, skip).

    Pass rate divides by the runs that actually happened, so a missing
    fixture never counts against a policy. All skips means no rate at all
    (`None`), printed as a dash — we did not measure this, which is a
    different statement from measuring zero.
    """

    gate: Gate
    counts: dict[str, tuple[int, int, int]]

    def pass_rate(self, policy: str) -> float | None:
        passed, failed, _skipped = self.counts.get(policy, (0, 0, 0))
        performed = passed + failed
        if performed == 0:
            return None
        return passed / performed

    def skipped(self, policy: str) -> int:
        return self.counts.get(policy, (0, 0, 0))[2]

    def performed(self, policy: str) -> int:
        passed, failed, _skipped = self.counts.get(policy, (0, 0, 0))
        return passed + failed

    def separates(self) -> bool:
        """Did this gate tell the model apart from the argmax_vols baseline?

        Both must have actually run. Equal rates mean the gate earned
        nothing, and neither does a gate only one of them was scored on.
        """
        model = self.pass_rate("model")
        hint = self.pass_rate("argmax_vols")
        if model is None or hint is None:
            return False
        return model != hint


def score_results(
    by_policy: Mapping[str, Sequence[GateResult]],
) -> tuple[GateScore, ...]:
    """Group a flat list of results per policy into one score per gate."""
    scores: list[GateScore] = []
    for gate in Gate:
        counts: dict[str, tuple[int, int, int]] = {}
        for policy in POLICY_ORDER:
            rows = [row for row in by_policy.get(policy, ()) if row.gate is gate]
            passed = sum(1 for row in rows if row.outcome is GateOutcome.PASS)
            failed = sum(1 for row in rows if row.outcome is GateOutcome.FAIL)
            skipped = sum(1 for row in rows if row.outcome is GateOutcome.NOT_PERFORMED)
            counts[policy] = (passed, failed, skipped)
        scores.append(GateScore(gate=gate, counts=counts))
    return tuple(scores)


def render_report(by_policy: Mapping[str, Sequence[GateResult]]) -> str:
    """Plain-text table. Matching model and argmax_vols rates are marked."""
    scores = score_results(by_policy)
    header = (
        f"{'gate':<{_COL}}"
        + "".join(f"{name:<{_COL}}" for name in POLICY_ORDER)
        + "note"
    )
    lines = [header]
    for score in scores:
        cells = "".join(
            f"{_fmt_rate(score, policy):<{_COL}}" for policy in POLICY_ORDER
        )
        note = "" if score.separates() else NO_DISCRIMINATING_POWER
        lines.append(f"{score.gate.value:<{_COL}}{cells}{note}")
    return "\n".join(lines) + "\n"


def _fmt_rate(score: GateScore, policy: str) -> str:
    rate = score.pass_rate(policy)
    skip = score.skipped(policy)
    if rate is None:
        cell = "—"
    else:
        cell = f"{rate:.2f}"
    if skip:
        cell += f" s={skip}"
    return cell
