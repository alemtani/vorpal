# vorpal — Specification (draft for review)

**Status:** proposal, pre-implementation

This document is written for adversarial review. Section 10 defines v1.
Section 11 lists design risks, weakest first. Reviewers should attack the
premise, not only the wiring.

---

## 1. Problem

Fantasy sports decision support: draft, weekly lineups, waivers, and trades.
The system recommends; the human executes.

First target platform is Sleeper (NFL), **redraft**. The tool is configured by
league ID and derives everything else from the platform API. No league's
settings, scoring, or roster shape are hardcoded.

Scope is a personal tool. Dynasty, keeper, and IDP formats are out. Nothing
here assumes commercial use, and the ethics constraints in §13 assume a human
who is a member of the league being analyzed.

## 2. The binding constraint

Sleeper's public API is **read-only**. Its documentation states: "No API Token
is necessary, as you cannot modify contents via this API." Every GET needed
exists (league, rosters, matchups, transactions, drafts, picks, players,
trending). There are no write endpoints.

Three possible write paths:

| Path | Mechanism | Risk |
|---|---|---|
| Manual | Human acts in the platform UI | None |
| Browser automation | Drive the platform web app | Fragile UI, session handling, ToS gray area |
| Internal API | Reverse-engineered endpoints | Breaks silently, clearest ToS violation, ban risk |

**Decision:** the human executes. Every policy emits a proposal; the user acts
in the platform UI. This keeps the valuable work unblocked by the fragile
work, and it is the only path with no terms-of-service exposure.

No plugin interface is introduced for this (§5).

Rate limit: stay under 1000 calls/minute. The `/players` endpoint is ~5MB and
should be fetched at most once per day.

## 3. League configuration

All league parameters are read from the platform API at runtime:

- Roster slots (including SUPER_FLEX, OP, and other non-standard slots)
- Scoring settings (PPR variants, TD values, TE premium, per-yard rates)
- Draft type, rounds, order, pick timer
- Waiver type, FAAB budget, minimum bid, processing day
- Trade deadline, veto rules, playoff structure and start week
- Keeper and taxi settings

**No format may be assumed.** Notably, some leagues start no kicker and no
defense while still carrying nonzero K/DST scoring values in their settings —
the presence of a scoring rule does not imply a startable slot. Slot
composition is the authority, not the scoring table.

### Unsupported formats — detect and refuse

v1 supports **snake redraft, offense-only**. The following are detected from
league settings and **refused with an explicit message**, not silently
mishandled:

| Condition | Signal | Why refuse |
|---|---|---|
| Keeper / dynasty | `max_keepers > 0` with keeper picks present, or taxi slots | Kept players must be removed from the pool; not implemented |
| IDP | Defensive player slots in roster positions | Offensive projection files have no rows for these slots |
| Auction | Draft type is auction | Budget allocation, not pick order; survival by pick number is meaningless |
| Linear draft | Draft type is linear | Supported, but survival math must use linear pick spacing |

Refusing is the v1 behavior. Degrading with a visible banner is acceptable
only where the degradation is stated on the board itself.

### Unknown draft slot

Draft order may be unset or may change before the draft. When the user's slot
is unknown:

- The board ranks by value only.
- Survival probabilities are **hidden**, not estimated. Survival is a function
  of slot, team count, and snake direction; without a slot there is no answer,
  and a guessed one is worse than none.
- The board recomputes and reveals survival as soon as the slot is set.

## 4. League-specific market modeling — deferred past v1

Positional pricing varies between leagues, and a league's own draft history is
evidence about it. The tool could fit a market model over prior drafts: when
each position comes off the board, where runs occur, where dead zones open.

**Not in v1.** A league typically has one or two prior drafts available. That
is a handful of managers' idiosyncrasies, not a market, and fitting it invites
confident nonsense. v1 uses public ADP for the format. See §11.1.

If this is built later, no specific league's tendencies belong in this
document or in code.

## 5. Architecture (proposal)

```
league state (platform read API)  ─┐
projections + distributions       ─┼──> valuation engine
player DB / news / injuries       ─┘    (VORP, league-specific replacement)
                                              │
        ┌─────────────┬─────────────┬─────────┴────┐
     draft         lineup        waivers        trades
     policy        policy        policy         policy
```

Each phase is a thin **policy** over one shared valuation engine:

- **draft** — best available given roster construction and picks-until-next
- **lineup** — max projected points over legal slot assignments
- **waivers** — draft policy with a FAAB budget instead of picks
- **trades** — difference of two roster valuations

**The diagram above is the full product, not v1.** v1 builds the read layer,
the valuation engine on point estimates, and the draft policy only. News,
injuries, distributions, and the other three policies are later phases.

### The v1 pick objective

The policy is a function, and it must be written as one or the eval in §9.2
has no referent:

> At each pick, recommend the available player that maximizes **expected
> starting-lineup VORP of the resulting roster**, where a player's
> contribution counts only if the roster has a legal slot for them, and where
> players available at the user's next turn with high probability are
> discounted by their survival probability (§8).

This is **one-step lookahead**, not static VORP and not myopic take-best. The
distinction is the product: static VORP takes the third receiver while a
starting slot sits empty; myopic take-best takes a player who would have
survived two more rounds.

Explicitly out of v1: multi-step lookahead, opponent-specific reasoning,
positional run detection.

### Proposal fields

Every policy emits a `Proposal`:

| Field | Meaning |
|---|---|
| `player_id` | Platform player ID |
| `objective_value` | Expected starting-lineup VORP after this pick |
| `alternatives` | Ranked runners-up with their objective values |
| `rationale` | Which slot this fills, and the survival term applied |
| `confidence` | Gap to the next alternative; small gaps are coin flips |

The human acts in the platform UI. There is no executor abstraction in v1 — a
plugin interface with exactly one implementation and no second implementation
planned is speculative generality.

## 6. Data sources

| Need | Source | v1? |
|---|---|---|
| League state | Platform read API | Yes — free, no auth, authoritative |
| Projections | One third-party **counting-stat** file, user-supplied | Yes — see below |
| ADP / market | Public ADP for the format, user-supplied | Yes |
| Usage detail | nflverse snap counts, target share, routes | No — waiver-phase input |
| Injury / news | nflverse injury reports; public endpoints | No |

### Buy the forecast, build the scoring

The valuation engine needs expected points per player in *this league's*
scoring. It does not follow that the tool must forecast the NFL.

**v1 buys counting stats and builds everything downstream.** The user drops one
projection file — passing yards, rushing yards, receptions, touchdowns — into
`private/`. The tool maps players to platform IDs, applies the league's actual
scoring settings, derives replacement levels from the league's slots, and
ranks by value over replacement.

What is trusted: someone else's yards and touchdowns. What is *not* trusted:
their fantasy-point totals, which encode a scoring format that is not this
league's. For non-standard formats — superflex, no-kicker, TE premium — that
distinction is most of the value.

Deriving projections from play-by-play is a months-long forecasting project
and is not a prerequisite for drafting. It is out of scope indefinitely.

**Files are user-supplied and manual.** No scraping in v1. A live scrape is a
dependency on someone else's HTML during the window when a break is least
affordable, and it is the clearest terms-of-service exposure. Automated
fetching may be added later, per-source, where terms permit.

### Projection file contract

CSV, one row per player, **season totals** (not weekly).

Required: `name`, `team`, `position`.
Required stat columns, zero-filled where inapplicable: `pass_yd`, `pass_td`,
`pass_int`, `rush_yd`, `rush_td`, `rec`, `rec_yd`, `rec_td`, `fum_lost`.
Optional: `two_pt`, `fg_made`, `fg_att`, `xp_made`, and any further columns
the league's scoring references.

**K and DST rows are required when the league has K or DST slots.** Where the
league has no such slot, they may be omitted. Where a slot exists and the file
lacks rows, the tool assigns a flat positional baseline and **states this on
the board** — it does not silently omit the position. The §9.3 golden-set
case ("a kicker in round 3") is unscoreable otherwise.

**Unmatched scoring keys fail loudly.** For every scoring setting in the
league with a nonzero value, the tool resolves a stat column. Any nonzero
scoring key with no column is **reported before the board renders**, listing
the key and its value. The user chooses to proceed (contributes zero) or to
supply a better file. It is never a silent zero — silent zeros erase exactly
the league-specific scoring this tool exists to handle.

**Never ingest a fantasy-points column**, even when present. It encodes a
scoring format that is not this league's.

### ADP file contract

CSV: `name`, `team`, `position`, `adp`. Optional `adp_stdev` (§8).

**Transport is a file, not an API.** §10.4's "public ADP" means a
user-supplied export. The platform's `trending` endpoint is not ADP and is not
a substitute.

**Format match is checked, not assumed.** The user declares the ADP product's
format. If the league has a SUPER_FLEX or OP slot and the declared ADP is
standard, the tool warns prominently — standard ADP misprices quarterbacks in
superflex badly enough to invalidate the board.

### Player ID mapping

Mapping the projection and ADP files to platform IDs is a v1 deliverable and a
known source of silent corruption (§11.7).

1. Match on normalized name + position + team.
2. Fall back to normalized name + position, flagging the team mismatch.
3. Everything else is unmatched.

Normalization strips punctuation, case, and generational suffixes.

The tool emits a **mapping report** before the board renders: counts matched
at each tier, and every unmatched player above a relevance threshold, by name.

**Fail closed.** If the match rate among the top 300 players by ADP falls
below **98%**, the tool refuses to render a board and prints the report. A
board with silent holes looks correct and is not.

## 7. Valuation

Compute value over replacement from projections, using the configured
league's actual replacement levels rather than generic ones.

Replacement level is a function of the league's slot composition and roster
depth. It must be derived from the configured slots, not assumed from a
standard-format table.

**v1 ranks on expected points.** Point estimates only. Distribution-aware and
ceiling-weighted logic is a later phase (§9.5).

### Algorithm

Let `T` = number of teams. Slots come from the league's roster positions.

**Pass 0 — rank key: projected points.**

1. For each position, sort all players by projected points.
2. Fill dedicated slots: for each dedicated slot type (QB, RB, WR, TE), absorb
   the top `T × (slots of that type)` players at that position.
3. Fill flexible slots: pool all remaining players eligible for each flexible
   slot type, sort by projected points, and absorb the top `T × (slots of that
   type)`. Process flexible slots **most-restrictive first** — FLEX (RB/WR/TE)
   before SUPER_FLEX or OP (which additionally admit QB) — so the broader slot
   draws from what the narrower one left.
4. **Bench slots are not absorbed.** Replacement level is defined by who
   starts, not who is rostered. Bench depth affects the draft pool, not the
   baseline.
5. Replacement for a position = projected points of the **first player at that
   position not absorbed** in steps 2–3.

**Pass 1 — rank key: VORP from pass 0.**

6. Repeat steps 2–3, sorting by pass-0 VORP instead of raw points. This is the
   only thing that changes, and it is the whole reason the computation is
   circular: flexible-slot allocation should reflect value over replacement,
   which pass 0 did not have.
7. Recompute replacement per step 5. **Stop.**

### Stop rule as an eval, not a comment

Pass 1 can move ranks, and in superflex it is most likely to — that is the
format this tool is for. So the convergence claim is testable, not assumed:

> **Invariant:** a hypothetical pass 2 must not move any position's
> replacement rank by more than **2**.

This runs as a **failing eval** in the §9.3 suite, not as a code comment. A
breach means the greedy approximation is inadequate for that league shape and
the board should not be trusted. It does not mean "build a fixed-point
solver" — it means investigate before drafting.

Small errors here dominate: a few ranks of movement in a position's
replacement level can invert the recommended ordering between positions.

Projection *distributions* matter, not only means. Late in a draft the correct
objective shifts from median toward ceiling.

**Rankings are not projections.** Ordinal consensus data cannot produce true
VORP or uncertainty estimates. It enters as a market prior only.

## 8. Survival model

Predicts whether a player is still available at a future pick. The draft
policy's "can I wait a round on this player" logic is entirely downstream of
it, and on draft night it is the highest-value output after value itself.

**v1: public ADP plus an explicit placeholder dispersion.** A probability
shipped with an unspecified variance is worse than showing ADP and no
probability at all, so the placeholder is written down and labelled:

- **Family:** normal over pick number, truncated below at pick 1.
- **Dispersion:** `adp_stdev` from the ADP file where the source provides it.
  Where it does not, `σ = max(4, 0.30 × ADP)` — dispersion grows with ADP
  because late-round consensus is weaker. **This is a placeholder**, chosen
  for plausible shape, not fitted. It is flagged as such on the board.
- **Already drafted:** survival probability 0. Not a distribution.
- **Independence:** players are treated as independent. This is **known to be
  wrong** and the direction of the error is known — real drafts have
  positional runs, so joint survival of two players at the same position is
  overstated. "Can I wait on both of these receivers" is therefore the
  question v1 answers worst.

Because the dispersion is a placeholder, the board shows survival in **coarse
bands** (likely / toss-up / unlikely) rather than a decimal probability. The
precision of a number implies a calibration that does not exist yet.

Calibrating dispersion against real draft data is §9.6.

Fitting the configured league's own draft history is deferred (§4). Note that
public ADP is itself an opponent model with a flat prior — the v1 cut removes
the *fitting*, not the survival curve.

The gap between the valuation model and the market model is the edge.

## 9. Evaluation

A draft happens once a season and the outcome is dominated by luck. "Did we
win" is not a signal. Score decisions, not results.

### 9.1 Error decomposition (core)

For every pick, compare three choices:

1. what the policy picked
2. what it should have picked **given its own projections** → gap = **decision error** (logic bug)
3. what it should have picked **given actual end-of-season value** → gap = **projection error** (data problem)

Conflating these is why most fantasy tools never improve.

The decomposition also determines *which evals are runnable at all*. Decision
error and projection error have completely different data requirements, and
only one of them is blocked by history.

### 9.2 Decision error — runnable, no historical data (v1)

Decision error is an **internal consistency test**. It asks whether the policy
picked what its own value model says was best, given roster state and picks
until the next turn.

The same projections sit on both sides of the comparison and no outcomes are
involved, so **there is nothing to leak**. It needs no point-in-time file and
no completed season. It can run today, across thousands of simulated board
states.

It catches **computation** bugs: a wrong implementation of the §7 fill, roster
construction that mishandles flexible slots, survival terms applied to the
wrong pick, arithmetic in the objective.

It **cannot** catch a wrong value model. If §7 defines replacement badly and
the code implements that definition faithfully, every check passes. Model
correctness is the golden set's job (§9.3) and the invariant in §7.

### Board-state generation

The "simulated board states" must come from somewhere, and the choice matters:

**v1 uses a separate sampler, not the survival model.** States are generated
by removing players from the pool according to ADP order with injected noise,
across a grid of round numbers and roster compositions.

Using the survival model as the generator would rest the one committed eval on
the one unfitted placeholder input (§8) — the eval would agree with the policy
by construction. A separate sampler tests states the policy might not predict,
which is the point.

The sampler must include adversarial states, not just plausible ones: runs
that empty a position, a roster with every flexible slot filled, the user's
last pick.

This is the eval v1 commits to.

### 9.3 Golden set (v1)

A small set of hand-labeled scenarios with confident correct answers — a
kicker in round 3, a third tight end while a starting slot sits empty. Runs in
seconds, catches regressions during rapid iteration.

**This is an external oracle, and it is the only v1 eval that can catch a bad
value model.** §9.2 asks whether the code matches the model; the golden set
asks whether the model matches reality, using human judgement as the label.
It is not a special case of §9.2 — it is the other half.

It may assume only what a competent human would assert without a projection
source: a kicker in round 3 is wrong, a third tight end while a starting slot
sits empty is wrong, a quarterback taken in a superflex league at a pick where
two remain and eight teams need one is right.

Because §7's convergence invariant is also a labelled assertion about model
correctness, it runs here.

### 9.4 Outcome replay — conditional (and it is not projection error)

Replay a historical draft: sit in the user's actual slot, hold every other
pick fixed, let the policy choose. Score both rosters on **sum of optimal
weekly lineup** in that season's scoring, which strips out start/sit noise and
measures the draft alone.

The question this answers is narrow and worth stating plainly: *given the
board that actually happened, would the policy have drafted better than the
user did?* It does **not** answer whether the user would have won, because
the other drafters would not have behaved identically. For a personal tool the
narrow question is enough.

**This eval is blocked on a projection file dated before that draft.** Running
it on today's projections, or on end-of-season results, measures
hindsight-optimal value — which always looks brilliant and says nothing about
draft night.

Sources of a dated file, in order of likely success: web archive snapshots of
public projection pages from the relevant week (point-in-time by
construction), then paid historical archives, then nothing.

**If no dated file is found, this eval is reported as NOT PERFORMED.** Not as
a caveated number. A leaky result must never gate a decision.

**This is not projection error.** §9.1 item 3 defines projection error as the
gap between *the best pick given the model's projections* and *the best pick
given actual end-of-season value*. That is a property of the projection
source, measurable without any policy at all. Outcome replay is a different
thing: policy-versus-user on a frozen board, which mixes model quality,
projection quality, and the user's own decisions into one number.

Reporting replay as projection error would be exactly the conflation §9.1
says kills these tools. Projection error proper is also conditional on a dated
file and is **out of v1**.

### 9.5 Monte Carlo — later

Simulate many drafts with market noise, then simulate seasons from projection
distributions. Reports the distribution of outcomes and separates close calls
from real decisions. Valuable, not required to draft.

### 9.6 Survival model calibration — later

How well does the survival model predict when players actually went? Report
calibration curves, not accuracy.

## 10. Scope and phasing

### v1 — what ships before the draft

1. Read the platform API: league, roster slots, scoring, draft state. Refuse
   unsupported formats (§3).
2. Load a user-supplied projection file and ADP file from `private/` against
   the contracts in §6. Emit the mapping report. Fail closed below threshold.
3. Apply the league's scoring. Report any unmatched nonzero scoring key.
4. Replacement levels by the §7 algorithm, with the convergence invariant
   running as an eval.
5. Survival bands from ADP and the §8 placeholder dispersion. Hidden entirely
   when the draft slot is unknown.
6. Draft policy implementing the §5 objective, emitting `Proposal`s.
7. Board: value, ADP, legal slots, survival band, roster needs. Local page
   polling the draft API (see below).
8. Decision-error evals (§9.2) and the golden set (§9.3).
9. Outcome replay **only** if a pre-draft projection file is found (§9.4).

Explicitly not in v1: projection error as defined in §9.1, market model fitted
on league history, distribution/ceiling logic, multi-step lookahead, waiver
engine, trade engine, executor abstraction, multi-sport layer, any scraping.

### Draft-night polling contract

The board is a local page polling the draft API. Draft night is the one window
where a silently stale board is unrecoverable, so the failure behavior is
specified, not left to the implementation:

- **Interval:** 3 seconds while the draft is active. Well inside the platform
  rate limit (§2) for a single league.
- **Backoff:** on error, retry at 5s, 15s, 45s, then hold at 45s. Reset on
  first success.
- **Staleness is always visible.** The board shows the age of its data at all
  times, not only on failure. Past 15 seconds the display degrades visibly.
- **Never render a stale board as current.** If the last successful poll is
  older than one pick interval, the recommendation is greyed and marked
  unreliable.

### Later phases

| Phase | Deliverable | Gating |
|---|---|---|
| v2 | Weekly lineup optimizer | Week 1 |
| v3 | Waivers + FAAB bid sizing | Week 2 |
| v4 | Trade evaluation (inbound), then proposal (outbound) | Week 3+ |
| — | Market model fitted on league history (§4) | Needs multiple seasons |

### Non-goals

- Automatic execution of any kind
- Outbound trade proposals sent without human review
- Competing with the platform at being a fantasy app
- Multi-sport implementation (see below)

### Multi-sport constraint

Intended extension to NBA, FPL, and bracket pools. These are **not one
problem**:

- **Draft-and-manage** (NFL, NBA, MLB) — shares the full architecture
- **FPL** — budget-constrained knapsack with transfer costs, captaincy, chips.
  Shares the projection layer, almost none of the decision layer.
- **Bracket pools** — one-shot prediction where the optimum depends on the
  pool's other entries. Game theory, not valuation. Shares nearly nothing.

**Constraint on the design:** the shared layer is scoped to data ingestion and
projections. Each sport brings its own decision engine. Do not generalize the
"player value model" across all four — bracket pools will break it.

## 11. Design risks and known limitations

**Open risks first, then mitigated.** Items marked **[mitigated]** drove the
v1 cuts above and are listed for the record.

### Open

1. **Decision-error evals cannot detect a wrong value model.** §9.2 tests
   internal consistency. A policy that faithfully implements a bad valuation
   passes every check. The golden set (§9.3) and the §7 invariant are the only
   v1 defenses, and both rest on human judgement over a small number of cases.
   **This is the main limitation of the v1 eval story.**
2. **Survival dispersion is a placeholder, not a measurement.** §8 fixes a
   family and a σ formula chosen for plausible shape. Coarse bands and an
   explicit label reduce the harm; they do not make it right. Independence is
   known-wrong and biases toward over-confident waiting on same-position
   players.
3. **Player ID mapping is a swamp with a threshold, not a solution.** §6 fails
   closed below 98% on the top 300 and emits a report, which catches gross
   failure. It does not catch a small number of *wrong* matches, which are
   worse than misses because they are invisible.
4. **An observed "inefficiency" may just be the market.** If a league prices a
   position a certain way every year, that price *is* the equilibrium.
   Distinguishing a mispricing from a stable local equilibrium is unaddressed,
   and is a precondition for ever building §4.
5. **The outcome-replay target may be wrong.** §9.4 scores on optimal weekly
   lineup summed over the season, which ignores playoff-week timing and games
   missed. A player who produced but was unavailable in the weeks that decided
   the season is not a good pick.
6. **The greedy replacement algorithm may not converge in the format it
   targets.** §7 runs two passes and asserts an invariant. Superflex is the
   most likely place for that invariant to break, and the spec's answer is
   "investigate before drafting" — which is honest, but it is not a fix.
7. **The v1 scope may still not fit before a near-term draft date.** The
   fallback is a static ranked sheet from the same valuation engine. No
   scope-cut date is defined.

### Accepted deliberately

8. **Replaying a slot does not produce an independent sample.** Other
   drafters' choices are held fixed while the policy's vary, and a real
   different pick would change the board downstream. For one person's tool the
   narrow question in §9.4 is enough.

### Mitigated

9. **Single-season market models are near-worthless.** Fitting positional
   pricing from one or two prior drafts captures a few managers'
   idiosyncrasies, not a market. **[deferred, §4]**
10. **Backtests leak.** **[§9.4 is conditional and reports NOT PERFORMED
    rather than a caveated number]**
11. **Scraping is a dependency on someone else's HTML and terms.** **[no
    scraping in v1; files are user-supplied, §6]**
12. **The pick objective was undefined**, leaving §9.2 without a referent.
    **[written as a function in §5]**

## 12. Open questions

- Are platform mock draft IDs readable via the public API? If so, mocks are
  the integration test for the full read → recommend loop. **Unverified, and
  the cheapest remaining de-risking step.**
- Can a projection file dated before a past draft be recovered from web
  archive snapshots? Determines whether §9.4 runs at all. Timebox the hunt.
- Which ADP sources publish a per-player dispersion, so §8's placeholder can
  be replaced with a measurement?
- What validates that a *matched* player is correctly matched (§11.3)?
- What is the scope-cut date, and what exactly is the static fallback sheet?

## 13. Ethics

Some leagues prohibit automated assistance. Users should disclose to their
league before drafting.

Projections and lineup math are equivalent to widely-used public tools and are
not meaningfully novel. v1 uses public ADP and a projection file — nothing
about any specific league-mate.

**A market model fitted on a league's own draft history (§4) is different in
kind.** It is analysis of specific people's behavior derived from their
records, and some will object on grounds that do not apply to player
projections. It is also likely the largest edge. **Should §4 ever be built,
users should disclose it specifically** — the general disclosure above does
not cover it.

The tool must not require or encourage committing a league's data — including
other managers' identities and transaction histories — to a shared repository.
