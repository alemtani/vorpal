# vorpal

`docs/SPEC.md` is the contract. Do not invent behavior it does not specify.

Personal NFL redraft tool. A `LeagueHost` adapter reads the platform.
v1 implements Sleeper. ESPN would be another adapter, not a rewrite.
Forecast (stats, ADP, ECR) stays in ingest. Valuation never imports a host.

## TDD

FAIL_TO_PASS first. Write the test. Run it. Confirm it fails for the reason
you intend. Then implement. Then run it again and confirm it passes.

Do not implement first and backfill tests. Do not write a test that already
passes.

99% line coverage is a CI gate. If it is missing, add it. Do not lower it.
Do not exclude new code to keep the number.

Non-obvious helpers get a short docstring (what they keep, what they cap).

## Session protocol

From `docs/PLAN.md` section 5.

Start in a worktree: `git worktree add ../vorpal-sN -b feat/<scope> main`.
Touch only the files your prompt says you own.

If a generic type must change, stop and open a small PR against
`src/vorpal/contracts.py` / `src/vorpal/platform/`. Do not silently fork
the type in your package. Rebase after it merges.

Before you open the PR: write `docs/handoffs/SN.md`, set your PLAN.md
row to DONE, update prompts of sessions that depend on you. A PR that
skips those is not finished.

## Do not

- Write to a host, scrape, or drive a browser.
- Hardcode a league's settings, scoring, or roster.
- Commit `private/`, `*.local.json`, or anything that identifies a league
  or its managers.
- Ingest a fantasy-points column. Apply this league's scoring to counting
  stats.
- Silent-zero an unmatched nonzero scoring key.
- Add an executor. The human clicks in the host UI.
- Fit a market model on this league's draft history.
- Build lineup, waiver, or trade policy in v1.
- Add a chance-to-last-until-the-next-pick number.

## Facts agents miss

- **Slots, not scoring, decide what starts.** Canonical defense slot is
  `DEF`. Canonical superflex slot is `SUPER_FLEX`. Hosts map their wire
  onto those.
- **Refuse, do not degrade:** `LeagueFormat` keeper/dynasty, taxi slots,
  IDP slot codes, auction, linear, `reversal_round != 0`. `max_keepers > 0`
  on redraft is a banner, not a refusal.
- **Unknown seat:** omit `next_user_pick`, `picks_until_next`, `between`.
- **`/players` has no bye.** Take bye from FantasyPros `player_bye_week`.
- **VOLS is last starter, two passes.** Bench is not absorbed. Spec
  section 3. The pick is the model's; `hint_argmax_vols` is a calculator.
- **ECR is not the pick** and is not a valuation input. S2 then S5.
- **Standalone mocks:** `league_id` is JSON `null`. Slots from the mock,
  scoring from a borrowed league.
- **Poll:** 3s while `drafting`, else 15s until `complete`. Observed
  statuses include `paused`. Never poll projections or FantasyPros.
- **Rate limit:** under 1000/min. `/players` at most once per day.

## Errors

All are `VorpalError`. Print to stderr, exit 2. Do not collapse them.

| Class | Meaning |
|---|---|
| `UnsupportedLeague` | Permanent. Format is out of v1. |
| `DataRefusal` | Fixable by a better file. |
| `PlatformError` | The host or projections API. |
| `UserRefusal` | Operator identity or seat. |

```
uv sync
uv run pytest
uv run pytest -m golden
uv run pytest -m invariant
uv run ruff check .
uv run ruff format .
```

Python >= 3.12. CI is 3.12 and 3.13. Marker `live` is off in CI.
`invariant` / `golden` failures are model problems, not code bugs.
