# Proof

What a change must show before it merges. This is the connective policy
over the gates in `SPEC.md` §5 and the families in `evals/README.md`. It
does not add a gate. It decides which existing proof a change owes.

`AGENTS.md` wins on conflict. `SPEC.md` is still the contract for what a
gate checks; this file only says when you must run one.

## The rule

**Proof climbs to the surface the change touches.** A change owes proof on
the highest rung it reaches, and on every rung below that it also touches.
One change can owe a unit test *and* a snapshot.

It is not "backend gets evals, the night board gets a screenshot." It is
one ladder. Most PRs touch one rung. A prompt change that also moves the
board reaches two.

## The ladder

| Rung | Surface the change touches | Proof it owes | Where it lives |
|---|---|---|---|
| 0 | Pure valuation or logic. Nothing the operator sees changes. | Unit test; `-m invariant` when it touches VOLS replacement rank. | `tests/`, `pytest -m invariant` |
| 1 | The model's judgment on a **single pick**. | A golden or regret case. Rec/alternatives on a frozen board, pass/fail against a hand-written verdict. | `tests/golden`, `tests/regret`, `evals.run` |
| 2 | **Whole-draft** behavior. Does it complete every pick on the clock without crashing? | A dress rehearsal: a full end-to-end mock the operator sits in. | `evals/rehearse.py`, issue #21 |
| 3 | What the operator **sees or acts on** during the draft. | The night-board HTML snapshot must change, and read cleanly before the clock hits zero. | night view, issue #19 |

Rungs 0 and 1 are CI. Rungs 2 and 3 are the operator's, run by hand
against a live mock. CI never makes a live call and never times a clock;
that stays a rule (`evals/README.md`, "What CI does").

## The decision question

Ask one thing:

> **Does the change alter what the operator sees or does on the clock?**

- **Yes** → rung 3. The snapshot must change, and you owe a dress
  rehearsal (rung 2) so the new view survives a real 30-second pick.
- **No** → a golden or regret case (rung 1), or a `rehearse` run (rung 2)
  if the change is about whether a whole draft holds together, is enough.
  A screenshot proves nothing a frozen-board case does not.

"If the operator sees it, show it." Otherwise a gate is the proof.

## The unit of proof

The proof artifact is the redacted JSON snapshot (#22): payload +
proposal + human pick + pick numbers, player ids only, no league id, no
manager names. It is the save half of turning a real draft into a case,
and the seed a later PR promotes to `tests/golden`, `tests/regret`, or
drops as taste (#29).

A dress rehearsal (rung 2) and a live mock both end in one of these files.
That is how a Friday-night draft becomes next week's eval case.

## pstack

pstack is the operator's workflow for driving a **live mock** — start the
draft, watch the board render, time the on-clock call. It is not a vorpal
dependency and not a CI step (#28). It belongs to rungs 2 and 3, in the
operator's hands, never in the repo's imports.

No LLM-as-judge, here or anywhere. The operator is the judge while every
trace still fits under one pair of eyes (`SPEC.md` §5).

## Related issues

- #29 — human feedback promoted to an eval case (the reactive signal).
- #28 — projection-season sim as the drafted-well gate (a rung-1 outcome
  test, v2-adjacent).
- #26 — grow the golden set from real drafts, not synthetic kickers.
- #22 — snapshot a completed draft to JSON (the artifact above).
- #21 — dress rehearsal the operator sits in (rung 2).
- #19 — draft-night board: rec first, snapshots must change (rung 3).
