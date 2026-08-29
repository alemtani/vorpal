"""Four pass rates per gate. Matching model and argmax_vols is visible."""

from __future__ import annotations

from vorpal.contracts import Gate, GateOutcome, GateResult
from vorpal.evals.report import (
    NO_DISCRIMINATING_POWER,
    POLICY_ORDER,
    GateScore,
    render_report,
    score_results,
)


def _result(gate: Gate, outcome: GateOutcome) -> GateResult:
    return GateResult(gate=gate, outcome=outcome, reason=None)


def _flat(
    outcome_by_gate: dict[Gate, list[GateOutcome]],
) -> list[GateResult]:
    rows: list[GateResult] = []
    for gate, outcomes in outcome_by_gate.items():
        rows.extend(_result(gate, outcome) for outcome in outcomes)
    return rows


def test_pass_rate_ignores_not_performed() -> None:
    results = {
        "model": _flat(
            {
                Gate.SCHEMA: [
                    GateOutcome.PASS,
                    GateOutcome.FAIL,
                    GateOutcome.NOT_PERFORMED,
                    GateOutcome.NOT_PERFORMED,
                ]
            }
        ),
        "argmax_vols": _flat({Gate.SCHEMA: [GateOutcome.PASS, GateOutcome.PASS]}),
        "adp_follow": _flat({Gate.SCHEMA: [GateOutcome.FAIL]}),
        "ecr_follow": _flat({Gate.SCHEMA: [GateOutcome.NOT_PERFORMED]}),
    }
    scores = {row.gate: row for row in score_results(results)}
    schema = scores[Gate.SCHEMA]
    assert schema.pass_rate("model") == 0.5
    assert schema.skipped("model") == 2
    assert schema.pass_rate("argmax_vols") == 1.0
    assert schema.pass_rate("adp_follow") == 0.0
    assert schema.pass_rate("ecr_follow") is None
    assert schema.separates() is True


def test_matching_rates_have_no_discriminating_power() -> None:
    results = {
        "model": _flat({Gate.VOLS_DISSENT: [GateOutcome.PASS, GateOutcome.PASS]}),
        "argmax_vols": _flat({Gate.VOLS_DISSENT: [GateOutcome.PASS, GateOutcome.PASS]}),
        "adp_follow": _flat({Gate.VOLS_DISSENT: [GateOutcome.FAIL]}),
        "ecr_follow": _flat({Gate.VOLS_DISSENT: [GateOutcome.PASS]}),
    }
    score = next(row for row in score_results(results) if row.gate is Gate.VOLS_DISSENT)
    assert score.separates() is False
    table = render_report(results)
    assert NO_DISCRIMINATING_POWER in table
    assert "vols_dissent" in table


def test_different_rates_do_not_carry_the_warning() -> None:
    results = {
        "model": _flat({Gate.REGRET: [GateOutcome.PASS, GateOutcome.FAIL]}),
        "argmax_vols": _flat({Gate.REGRET: [GateOutcome.PASS, GateOutcome.PASS]}),
        "adp_follow": _flat({Gate.REGRET: [GateOutcome.FAIL, GateOutcome.FAIL]}),
        "ecr_follow": _flat({Gate.REGRET: [GateOutcome.PASS]}),
    }
    table = render_report(results)
    # The regret row separates; the warning must not attach to it.
    regret_line = next(line for line in table.splitlines() if line.startswith("regret"))
    assert NO_DISCRIMINATING_POWER not in regret_line
    assert "0.50" in regret_line
    assert "1.00" in regret_line


def test_skipped_only_is_not_a_zero_pass_rate() -> None:
    results = {
        "model": _flat({Gate.REPLAY: [GateOutcome.NOT_PERFORMED]}),
        "argmax_vols": _flat({Gate.REPLAY: [GateOutcome.NOT_PERFORMED]}),
        "adp_follow": _flat({Gate.REPLAY: [GateOutcome.NOT_PERFORMED]}),
        "ecr_follow": _flat({Gate.REPLAY: [GateOutcome.NOT_PERFORMED]}),
    }
    table = render_report(results)
    replay_line = next(line for line in table.splitlines() if line.startswith("replay"))
    assert "—" in replay_line or "--" in replay_line
    assert NO_DISCRIMINATING_POWER in replay_line
    assert "0.00" not in replay_line


def test_report_lists_policies_side_by_side() -> None:
    results = {name: _flat({Gate.SCHEMA: [GateOutcome.PASS]}) for name in POLICY_ORDER}
    table = render_report(results)
    header = table.splitlines()[0]
    for name in POLICY_ORDER:
        assert name in header
    assert table.splitlines()[0].index("model") < table.splitlines()[0].index(
        "argmax_vols"
    )


def test_gate_score_counts() -> None:
    score = GateScore(
        gate=Gate.SCHEMA,
        counts={
            "model": (3, 1, 2),
            "argmax_vols": (4, 0, 0),
            "adp_follow": (0, 0, 5),
            "ecr_follow": (1, 1, 0),
        },
    )
    assert score.performed("model") == 4
    assert score.skipped("model") == 2
    assert score.pass_rate("model") == 0.75
    assert score.pass_rate("adp_follow") is None
    assert score.separates() is True


def test_missing_policy_is_blank_not_a_zero() -> None:
    results = {"model": _flat({Gate.SCHEMA: [GateOutcome.PASS]})}
    table = render_report(results)
    assert "model" in table
    schema_line = next(line for line in table.splitlines() if line.startswith("schema"))
    assert "—" in schema_line or "--" in schema_line


def test_render_includes_every_gate_even_when_absent_from_results() -> None:
    results = {
        "model": _flat({Gate.SCHEMA: [GateOutcome.PASS]}),
        "argmax_vols": _flat({Gate.SCHEMA: [GateOutcome.PASS]}),
        "adp_follow": _flat({Gate.SCHEMA: [GateOutcome.PASS]}),
        "ecr_follow": _flat({Gate.SCHEMA: [GateOutcome.PASS]}),
    }
    table = render_report(results)
    for gate in Gate:
        assert gate.value in table
