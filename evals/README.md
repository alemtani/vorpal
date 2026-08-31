# Evals

Four policies on each board: **model**, **argmax_vols**, **adp_follow**,
**ecr_follow**. A gate where model and VOLS post the same rate has no
discriminating power (SPEC.md §5).

```
uv run python -m evals.run
uv run python -m evals.run --only golden
uv run python -m evals.run --only regret
uv run python -m evals.run --only human
```

**A default run replays cassettes and spends nothing.** No
`ANTHROPIC_API_KEY` needed. A board with no recording raises and names
the key; it never falls through to a live call.

`--record` is the only thing that spends. See `evals/cassettes/README.md`.

```
uv run python -m evals.run --only golden --record
```

Eval path is `recommend` / `run_stability`. A violation is the score.
Draft night calls `propose` instead; do not use it here.

## The three families

| Family | Asks | In the four-column table? |
|---|---|---|
| **golden** | Did it avoid a mistake a human can name in one sentence? 12 hand-built boards, forbid + require. | yes |
| **regret** | Could we have had both names? Fail iff rec survived to our next pick and a listed alternative did not. | yes |
| **human** | What would each policy have said on the operator's mocks? Agreement with a click, not a verdict. | no |

Golden cases: `tests/golden/README.md`. Regret fixtures:
`tests/regret/README.md`. `argmax_vols` already passes 9 of 12 golden
cases; only three can show the model is doing anything.

## What CI does

`pytest -m "not live"` includes `pytest -m golden`. Those tests check
that the cases are well-formed, that the gates agree with the
hand-written verdicts on synthetic proposals, and that the recorded
model answers pass `golden_forbid` and `golden_require`. They do not
call the model. `bye_hole` is not a CI fail until #31 is settled. The
four-column table is this runner. Do not put it on the CI job.
