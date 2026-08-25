# vorpal

`docs/SPEC.md` is the contract. Do not invent behavior it does not specify.

Personal NFL redraft tool. Draft id and operator in; a recommendation out.
The human acts in the Sleeper UI.

## TDD

FAIL_TO_PASS first. Write the test. Run it. Confirm it fails for the reason
you intend. Then implement. Then run it again and confirm it passes.

Do not implement first and backfill tests. Do not write a test that already
passes.

99% line coverage is a CI gate. If it is missing, add it. Do not lower it.
Do not exclude new code to keep the number.

## Session protocol

Standing rules from `docs/PLAN.md` section 5.

**Start.** Create a worktree, never switch branches in a shared checkout:

```
git worktree add ../vorpal-sN -b feat/<scope> main
```

**During.** Touch only the files your prompt says you own. If you need a
contract change, stop and open a separate contract PR.

**Finish.** Before you open the PR:

1. Write `docs/handoffs/SN.md` — what you built, what you learned that the next
   session cannot see from the code, anything in the spec that turned out to be
   wrong or ambiguous.
2. Update your own row in the PLAN.md section 3 table to `DONE` (or
   `BLOCKED: reason`).
3. Update the prompt file of every session that depends on you, with the real
   function signatures they will call and any gotcha you hit.
4. If your work makes a *new* session necessary, write its prompt file and add
   its row.

A PR that does not do all four is not finished.

Shared files after the seed (`pyproject.toml`, `src/vorpal/contracts.py`,
`src/vorpal/errors.py`) are frozen. Do not edit them. Handoff notes go in
`docs/handoffs/SN.md`, one file per session.

## Do not

- Write to Sleeper, scrape, drive a browser, or reverse-engineer internal APIs
  beyond the projections host the spec already accepts.
- Hardcode any league's settings, scoring, or roster. Read them at runtime.
- Commit `private/`, `*.local.json`, or anything that identifies a league or
  its managers.
- Ingest a fantasy-points column. Apply the league's scoring to counting stats.
- Silent-zero an unmatched nonzero scoring key. Report it before the board
  renders.
- Add an executor or write-plugin. One implementation is not an interface.
- Fit a market model on this league's draft history (later, not v1).
- Build lineup, waiver, or trade policy in v1. Draft only.
- Add a chance-to-last-until-the-next-pick number. Wait-vs-take is the
  model's. SPEC.md section 4 is explicit.
- Treat last-starter value as a deeper waiver baseline. v1 value is VOLS
  (last starter). Deeper baselines are later.

## Facts agents miss

- **Slots, not scoring, decide what starts.** A league can store K/DEF scoring
  with no K/DEF slot. The wire code is `DEF`, not `DST`. The wire code is
  `SUPER_FLEX`, not `SUPERFLEX`.
- **Refuse, do not degrade:** keeper/dynasty (`settings.type ∈ {1,2}` or
  `taxi_slots > 0`), IDP slot codes, auction, linear, `reversal_round ≠ 0`.
  `max_keepers > 0` on `type == 0` is **not** a refusal: banner *keepers
  possible* and proceed. A truthy `is_keeper` on a pick drops that player
  from the pool.
- **Unknown draft slot:** omit `next_user_pick`, `picks_until_next`, and
  `between`. Do not guess the seat.
- **Mapping fail-closed:** match on `player_id` where you have it; else
  name+pos+team, then name+pos (flag team mismatch). If match rate on the
  top 300 by ADP is below 98%, refuse and print the report.
- **K/DEF rows** are required when those slots exist. If a slot exists and
  the file has no rows, use a flat baseline and state that on the board.
- **VOLS (SPEC.md section 3):** two passes (points, then VOLS). Bench is not
  absorbed. Fill flexible slots most-restrictive first. A hypothetical further
  pass must not move any position's replacement rank by more than 2 — that is
  a failing eval, not a comment. `vols = points − replacement[position].points`.
- **The pick is the model's.** Code ships `hint_argmax_vols` as a calculator,
  not the answer. Rec ≠ hint without `VOLS_DISSENT` fails the call.
- **`/players` has no bye field** on the recorded bytes. Do not invent one.
  FantasyPros rows carry `player_bye_week`. Join ECR on `yahoo_id`
  (Sleeper int or null) / `player_yahoo_id` (string).
- **Standalone mocks** have `league_id: null`. Slots come from the mock.
  Scoring is borrowed from a named other league. Banner both. They may
  disagree. A borrowed scoring league never overrides slots.
- **Evals:** every gate is pass, fail, or `NOT_PERFORMED`. No scores, no
  “lean”. The golden set is the main eval limit. Outcome replay without a
  dated pre-draft file is `NOT_PERFORMED`, never a caveated number. Do not
  sample board states from a fitted wait model. There is none in v1.
- **Draft-night poll:** 3s while `drafting`; 15s otherwise until `complete`.
  Error backoff 5/15/45s, then hold. Always show data age. Past 15s, degrade
  visibly. Grey the recommendation at `pick_timer` (skip if the timer is
  0/null). Never present a stale board as current. Observed statuses include
  `pre_draft`, `drafting`, `complete`, and `paused`.
- **Shared layer across sports is ingest + projections only.** Do not
  generalize the player-value model.
- **Rate limit:** stay under 1000 calls/min. Fetch `/players` at most once
  per day (~5MB). Fetch projections and FantasyPros once per process. Never
  poll them.

## Layout and toolchain

```
src/vorpal/sleeper     platform read (documented api.sleeper.app)
src/vorpal/ingest      projections, ECR, override CSV
src/vorpal/resolve     slots, scoring source, seat, refusals
src/vorpal/valuation   scoring, VOLS, weekly vector, delta
src/vorpal/payload     board cap and serialisation
src/vorpal/model       the call
src/vorpal/evals       the eleven gates and three baselines
src/vorpal/board       local HTML page and poll loop
src/vorpal/cli.py      one owner, after the modules merge
tests/fixtures/        redacted recorded JSON from the seed
evals/                 eval run and report
```

Refusal taxonomy (load-bearing). All are `VorpalError`. CLI prints them to
stderr and exits 2. Do not collapse the classes.

| Class | Meaning |
|---|---|
| `UnsupportedLeague` | Permanent. Format is out of v1. |
| `DataRefusal` | Fixable by a better file. |
| `PlatformError` | The API or projections host. |
| `UserRefusal` | Operator identity or seat. |

Commands:

```
uv sync
uv run pytest
uv run pytest -m golden
uv run pytest -m invariant
uv run pytest -m live
uv run ruff check .
uv run ruff format .
```

Python >= 3.12. CI is 3.12 and 3.13. The `live` marker is deselected in CI.

Pytest markers: `invariant` (VOLS rank-2), `golden` (SPEC.md section 5),
`live` (network). A marker failure on `invariant` or `golden` is a model
problem, not a code bug.
