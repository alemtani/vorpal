# S10 eval report

Live model. Eval path is `recommend` / `run_stability`. Draft night
`propose` was not used on any scored fixture.

**Verdict.** On the golden set the model separates from `argmax_vols`. It
passed all 12 human verdicts. The calculator failed the three cases S9
named. SPEC.md section 5 asked for that separation. The other gates
mostly do not separate, and several were not measured. Do not tune the
gates on this table.

---

## Four-column table

Fixtures in this table: **12 golden cases + 4 regret seats = 16**. Pass
rate ignores `NOT_PERFORMED`. `s=N` is the skip count. A matching model
and `argmax_vols` rate is marked `NO DISCRIMINATING POWER`.

```
gate            model           argmax_vols     adp_follow      ecr_follow      note
schema          1.00            1.00            1.00            1.00            NO DISCRIMINATING POWER
golden_forbid   1.00 s=4        0.75 s=4        0.92 s=4        0.83 s=4
golden_require  1.00 s=4        0.92 s=4        1.00 s=4        0.92 s=4
vols_dissent    1.00            1.00            1.00            1.00            NO DISCRIMINATING POWER
ecr_dissent     0.93 s=2        1.00 s=2        1.00 s=2        1.00 s=2
ecr_sanity      1.00 s=2        1.00 s=3        1.00 s=4        1.00 s=2        NO DISCRIMINATING POWER
bye_hole        0.07 s=2        0.00 s=3        0.00 s=4        0.00 s=2
stability       1.00 s=3        1.00            1.00            1.00            NO DISCRIMINATING POWER
vols_invariant  1.00 s=12       1.00 s=12       1.00 s=12       1.00 s=12       NO DISCRIMINATING POWER
regret          0.50 s=12       0.75 s=12       0.75 s=12       1.00 s=12
replay          — s=16          — s=16          — s=16          — s=16          NO DISCRIMINATING POWER
```

### Counts (pass / fail / skip)

| gate | model | argmax_vols | adp_follow | ecr_follow | separates |
|---|---|---|---|---|---|
| `schema` | 16/0/0 | 16/0/0 | 16/0/0 | 16/0/0 | no |
| `golden_forbid` | 12/0/4 | 9/3/4 | 11/1/4 | 10/2/4 | yes |
| `golden_require` | 12/0/4 | 11/1/4 | 12/0/4 | 11/1/4 | yes |
| `vols_dissent` | 16/0/0 | 16/0/0 | 16/0/0 | 16/0/0 | no |
| `ecr_dissent` | 13/1/2 | 14/0/2 | 14/0/2 | 14/0/2 | yes |
| `ecr_sanity` | 14/0/2 | 13/0/3 | 12/0/4 | 14/0/2 | no |
| `bye_hole` | 1/13/2 | 0/13/3 | 0/12/4 | 0/14/2 | yes |
| `stability` | 13/0/3 | 16/0/0 | 16/0/0 | 16/0/0 | no |
| `vols_invariant` | 4/0/12 | 4/0/12 | 4/0/12 | 4/0/12 | no |
| `regret` | 2/2/12 | 3/1/12 | 3/1/12 | 4/0/12 | yes |
| `replay` | 0/0/16 | 0/0/16 | 0/0/16 | 0/0/16 | no |

Golden skips `vols_invariant`, `regret`, and `replay` (no full pool, no
completed-draft survival, no dated projections). Regret skips the two
golden gates. Replay is `NOT_PERFORMED` on every fixture: S9 shipped no
dated projections file.

---

## Does the model separate?

**Yes, on golden_forbid and golden_require.** That is the only pair this
set can use to answer SPEC.md section 5. S9 already said `argmax_vols`
fails 3 of 12 golden cases, and that three cases is the ceiling.

The model passed all 12. The calculator failed:

| Case | Calculator pick | Model pick | Human verdict |
|---|---|---|---|
| `third_te_while_wr_empty` | `te-third` (forbid) | `wr-a` + `VOLS_DISSENT` | require a WR |
| `bye_stack` | `wr-bye-clash` (forbid) | `wr-bye-clear` + `VOLS_DISSENT` + `BYE_STACK` | require the bye-5 WR |
| `empty_starter_late` | `wr-depth` (forbid) | `k-a` + `VOLS_DISSENT`, `coin_flip` | require K or DEF |

`golden_require` only fails `argmax_vols` on `empty_starter_late`. The
other two calculator misses still named a required player as the
alternative, so require passed. The model also took `wide-b` on
`vols_compressed` (`VOLS_DISSENT`, `UPSIDE`, `coin_flip`) instead of the
hint `flat-a`. Require still passed for the calculator because the
alternative can satisfy the set.

Twelve cases. One flipped verdict moves the rate by eight points. Do not
read 1.00 as "the model is good." Read it as: it avoided the twelve
mistakes a human marked, and it did so on the three boards where the
calculator does not.

### Gates that do not separate, or barely do

- **`schema`.** Floor. Everyone passed.
- **`vols_dissent`.** Floor. The model set the flag when it left the
  hint. Baselines set it mechanically.
- **`ecr_sanity`.** Floor. Everyone who ran stayed inside the margin.
- **`stability`.** The model was 13/13 performed (three `coin_flip`
  skips: `empty_starter_late`, `vols_compressed`, `superflex_seat07_r02`).
  Baselines are deterministic, so they always pass. Same rate, no
  information.
- **`vols_invariant`.** About our arithmetic, not the model. Pass on the
  four regret pools. Skip on golden (no full pool).
- **`ecr_dissent`.** The model is *worse* than the calculator (13/14 vs
  14/14). The one fail is `te_cliff`: rec was `te-elite` (correct, and
  the hint), ECR 26, `ecr_best` is `rb-g` at 25. The first of five calls
  did not set `ECR_DISAGREE`. The pick was right. The XOR flag was
  wrong. Later reruns set the flag. The eval uses the first call.
- **`bye_hole`.** 1/14 model, 0/13 calculator. S9 already pinned this:
  the gate compares alternatives only in the rec's own bye week, so a
  short position fails both candidates. The one model pass is
  `vols_compressed`. This is a spec question. Do not patch the gate to
  make the rate look better.
- **`regret`.** 2/4 model, 3/4 calculator, 4/4 `ecr_follow`. Four seats,
  public-API 60-player boards (see below). This is not evidence the
  model is worse at wait-or-take. It is four coin flips on a truncated
  market.

Do not retune gates until a larger set exists. The golden pair already
separates.

---

## Forecast cap (every live board)

The FantasyPros key in this environment is the public API. Every list
returns `public_api_limited: true`, `limit: 10`.

Measured:

- ADP `ALL` PPR: 10 rows (count 684)
- ADP `OP`: 0 rows, so superflex banners `adp_1qb_market`
- ECR overall: 10 rows
- Projections across six positions: 60 rows

`load_forecast` still returns. The 98% mapping gate runs on the top-N
*present* ADP rows, so 10/10 passes. VOLS then runs on 60 players. That
is not a draft board. Regret, the operator's two mocks, and the live
rehearsal all used this universe. Golden did not: those payloads are
hand-written.

A paid FantasyPros key is required before any live-forecast number is
worth a draft-night decision.

---

## Golden (12 cases, full model)

Eval path. Five identical payloads per case, unless `coin_flip`.

No schema violation. No stability fail. Two `coin_flip` skips, both on
boards the case was written to make close (`empty_starter_late`,
`vols_compressed`).

Per-case recs are in `evals/results/golden.json`. `case.why` is next to
any fail there. The only model gate fail besides `bye_hole` is
`te_cliff` / `ecr_dissent`, described above.

---

## Regret (4 seats, 3 drafts)

Boards built from recorded picks plus the capped live forecast. Era mix:

- `snake_redraft_*`: 2025 recorded survival, 2025 FP lists (still 10/60)
- `superflex_seat07_r02` and `mock_standalone_seat06_r05`: 2026

`vols_invariant` passed on all four full available pools.

Regret gate (rec survived to next pick, a listed alternative did not):

| Fixture | Model rec | Hint | Actually picked | Regret |
|---|---|---|---|---|
| `mock_standalone_seat06_r05` | hint | same | different | FAIL |
| `snake_redraft_seat02_r03` | left the hint | — | different | PASS |
| `snake_redraft_seat02_r09` | left the hint | — | different | PASS |
| `superflex_seat07_r02` | hint, `coin_flip` | same | different | FAIL |

`ecr_follow` passed all four. That is "always take the name the experts
rank first, and in these four rooms that name was gone or the
alternative survived." It is not a policy to ship.

Replay remains skip. No dated projections file.

---

## Operator mocks (two completed 10-team superflex, seat 1)

Transcribed from the operator. 140/140 names joined onto host ids.

**The model did not score these.** After golden + regret + the live
loop, Anthropic returned `credit balance is too low` on every one of
the 28 `recommend` calls. Schema is 0.00 for the model on this family
because there was no readable proposal. Baselines still ran.

Agreement of baselines with the recorded pick, 28 seat-1 turns:

| Policy | Match |
|---|---|
| `argmax_vols` | 4 / 28 (0.14) |
| `adp_follow` | 2 / 28 (0.07) |
| `ecr_follow` | 6 / 28 (0.21) |

At 1.01 both drafts took Josh Allen. `ecr_follow` agreed. `argmax_vols`
took Jahmyr Gibbs. That is the superflex / 1QB tension — except the
forecast used 1QB ADP (`adp_1qb_market`) on a superflex config because
OP ADP was empty. Do not read this as "the calculator is wrong in
superflex." The market it saw was not a superflex market.

Stability was not run (28 × 5 calls). Replay skip. Report these 28 as a
human baseline against the three rules, not as a model measurement.

---

## Dress rehearsal

### What ran

1. **`--once` cold start** against the standalone mock id the operator
   sent, while it was still `pre_draft`, 0 picks, 12-team 1QB, 60s
   `pick_timer`. Scoring borrowed from the operator's 2026 PPR league
   (slots stayed on the mock). Wall **16.9s**. Model **8.3s**. First rec
   was Jahmyr Gibbs (the VOLS hint on that capped board). Under 60s.

2. **Poll loop** on that same id after it went `drafting`. `pick_timer`
   on the wire was then **30s**. Poll 3s. Model calls while within two
   picks of seat 7: 14.6s, 12.4s, 11.9s, 11.8s. All under 30s. The page
   wrote. Grey-out is data age, not the pick clock; a 12s call still
   leaves time to read.

3. The operator then said they had **not started** that mock. The id
   was a 12-team 1QB lobby they were seated in (slot 7), CPU autopick
   on, already picking. The poll was stopped. That loop is **not** a
   dress rehearsal of the 10-team superflex they described.

### What did not run

- No poll loop against a mock the operator started and sat in.
- No timing of "read the board and click" on their 10-team superflex
  clock.
- After the credit error, a new live `propose` would fail until the
  Anthropic account has balance.

The timing numbers above are still the only live pick-clock measurement
this session has: cold start 17s, on-clock model 12–15s, timers 30–60s.
That is enough to say the loop can write a board before a 30s clock
expires, on this machine, with this capped forecast. It is not a
draft-night dress rehearsal of the league they will actually play.

---

## Operator note: the page is not usable on a clock

The operator sat with `board.html` and called it clunky. That is the
right read. The last written page from the live loop had:

- **Ten loud red banners** before the pick. Scoring-key dumps, borrowed
  league prose, keepers, `board_capped`, stale-data, a raw Anthropic
  JSON credit error, and `proposal_not_current`. Spec wanted banners
  loud. On a 30s clock they ate the viewport.
- **The rec heading was `8151`.** The recommendation was for pick 18,
  shown at pick 28, and that player was no longer on the capped board,
  so the renderer fell back to the raw id. Alternatives mixed names and
  ids.
- **Eighteen identical week rows**, each listing every empty starter
  slot in red. After two picks the weekly vector is still mostly holes.
  It does not help a click.
- **No countdown.** The header prints `Pick timer: 30s` as a setting,
  not time left. Age is a frozen number from the last write. The whole
  page meta-refreshes every 3s.
- **A spreadsheet under the rec** with column headers
  `delta_starter_points`. ADP was 0.0 on every row (public FP cap).

The pick the operator can act on has to be the first thing on the page.
Banners that are not about *this* pick belong in a fold, or off the
night view. That is a board session, not an eval-gate session. See
`docs/prompts/S12.md`.

**One CLI fix shipped after this note.** The poll loop no longer calls
the model within two picks of the seat. It calls only when
`picks_until_next == 0`. Other turns show the calculator. `--once` still
asks, because that command is "give me a rec for this board." The Walker
rec arrived in time *because* of the old window. The new rule saves
tokens and will spend ~12s of the pick clock on the call.

---

## What failed

- `bye_hole` fails almost every performed board. Spec, not a code bug.
- `te_cliff` silent ECR dissent on the first of five calls.
- Regret 2/4 for the model on truncated boards.
- Human family: 28/28 model calls failed with Anthropic credit
  exhaustion.
- FantasyPros public cap: 10 rows per list.

## What this session did not measure

- Replay (no dated projections).
- VOLS invariant on golden (no full pool).
- A paid FantasyPros universe (ADP/ECR/stats past row 10).
- Model vs the operator's two mocks (credits).
- Stability on those 28 turns.
- Flags other than the two XOR bits (`UPSIDE`, `POSITION_RUN`,
  `BYE_STACK`, `EMPTY_STARTER` are unmeasured as evals).
- A dress rehearsal of the operator's own mock, under their pick timer,
  with them reading the page.

---

## How to repeat

```sh
cd ../vorpal-s10   # feat/eval-run worktree
export ANTHROPIC_API_KEY=...
export FANTASYPROS_API_KEY=...   # paid key, or the table is a toy
uv run python evals/run.py                  # golden + regret + human
uv run python evals/run.py --only golden    # cached under evals/_cache
uv run python evals/rehearse.py \
  --draft-id ID --operator NAME \
  --scoring-league-id LEAGUE \   # standalone mock only
  --max-seconds 900
```

Open `evals/_cache/rehearsal/board.html`. Golden model raws are cached;
re-running `--only golden` does not spend five new calls per case.
