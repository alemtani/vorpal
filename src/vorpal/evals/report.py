"""Four pass rates per gate, model against the three baselines."""

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
    """Pass/fail/skip counts for one gate across policies.

    Pass rate is passes / (passes + fails). Skips are not a zero.
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
        """True only when model and argmax_vols both ran and posted different rates."""
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
