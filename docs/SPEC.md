# vorpal — Specification (draft for review)

**Status:** proposal, pre-implementation

This document is written for adversarial review. Section 11 lists the claims
believed to be weakest. Reviewers should attack the premise, not only the
wiring.

---

## 1. Problem

Fantasy sports decision support: draft, weekly lineups, waivers, and trades.
The system recommends; the human executes.

First target platform is Sleeper (NFL). The tool is configured by league ID
and derives everything else from the platform API. No league's settings,
scoring, or roster shape are hardcoded.

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

**Decision:** build the analysis layer assuming manual execution. Model writes
as a pluggable `Executor` interface with `ManualExecutor` as the only
implementation. This keeps the valuable work unblocked by the fragile work.

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

The system must handle a draft slot that is unknown or subject to change
before the draft begins.

## 4. League-specific market modeling

Positional pricing varies substantially between leagues, and a league's own
draft history is better evidence for it than public ADP.

The tool ingests prior drafts from the configured league and fits a market
model over them: when each position tends to come off the board, where runs
occur, and where dead zones open. Where a league has few prior drafts, the
model falls back to public ADP for the format and reports low confidence.

**This is a feature, not a finding.** No specific league's tendencies belong
in this document or in code. See §11 for why single-season market models
should be treated with suspicion.

## 5. Architecture (proposal)

```
league state (platform read API)  ─┐
projections + distributions       ─┼──> valuation engine
player DB / news / injuries       ─┘    (VORP, league-specific replacement)
                                              │
        ┌─────────────┬─────────────┬─────────┴────┐
     draft         lineup        waivers        trades
     policy        policy        policy         policy
                          │
                    Executor (manual)
```

Each phase is a thin **policy** over one shared valuation engine:

- **draft** — best available given roster construction and picks-until-next
- **lineup** — max projected points over legal slot assignments
- **waivers** — draft policy with a FAAB budget instead of picks
- **trades** — difference of two roster valuations

Every policy emits a `Proposal`. How a proposal gets submitted is the
executor's problem, not the policy's.

## 6. Data sources

| Need | Source | Notes |
|---|---|---|
| League state | Platform read API | Free, no auth, authoritative |
| Projections | nflverse (play-by-play, usage) + consensus | Blend; see §7 |
| Usage detail | nflverse snap counts, target share, routes | Drives waiver quality |
| ADP / market | Public ADP for the format + league's own history | See §4, §8 |
| Injury / news | nflverse injury reports; public endpoints | Timeliness matters near kickoff |

Consensus rankings are scraped, which is both a fragility and a ToS question.
Superflex and other non-standard format products are thinner than standard
ones.

## 7. Valuation

Compute value over replacement from projections, using the configured
league's actual replacement levels rather than generic ones.

Replacement level is a function of the league's slot composition and roster
depth, and must be **derived from simulated lineup usage**, not assumed. In
formats with flexible slots (FLEX, SUPER_FLEX, OP), a position's replacement
rank depends on how often those slots are filled by that position — which is
itself an output of the valuation, so the computation is iterative.

Small errors here dominate. A few ranks of movement in a position's
replacement level can invert the recommended draft ordering between positions.

Projection *distributions* matter, not only means. Late in a draft the correct
objective shifts from median toward ceiling.

**Rankings are not projections.** Ordinal consensus data cannot produce true
VORP or uncertainty estimates. It enters as a market prior only.

## 8. Opponent model

Predicts when each player will be taken. The draft policy's "can I wait a
round on this player" logic is entirely downstream of it.

Built from the configured league's own history where enough exists, falling
back to public ADP for the format. Outputs a survival probability per player
per future pick, not a point estimate, with an explicit confidence that
reflects sample size.

The gap between the valuation model and the market model is the edge.

## 9. Evaluation

A draft happens once a season and the outcome is dominated by luck. "Did we
win" is not a signal. Score decisions, not results.

### 9.1 Error decomposition (core)

For every pick, compare three choices:

1. what the agent picked
2. what it should have picked **given its own projections** → gap = **decision error** (logic bug)
3. what it should have picked **given actual end-of-season value** → gap = **projection error** (data problem)

Conflating these is why most fantasy tools never improve. Keeping them
separate is the main reason to believe this project improves year over year.

### 9.2 Backtest

Replay historical drafts from every slot, not only the user's. Score each
resulting roster on **sum of optimal weekly lineup** over the relevant weeks —
this strips out start/sit noise and measures the draft alone.

Strict point-in-time discipline required: no post-hoc rankings, no information
dated after the draft.

### 9.3 Opponent model calibration

Separate and cheap. How well does the model predict *when* players actually
went? Report calibration curves, not accuracy.

### 9.4 Monte Carlo

Simulate many drafts with opponent noise, then simulate seasons from
projection distributions. Report the distribution of team outcomes. Also
identifies which decisions are close calls and which are real.

### 9.5 Golden set

A small set of hand-labeled pick scenarios with confident correct answers.
Runs in seconds. Catches regressions during rapid iteration.

## 10. Scope and phasing

| Phase | Deliverable | Gating |
|---|---|---|
| 0 | Read layer, projections, valuation engine | Blocks everything |
| 1 | Draft assistant + browser board | League draft date |
| 2 | Weekly lineup optimizer | Week 1 |
| 3 | Waivers + FAAB bid sizing | Week 2 |
| 4 | Trade evaluation (inbound), then proposal (outbound) | Week 3+ |

Phase 1 UI: local page kept open beside the platform app, auto-refreshing off
the draft API. Shows board state, recommendations with value vs market, roster
needs, positional-run alerts, and survival probabilities to the next pick.

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

## 11. Weakest claims (attack these first)

1. **Single-season market models are near-worthless.** §4 fits positional
   pricing from a league's own drafts. With one or two prior seasons that is
   a handful of managers' idiosyncrasies, not a market. The confidence
   reporting is asserted but not designed.
2. **An observed "inefficiency" may just be the market.** If a league prices a
   position a certain way every year, that price *is* the equilibrium. There
   is no arbitrage, only a different market. Distinguishing a mispricing from
   a stable local equilibrium is not addressed.
3. **Replacement level is described as iterative but not specified.** §7 says
   the computation is circular (slot usage depends on valuation depends on
   slot usage) and that small errors dominate. Neither the fixed-point method
   nor its convergence is defined.
4. **The eval target may be wrong.** §9.2 scores on end-of-season optimal
   lineup. That ignores playoff-week timing and games missed to injury. A
   player who produced but was unavailable in the weeks that decided the
   season is not a good pick.
5. **Backtests leak.** Any projection or ranking source revised since the
   historical draft contaminates the test. Point-in-time data may not be
   recoverable for all sources, which would quietly invalidate §9.2.
6. **Replaying "every slot" does not produce independent samples.** Other
   drafters' choices are held fixed while the agent's vary. The data cannot
   support that counterfactual.
7. **The opponent model is reflexive.** If the agent drafts differently, the
   board changes downstream for everyone, and the model was fit on a world in
   which the agent did not exist.
8. **Scraping consensus rankings** is a dependency on someone else's HTML and
   terms. No fallback is specified.
9. **Phase 0 plus phase 1 with real evals may not fit before a near-term
   draft date.** The fallback is a static cheat sheet. No scope-cut date is
   defined.

## 12. Open questions

- Are platform mock draft IDs readable via the public API? If so, mocks are
  the integration test for the full read → recommend loop. **Unverified.**
- Which projection sources are point-in-time recoverable for backtesting?
- How should the system detect and report that a league has too little
  history for its market model to mean anything?
- What is the minimum viable fallback if phase 1 is not ready by a user's
  draft date?

## 13. Ethics

Some leagues prohibit automated assistance. Users should disclose to their
league before drafting.

Projections and lineup math are equivalent to widely-used public tools and are
not meaningfully novel. **Opponent modeling is different in kind** — it is
analysis of specific people's behavior derived from their transaction history,
and some will object to it on grounds that do not apply to player projections.
It is also likely the largest edge. Users should disclose it specifically.

The tool must not require or encourage committing a league's data — including
other managers' identities and transaction histories — to a shared repository.
