# vorpal

`docs/SPEC.md` is the contract. Do not invent behavior it does not specify.

Personal NFL redraft tool. A `LeagueHost` adapter reads the platform.
v1 implements Sleeper. ESPN would be another adapter, not a rewrite.
Forecast (stats, ADP, ECR, bye) is FantasyPros. It stays in ingest.
Valuation never imports a host.

Ingest is host-agnostic. Parameters are `host_players`, not `sleeper_*`.
The host player map is a join directory (id, yahoo_id, name, pos, team).
Player join has one implementation. New sources add an extractor, not a
new matcher. Independent forecast fetches run in parallel and join.

## A league is a table, not a branch

FantasyPros is the hub. It supplies the numbers: counting stats, ADP, ECR,
bye. Those are the same for every league. A league is two things on top of
them: a mapping from its wire names onto ours, and its own draft settings
(slots, teams, order, seat).

So the metrics are league-agnostic. Scoring, VOLS, the weekly vector, and
marginal value read a table and apply it. They do not know which host the
league is on, and they do not change shape when the league does.

Wire names live in exactly one place: `platform/scoring_keys.py`, one table
per host. `resolve` reads it to decide which slot a key belongs to.
`valuation` reads it to decide which formula scores a key. Neither owns a
copy.

Rules that follow:

- **Never infer a key's meaning from its prefix.** `pass_int` is a QB key
  and `int` is a defense key because the table says so, not because one
  string is longer. A key with no row is unclassified: report it, never
  score it as zero.
- **One row per key, one meaning.** If two layers need to disagree about a
  key, they are wrong, not the table. Fix the row.
- **Do not add a key you have not verified** against the host's own
  scoring settings. An unclassified key already surfaces as a banner. A
  guessed row is silent and wrong.
- **Onboarding a host is filling in tables** — `FP_TO_HOST` in
  `ingest/keys.py`, `SCORING_KEY_GROUP` in `platform/scoring_keys.py` —
  plus a `LeagueHost` adapter. If it also needs an edit to `valuation`,
  something leaked. Put it back.

## TDD

FAIL_TO_PASS first. Write the test. Run it. Confirm it fails for the reason
you intend. Then implement. Then run it again and confirm it passes.

Do not implement first and backfill tests. Do not write a test that already
passes.

99% line coverage is a CI gate. If it is missing, add it. Do not lower it.
Do not exclude new code to keep the number.

Non-obvious helpers get a short docstring (what they keep, what they cap).

## Work tracking

v1 sessions (S0–S9) are done. Do not add S11.

A change is an issue or a spec, never a numbered session.

- **Issue:** one obvious approach, one or two commits. The PR closes it.
- **needs-spec:** more than one viable approach, a human has to choose,
  or the work spans several commits. Open an issue labeled `needs-spec`.
  Do not start the implementation PR until a spec is accepted. The spec
  is a later PR against `docs/SPEC.md` (or a short `docs/specs/<slug>.md`).

Dependencies live on the issue (`blocked by #N`), not in PLAN.md.

Start in a worktree: `git worktree add ../vorpal-<slug> -b feat/<slug> main`.

If a generic type must change, stop and open a small PR against
`src/vorpal/contracts.py` / `src/vorpal/platform/`. Do not silently fork
the type in your package. Rebase after it merges.

If the next person cannot see it from the code, put it in the PR body.

## Do not

- Write to a host, scrape, or drive a browser.
- Hardcode a league's settings, scoring, or roster.
- Commit `private/`, `*.local.json`, or anything that identifies a league
  or its managers.
- Ingest a fantasy-points column. Apply this league's scoring to counting
  stats.
- Silent-zero an unmatched nonzero scoring key.
- Match a wire name by prefix, or keep a second copy of a host's key table.
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
- **Forecast is FantasyPros.** Counting stats, ADP, ECR, bye. Host `/players`
  is the join directory. Do not fetch Sleeper projections.
- **VOLS is last starter, two passes.** Bench is not absorbed. Spec
  section 3. The pick is the model's; `hint_argmax_vols` is a calculator.
- **ECR is not the pick** and is not a valuation input. Ingest then payload.
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
