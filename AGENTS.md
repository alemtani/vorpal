# vorpal

`docs/SPEC.md` is the contract. Do not invent behavior it does not specify.

Personal NFL redraft tool. Sleeper league ID in; recommendations out. The human acts in the platform UI.

## TDD

FAIL_TO_PASS first. Write the test. Run it. Confirm it fails for the reason you intend. Then implement. Then run it again and confirm it passes.

Do not implement first and backfill tests. Do not write a test that already passes.

99% line coverage is a CI gate. If it is missing, add it. Do not lower it. Do not exclude new code to keep the number.

## Do not

- Write to Sleeper, scrape, drive a browser, or reverse-engineer internal APIs. The public API is read-only.
- Hardcode any league's settings, scoring, or roster. Read them at runtime.
- Commit `private/`, `*.local.json`, or anything that identifies a league or its managers.
- Ingest a fantasy-points column. Apply the league's scoring to counting stats.
- Silent-zero an unmatched nonzero scoring key. Report it before the board renders.
- Add an executor or write-plugin. One implementation is not an interface.
- Fit a market model on this league's draft history (deferred, SPEC.md §4).
- Build lineup, waiver, or trade policy in v1. Draft only.

## Facts agents miss

- **Slots, not scoring, decide what starts.** A league can store K/DST scoring with no K/DST slot.
- **Refuse, do not degrade:** keeper/dynasty (`max_keepers > 0` or taxi), IDP, auction. Linear draft is in scope but must not use snake pick spacing.
- **Unknown draft slot:** hide survival entirely. Do not guess it.
- **Mapping fail-closed:** match name+pos+team, then name+pos (flag team mismatch). If match rate on the top 300 by ADP is below 98%, refuse and print the report.
- **K/DST rows** are required when those slots exist. If a slot exists and the file has no rows, use a flat baseline and state that on the board.
- **Replacement (SPEC.md §7):** two passes (points, then VORP). Bench is not absorbed. Fill flexible slots most-restrictive first. A hypothetical pass 2 must not move any position's replacement rank by more than 2 — that is a failing eval, not a comment.
- **Pick objective:** one-step lookahead that maximizes expected starting-lineup VORP, discounted by survival to the user's next pick. Not static VORP. Not myopic take-best.
- **Survival:** placeholder `σ = max(4, 0.30 × ADP)` unless the file supplies `adp_stdev`. Show coarse bands, not decimals. Independence is known-wrong. Already-drafted = 0.
- **Evals:** decision error (SPEC.md §9.2) is internal consistency — same projections on both sides. Do not generate board states from the survival model. The golden set (SPEC.md §9.3) is the only v1 check that can catch a bad value *model*. Outcome replay without a pre-draft projection file is `NOT PERFORMED`, never a caveated number.
- **Draft-night poll:** 3s while active; backoff 5/15/45s. Always show data age. Past 15s, degrade visibly. Older than one pick interval: grey the recommendation. Never present a stale board as current.
- **Shared layer across sports is ingest + projections only.** Do not generalize the player-value model. FPL and brackets are different problems.
- **Rate limit:** stay under 1000 calls/min. Fetch `/players` at most once per day (~5MB).

## Layout and toolchain

`main` is spec-only. Reuse `chore/project-skeleton` rather than inventing packaging.

Intended tree, matching SPEC.md §5:

- `src/vorpal/sleeper` — platform read
- `src/vorpal/ingest` — user files from `private/`
- `src/vorpal/valuation` — scoring, replacement, VORP
- `src/vorpal/policy` — draft (v1)
- `src/vorpal/board` — local page
- `evals/` — decision quality, not outcomes

Refusal taxonomy (load-bearing): `UnsupportedLeague` is permanent; `DataRefusal` is fixable by a better file; `PlatformError` is the API. All are `VorpalError`. CLI prints them to stderr and exits 2. Do not collapse the two refusal types.

Intended commands (skeleton, not yet on `main`):

```
uv sync
uv run pytest
uv run pytest -m golden
uv run pytest -m invariant
uv run ruff check .
uv run ruff format .
```

Python >=3.12. CI is 3.12 and 3.13. Runtime deps arrive with the PR that needs them.

Pytest markers: `invariant` (SPEC.md §7), `golden` (SPEC.md §9.3). A marker failure is a model problem, not a code bug.
