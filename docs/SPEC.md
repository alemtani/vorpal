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
**draft ID and operator identity**. Scoring is read from a league — the
draft's own league when it has one, or a named other league when it does not
(standalone mocks). Roster slots come from that same league when the draft
belongs to one, and from the draft object otherwise. Draft type and pick
order come from the draft. Nothing about any league is hardcoded.

Scope is a personal tool. Dynasty, keeper, and IDP formats are out. Nothing
here assumes commercial use, and the ethics constraints in §13 assume a human
who is a member of the league being analyzed.

---

## 2. The binding constraint

Sleeper's public API is **read-only**. Its documentation states: "No API Token
is necessary, as you cannot modify contents via this API." Every documented
GET needed exists (league, rosters, matchups, transactions, drafts, picks,
players, trending, user). There are no write endpoints.

Three possible write paths:

| Path | Mechanism | Risk |
|---|---|---|
| Manual | Human acts in the platform UI | None |
| Browser automation | Drive the platform web app | Fragile UI, session handling, ToS gray area |
| Internal API | Reverse-engineered write endpoints | Breaks silently, clearest ToS violation, ban risk |

**Decision (writes):** the human executes. Every policy emits a proposal; the
user acts in the platform UI. This keeps the valuable work unblocked by the
fragile work, and it is the only write path with no terms-of-service
exposure. The default *read* path is a separate, accepted exception below.

No plugin interface is introduced for this (§5).

Rate limit on the documented host (`api.sleeper.app`): stay under 1000
calls/minute. That limit is not documented for `api.sleeper.com` and is not
assumed to apply there.

The `/players` endpoint is ~5MB unfiltered. Position-filtered fetches are
allowed and preferred. Cache the result at most once per day. Do **not**
filter the player pool by `active=true` — inactive, IR, unsigned, and rookie
players are draftable. `search_rank` on the player object is a single
cross-positional order with no superflex variant; it is **not ADP**.

### Undocumented projections endpoint — accepted read exception

v1's default forecast does **not** come from a documented endpoint. It comes
from:

```
GET https://api.sleeper.com/projections/nfl/{season}?season_type=regular&position[]={POS}
```

This host is not `api.sleeper.app`. The path is not in Sleeper's public
documentation. The payload redistributes Rotowire counting-stat projections
and several ADP series, keyed by Sleeper `player_id`.

| Path | Mechanism | Risk |
|---|---|---|
| Undocumented read | `api.sleeper.com/projections` | Breaks silently, ToS gray, possible ban. Same risk class as the Internal API row above, moved from write to read. |

**Decision:** accept this as the default path. Mitigation is a user-supplied
override file (§6) that restores both the forecast and the market prior if
the endpoint changes or vanishes. The risk is not mitigated by pretending
the endpoint is public.

Fetch this endpoint **once per process** and cache it with `/players`. Never
poll it. Never assume the documented `.app` rate limit covers `.com`.

---

## 3. League configuration

Configuration is assembled from two platform objects, then reduced to one
resolved slot list that every later section consumes.

**From the draft** (`GET /draft/{id}`): draft type, teams, rounds, pick
timer, reversal round, slot counts (`slots_qb`, `slots_super_flex`, …),
`draft_order`, `slot_to_roster_id`, `status`, `season`, `league_id`.

**From a league** (`GET /league/{id}`): `scoring_settings`,
`roster_positions`, `settings.type`, `settings.max_keepers`,
`settings.taxi_slots`, and the rest of the settings table (waivers, FAAB,
playoffs). On a standalone mock the draft's `league_id` is null; scoring and
format settings come from a named other league supplied by the operator.
That borrowed league does **not** supply slots. Waiver / FAAB / playoff
settings from a borrowed league are unused in v1.

`GET /draft/{id}` never returns `scoring_settings`.
`metadata.scoring_type` is a label (`"ppr"`, `"2qb"`), never a scoring table,
and never an input to ADP selection or valuation.

### Slot authority

Resolve slots **once**:

1. If the draft's own `league_id` is non-null and that league's
   `roster_positions` is present, that array is the slot list.
2. Otherwise (standalone mock: `league_id` is null) use
   `draft.settings.slots_*`. A scoring-source league supplied for a mock
   never overrides this.
3. Bench: if `slots_bn` is absent **and** step 1 did not fire, infer bench
   as `rounds − Σ(starter slots)`, excluding IR and taxi from the
   remainder. If the chosen source already names bench slots, do not infer.

The resolved list is the only slot input to ADP-variant selection (§6),
unmatched-key classification (§6), replacement (§7), and survival (§8).

### Slot eligibility

A player's legal slots are a function of position, not of league settings:

| Slot | Eligible positions |
|---|---|
| QB | QB |
| RB | RB |
| WR | WR |
| TE | TE |
| K | K |
| DEF / DST | DEF |
| FLEX | RB, WR, TE |
| SUPER_FLEX, OP | QB, RB, WR, TE |
| BN | any |

IDP slot codes (DL, LB, DB, IDP, …) are out of v1; their presence is a
refusal, not an eligibility row.

### Unsupported formats — detect and refuse

v1 supports **snake redraft, offense-only**. The following are detected and
**refused with an explicit message**, not silently mishandled:

| Condition | Signal | Why refuse |
|---|---|---|
| Keeper / dynasty | `settings.type ∈ {1, 2}`, or `taxi_slots > 0` | Kept players must be removed from the pool; not implemented |
| Unknown league type | `settings.type` absent, or not in `{0, 1, 2}` | The enum is measured, not documented (only `0` has been observed). Unknown means unknown. |
| IDP | Defensive player slots in the resolved slot list | Offensive projection rows have no values for these slots |
| Auction | Draft type is auction | Budget allocation, not pick order; survival by pick number is meaningless |
| Linear | Draft type is linear | Survival math is snake-specific; not implemented |
| Third-round reversal | `reversal_round` present and not `0` | Pick-number spacing is not standard snake; not implemented |

`settings.type` mapping, recorded as measured: `0` = redraft (observed).
`1` = keeper and `2` = dynasty are inferred from Sleeper's product, not from
public documentation. `settings.type` absent, or present and not in
`{0, 1, 2}`, is an unknown league type and is refused.

`max_keepers > 0` on a `type == 0` league is **not** a refusal. The
predicate "keeper picks present" is undecidable before the draft starts —
the picks list is empty. v1 banners *"keepers possible; pool unchanged
until a keeper pick appears"* and proceeds. If a pick arrives whose
`is_keeper` field is present and is not `null`, `false`, `0`, or `""`,
banner and remove that player from the pool. Do not refuse mid-draft.

### Standalone mocks

Standalone mock drafts are readable on the documented draft endpoints.
Their `league_id` is null. Scoring must be borrowed from a named league;
without one, refuse. Slots come from the draft; scoring comes from the
borrowed league. The board banners both sources.

This is a chimera by construction. The resolved slot list is the mock's
(step 2 above). Scoring is the borrowed league's. ADP-variant selection
consumes the resolved slots; valuation consumes the borrowed scoring. The
two are allowed to disagree; the banner is how that disagreement stays
visible.

### Operator identity

The documented API is unauthenticated. Nothing in the draft payload
identifies the operator. Operator identity is a **required input**
(username or user_id).

Resolution:

1. `GET /user/{username}` or `GET /user/{user_id}` → `user_id`. Match on
   username, not display name.
2. Look `user_id` up in `draft_order`.
3. `draft_order` unset (null or empty) → proceed; hide survival (§3
   unknown-slot rule). This is the only case hidden-survival covers.
4. `draft_order` **partial** (at least one entry, fewer than `teams`) and
   the operator is absent → require an explicit slot; if none is given,
   refuse.
5. `draft_order` **complete** (an entry for every slot in `1..teams`) and
   the operator is absent → refuse.

`picked_by` on a pick may be `""` (CPU slots). It is display-only. Operator
matching uses `draft_order`, never `picked_by`.

### Unknown draft slot

Draft order may be unset or may change before the draft. When the user's
slot is unknown **because the league has not set an order**:

- The board ranks by value only.
- Survival probabilities are **hidden**, not estimated. Survival is a
  function of slot, team count, and snake direction; without a slot there
  is no answer, and a guessed one is worse than none.
- The board recomputes and reveals survival as soon as the slot is set.

This is not the same unknown as "the operator did not say who they are."
That is user error and is refused, above.

### Draft liveness

Read liveness from `draft.status`, never from `start_time` (null on
standalone mocks). Observed values: `pre_draft`, `drafting`, `complete`.
Any other value, including a paused-like state, is treated as not-drafting.

### Refusal taxonomy

Four cases, none of them warnings, none of them silent zeros:

- **Format refusal.** The league or draft shape is out of v1. Unfixable by
  a better file. No escape hatch.
- **Data refusal.** Supplied or fetched data is not good enough to render
  a board (override file missing `player_id`, required counting-stat keys
  absent, endpoint returned more than one `company`). Fixable.
- **Platform error.** A documented or undocumented GET failed or returned
  something unusable.
- **User error.** Required operator identity is missing, or the operator
  cannot be placed on the board and no explicit slot was given.

---

## 4. League-specific market modeling — deferred past v1

Positional pricing varies between leagues, and a league's own draft history
is evidence about it. The tool could fit a market model over prior drafts:
when each position comes off the board, where runs occur, where dead zones
open.

**Not in v1.** A league typically has one or two prior drafts available.
That is a handful of managers' idiosyncrasies, not a market, and fitting it
invites confident nonsense. v1 uses the platform ADP field that matches the
resolved format (§6).

If this is built later, no specific league's tendencies belong in this
document or in code.

---

## 5. Architecture (proposal)

```
draft + operator identity  ─┐
league scoring (own or borrowed)
platform projections + ADP ─┼──> valuation engine
optional override file     ─┘    (VORP, league-specific replacement)
                                          │
        ┌─────────────┬─────────────┬─────┴──────┐
     draft         lineup        waivers      trades
     policy        policy        policy       policy
```

Each phase is a thin **policy** over one shared valuation engine:

- **draft** — best available given roster construction and picks-until-next
- **lineup** — max projected points over legal slot assignments
- **waivers** — draft policy with a FAAB budget instead of picks
- **trades** — difference of two roster valuations

**The diagram above is the full product, not v1.** v1 builds the read
layer, the valuation engine on point estimates, and the draft policy only.
News, injuries, distributions, and the other three policies are later
phases.

Required inputs, stated as inputs, not as flag names:

- draft id
- operator identity (username or user_id)
- scoring-source league id, if and only if the draft's `league_id` is null
- optional override file restoring projections and ADP together

### The v1 pick objective

The policy is a function, and it must be written as one or the eval in §9.2
has no referent:

> At each pick, recommend the available player that maximizes **expected
> starting-lineup VORP of the resulting roster**, where a player's
> contribution counts only if the roster has a legal slot for them, and
> where players available at the user's next turn with high probability are
> discounted by their survival probability (§8).

This is **one-step lookahead**, not static VORP and not myopic take-best.
The distinction is the product: static VORP takes the third receiver while
a starting slot sits empty; myopic take-best takes a player who would have
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

The human acts in the platform UI. There is no executor abstraction in v1 —
a plugin interface with exactly one implementation and no second
implementation planned is speculative generality.

---

## 6. Data sources

| Need | Source | v1? |
|---|---|---|
| League / draft state | Documented platform read API | Yes |
| Operator identity | Documented `GET /user/{username\|user_id}` | Yes |
| Projections | Undocumented `api.sleeper.com/projections` (§2) | Yes — default |
| ADP / market | Same payload, `adp_*` fields | Yes — default |
| Override | One user-supplied CSV keyed by `player_id` | Yes — insurance |
| Usage detail | nflverse snap counts, target share, routes | No — waiver-phase input |
| Injury / news | nflverse injury reports; public endpoints | No |

### Buy the forecast, build the scoring

The valuation engine needs expected points per player in *this league's*
scoring. It does not follow that the tool must forecast the NFL.

**v1 buys counting stats and builds everything downstream.** The default
purchase is the undocumented projections endpoint: passing yards, rushing
yards, receptions, touchdowns, already keyed by Sleeper `player_id`. The
tool applies the league's actual scoring settings, derives replacement
levels from the resolved slots, and ranks by value over replacement.

What is trusted: someone else's yards and touchdowns (Rotowire's, as
redistributed). What is *not* trusted: their fantasy-point totals, which
encode a scoring format that is not this league's. For non-standard
formats — superflex, no-kicker, TE premium — that distinction is most of
the value.

**Never ingest a fantasy-points column**, as a class. `pts_ppr`,
`pts_std`, and `pts_half_ppr` are examples, not an exhaustive list.

Deriving projections from play-by-play is a months-long forecasting
project and is not a prerequisite for drafting. It is out of scope
indefinitely.

### Projections payload contract

The default fetch is one GET per position (`QB`, `RB`, `WR`, `TE`, `K`,
`DEF`) for `season` taken from the draft object and `season_type=regular`.

Verified shape, used as the contract:

- One `company` value across the fetch, currently `rotowire`. If more than
  one distinct `company` appears, refuse (data refusal).
- Values are **season totals**. `week` is null; `gp` is a full season.
- `player_id` is the Sleeper id. No name matching on this path.
- Counting-stat keys include `pass_yd`, `pass_td`, `pass_int`, `pass_2pt`,
  `rush_yd`, `rush_td`, `rush_2pt`, `rec`, `rec_yd`, `rec_td`, `rec_2pt`,
  `fum_lost`, plus the kicker and DST keys listed in the taxonomy below.
- Every row carries `adp_std`, `adp_ppr`, `adp_half_ppr`, `adp_2qb`. There
  is no `adp_2qb_ppr` and no per-player dispersion field.
- A large majority of rows carry ADP and no counting stats (fringe
  players with a market price and no forecast). Exclude those rows from
  valuation. Report the excluded count. Do not invent stats for them.

If a startable dedicated position (QB, RB, WR, TE, and K or DEF when
those slots exist) has zero valuation-eligible rows, refuse. A missing
individual scoring key is the unmatched-key path below, not a board-level
refuse.

### ADP variant

Select one `adp_*` field from the same payload, using the **resolved slot
list** and the scoring table:

1. If the resolved slots include SUPER_FLEX, OP, or two or more dedicated
   QB slots → `adp_2qb`.
2. Else by the scoring table's `rec` weight: `≥ 0.75` → `adp_ppr`;
   `0.25–0.75` → `adp_half_ppr`; `< 0.25` → `adp_std`. Banner whenever
   `rec` is not exactly `1.0`, `0.5`, or `0.0`.

There is no `adp_2qb_ppr`. A 2QB PPR league (and a chimera mock whose
borrowed scoring is PPR while its slots are 2QB, or the reverse) uses
`adp_2qb` and banners the split. ADP models the other drafters; scoring
models our valuation. They are allowed to differ.

`search_rank`, the `trending` endpoint, and any third-party ranking or
ID-crosswalk file are not ADP and are not consulted.

### Override file

If the projections endpoint is down or the operator prefers a different
forecast, one CSV restores both the forecast and the market prior.

Required columns: `player_id`, plus the counting-stat columns the
league's startable scoring keys resolve to, plus `adp`. Optional:
`adp_stdev`, and name / team / position for humans.

**Refuse if `player_id` is missing.** Do not fuzzy-match on name. The
override exists so draft night does not depend on name matching; falling
back to name matching on the night the endpoint dies would put the
worst-case path on the critical path.

Endpoint down and no override file → data refusal. Not a half-board.

### Scoring-key taxonomy

Every nonzero scoring key is classified. The table is a **platform
taxonomy of known Sleeper keys**, not the keys of any one league.

| Class | Keys / prefixes | Startable when the resolved list has |
|---|---|---|
| QB | `pass_*`, `bonus_pass_*`, `bonus_rush_td_qb` | QB, SUPER_FLEX, or OP |
| RB | `bonus_rec_rb` | RB, FLEX, SUPER_FLEX, or OP |
| WR | `bonus_rec_wr` | WR, FLEX, SUPER_FLEX, or OP |
| TE | `bonus_rec_te` | TE, FLEX, SUPER_FLEX, or OP |
| K | `fgm`, `fgm_*`, `fgmiss`, `fgmiss_*`, `xpm`, `xpmiss` | K |
| DST | `pts_allow`, `pts_allow_*`, `yds_allow`, `yds_allow_*`, `def_*`, `st_*`, `sack`, `int`, `ff`, `safe`, `blk_kick`, `fum_rec`, `pr_td`, `kr_td` | DEF / DST |
| IDP | `idp_*` | any IDP slot (v1 refuses the league first) |
| offense-flex | `rec`, `rec_*`, `bonus_rec_*` (remaining), `rush_*`, `bonus_rush_*` (remaining), `fum`, `fum_lost`, `two_pt` | any of QB, RB, WR, TE, FLEX, SUPER_FLEX, OP |

Longer / more specific prefixes win. `pass_int` is QB, not DST. `idp_int`
is IDP, not DST. A key matching no row is **unknown**.

### Unmatched scoring keys

For every scoring setting with a nonzero value, resolve a stat column.

- A classified key whose class has a startable slot, and no column, is
  **itemized** before the board renders (key and value).
- A classified key whose class has no startable slot is collapsed to one
  summary line naming the class and the count. Slot composition is the
  authority, not the scoring table: a league may store K/DST values with
  no K/DST slot.
- An unknown key is **always itemized**, even if it might be unreachable.
  Fail loud.

The operator chooses to proceed (the key contributes zero) or to supply
an override. It is never a silent zero.

### Two-point conversions

Resolve per column, not all-or-nothing:

1. `pass_2pt` / `rec_2pt` / `rush_2pt` each use their dedicated column
   when that column is present (the default payload supplies all three).
2. Else that one key uses the optional `two_pt` column, if present.
3. Else that key is an unmatched startable key and is itemized.

### K and DST rows

The default payload includes K and DST rows. The flat positional baseline
("slot exists, file has no rows, assign a baseline and state it on the
board") applies only to the override path.

---

## 7. Valuation

Compute value over replacement from projections, using the configured
league's actual replacement levels rather than generic ones.

Replacement level is a function of the **resolved slot list** and roster
depth. It must be derived from those slots, not assumed from a
standard-format table.

**v1 ranks on expected points.** Point estimates only. Distribution-aware
and ceiling-weighted logic is a later phase (§9.5).

### Algorithm

Let `T` = number of teams. Slots come from the resolved slot list (§3).

**Pass 0 — rank key: projected points.**

1. For each position, sort all players by projected points.
2. Fill dedicated slots: for each dedicated slot type in the resolved
   list (QB, RB, WR, TE, and K or DEF when present), absorb the top
   `T × (slots of that type)` players at that position.
3. Fill flexible slots: pool all remaining players eligible for each
   flexible slot type, sort by projected points, and absorb the top
   `T × (slots of that type)`. Process flexible slots **most-restrictive
   first** — FLEX (RB/WR/TE) before SUPER_FLEX or OP (which additionally
   admit QB) — so the broader slot draws from what the narrower one left.
4. **Bench slots are not absorbed.** Replacement level is defined by who
   starts, not who is rostered. Bench depth affects the draft pool, not
   the baseline.
5. Replacement for a position = projected points of the **first player at
   that position not absorbed** in steps 2–3.

**Pass 1 — rank key: VORP from pass 0.**

6. Repeat steps 2–3, sorting by pass-0 VORP instead of raw points. This
   is the only thing that changes, and it is the whole reason the
   computation is circular: flexible-slot allocation should reflect value
   over replacement, which pass 0 did not have.
7. Recompute replacement per step 5. **Stop.**

### Stop rule as an eval, not a comment

Pass 1 can move ranks, and in superflex it is most likely to — that is
the format this tool is for. So the convergence claim is testable, not
assumed:

> **Invariant:** a hypothetical pass 2 must not move any position's
> replacement rank by more than **2**.

This runs as a **failing eval** in the §9.3 suite, not as a code comment.
A breach means the greedy approximation is inadequate for that league
shape and the board should not be trusted. It does not mean "build a
fixed-point solver" — it means investigate before drafting.

Small errors here dominate: a few ranks of movement in a position's
replacement level can invert the recommended ordering between positions.

Projection *distributions* matter, not only means. Late in a draft the
correct objective shifts from median toward ceiling.

**Rankings are not projections.** Ordinal consensus data cannot produce
true VORP or uncertainty estimates. The default payload supplies counting
stats, not ordinal consensus; ADP from the same payload is a market prior
only.

---

## 8. Survival model

Predicts whether a player is still available at a future pick. The draft
policy's "can I wait a round on this player" logic is entirely downstream
of it, and on draft night it is the highest-value output after value
itself.

**v1: platform ADP plus an explicit placeholder dispersion.** The
projections payload has no per-player spread. A probability shipped with
an unspecified variance is worse than showing ADP and no probability at
all, so the placeholder is written down and labelled:

- **Family:** normal over pick number, truncated below at pick 1.
- **Location:** the selected `adp_*` field (§6).
- **Dispersion:** `adp_stdev` from the override file where the operator
  supplies it. Where it is absent — the default path — `σ = max(4, 0.30 ×
  ADP)`. Dispersion grows with ADP because late-round consensus is
  weaker. **This is a placeholder**, chosen for plausible shape, not
  fitted. It is flagged as such on the board.
- **Already drafted:** survival probability 0. Not a distribution.
- **Independence:** players are treated as independent. This is **known
  to be wrong** and the direction of the error is known — real drafts
  have positional runs, so joint survival of two players at the same
  position is overstated. "Can I wait on both of these receivers" is
  therefore the question v1 answers worst.

Because the dispersion is a placeholder, the board shows survival in
**coarse bands** (likely / toss-up / unlikely) rather than a decimal
probability. The precision of a number implies a calibration that does
not exist yet.

Calibrating dispersion against real draft data is §9.6.

Fitting the configured league's own draft history is deferred (§4). Note
that platform ADP is itself an opponent model with a flat prior — the v1
cut removes the *fitting*, not the survival curve.

The gap between the valuation model and the market model is the edge.

---

## 9. Evaluation

A draft happens once a season and the outcome is dominated by luck. "Did
we win" is not a signal. Score decisions, not results.

An `invariant` or `golden` failure is a **model** failure, not a unit-test
failure. The distinction belongs in how the failure is reported, not in
a coverage number.

### 9.1 Error decomposition (core)

For every pick, compare three choices:

1. what the policy picked
2. what it should have picked **given its own projections** → gap =
   **decision error** (logic bug)
3. what it should have picked **given actual end-of-season value** → gap =
   **projection error** (data problem)

Conflating these is why most fantasy tools never improve.

The decomposition also determines *which evals are runnable at all*.
Decision error and projection error have completely different data
requirements, and only one of them is blocked by history.

### 9.2 Decision error — runnable, no historical data (v1)

Decision error is an **internal consistency test**. It asks whether the
policy picked what its own value model says was best, given roster state
and picks until the next turn.

The same projections sit on both sides of the comparison and no outcomes
are involved, so **there is nothing to leak**. It needs no point-in-time
file and no completed season. It can run today, across thousands of
simulated board states.

It catches **computation** bugs: a wrong implementation of the §7 fill,
roster construction that mishandles flexible slots, survival terms
applied to the wrong pick, arithmetic in the objective.

It **cannot** catch a wrong value model. If §7 defines replacement badly
and the code implements that definition faithfully, every check passes.
Model correctness is the golden set's job (§9.3) and the invariant in §7.

### Board-state generation

The "simulated board states" must come from somewhere, and the choice
matters:

**v1 uses a separate sampler, not the survival model.** States are
generated by removing players from the pool according to ADP order with
injected noise, across a grid of round numbers and roster compositions.

Using the survival model as the generator would rest the one committed
eval on the one unfitted placeholder input (§8) — the eval would agree
with the policy by construction. A separate sampler tests states the
policy might not predict, which is the point.

The sampler must include adversarial states, not just plausible ones:
runs that empty a position, a roster with every flexible slot filled, the
user's last pick.

This is the eval v1 commits to.

### 9.3 Golden set (v1)

A small set of hand-labeled scenarios with confident correct answers — a
kicker in round 3, a third tight end while a starting slot sits empty.
Runs in seconds, catches regressions during rapid iteration.

**This is an external oracle, and it is the only v1 eval that can catch a
bad value model.** §9.2 asks whether the code matches the model; the
golden set asks whether the model matches reality, using human judgement
as the label. It is not a special case of §9.2 — it is the other half.

It may assume only what a competent human would assert without a
projection source: a kicker in round 3 is wrong, a third tight end while
a starting slot sits empty is wrong, a quarterback taken in a superflex
league at a pick where two remain and eight teams need one is right.

Because §7's convergence invariant is also a labelled assertion about
model correctness, it runs here.

### 9.4 Outcome replay — conditional (and it is not projection error)

Replay a historical draft: sit in the user's actual slot, hold every
other pick fixed, let the policy choose. Score both rosters on **sum of
optimal weekly lineup** in that season's scoring, which strips out
start/sit noise and measures the draft alone.

The question this answers is narrow and worth stating plainly: *given the
board that actually happened, would the policy have drafted better than
the user did?* It does **not** answer whether the user would have won,
because the other drafters would not have behaved identically. For a
personal tool the narrow question is enough.

**This eval is blocked on a projection file dated before that draft.**
Running it on today's projections, or on end-of-season results, measures
hindsight-optimal value — which always looks brilliant and says nothing
about draft night.

A configured league may have a completed prior draft. That does not
unblock this eval. Sources of a dated file, in order of likely success:
a saved override CSV from before that draft, then web-archive snapshots
of public projection pages from the relevant week, then paid historical
archives, then nothing. Snapshots of the undocumented endpoint are
unlikely to exist.

**If no dated file is found, this eval is reported as NOT PERFORMED.**
Not as a caveated number. A leaky result must never gate a decision.

**This is not projection error.** §9.1 item 3 defines projection error as
the gap between *the best pick given the model's projections* and *the
best pick given actual end-of-season value*. That is a property of the
projection source, measurable without any policy at all. Outcome replay
is a different thing: policy-versus-user on a frozen board, which mixes
model quality, projection quality, and the user's own decisions into one
number.

Reporting replay as projection error would be exactly the conflation
§9.1 says kills these tools. Projection error proper is also conditional
on a dated file and is **out of v1**.

### 9.5 Monte Carlo — later

Simulate many drafts with market noise, then simulate seasons from
projection distributions. Reports the distribution of outcomes and
separates close calls from real decisions. Valuable, not required to
draft.

### 9.6 Survival model calibration — later

How well does the survival model predict when players actually went?
Report calibration curves, not accuracy.

---

## 10. Scope and phasing

### v1 — what ships before the draft

1. Read the documented draft and league endpoints. Resolve slots, scoring,
   and operator identity (§3). Refuse unsupported formats.
2. If an override file is supplied, use it in place of the projections
   endpoint; refuse if it lacks `player_id`. Otherwise fetch the
   projections payload (§6). Select the ADP variant. Report ADP-only
   rows excluded from valuation.
3. Apply the league's scoring. Report unmatched nonzero keys by the §6
   taxonomy.
4. Replacement levels by the §7 algorithm, with the convergence invariant
   running as an eval.
5. Survival bands from platform ADP and the §8 placeholder dispersion.
   Hidden entirely when the draft order is unset.
6. Draft policy implementing the §5 objective, emitting `Proposal`s.
7. Board: value, ADP, legal slots, survival band, roster needs, banners.
   Local display polling the draft API (see below).
8. Decision-error evals (§9.2) and the golden set (§9.3).
9. Outcome replay **only** if a pre-draft projection file is found (§9.4).

Build order, each step consuming the previous:

> read draft → resolve slots / scoring / operator → fetch projections and
> ADP → score → VORP → survival → proposal → board

Explicitly not in v1: projection error as defined in §9.1, market model
fitted on league history, distribution/ceiling logic, multi-step
lookahead, waiver engine, trade engine, executor abstraction, multi-sport
layer, name-based player matching, linear drafts, third-round reversal.

### Draft-night polling contract

The board is a local display polling the **documented** draft API. Draft
night is the one window where a silently stale board is unrecoverable, so
the failure behavior is specified, not left to the implementation:

- **Poll interval:** 3 seconds while `status` is `drafting`. Well inside
  the documented `.app` rate limit (§2) for a single league. While
  `pre_draft` or any other non-complete status, poll at 15 seconds. Stop
  at `complete`.
- **Backoff:** on error, retry at 5s, 15s, 45s, then hold at 45s. Reset
  on first success.
- **Staleness is always visible.** The board shows the age of its data at
  all times, not only on failure. Past 15 seconds the display degrades
  visibly.
- **Grey-out threshold:** `settings.pick_timer` seconds. If `pick_timer`
  is 0 or null, do not grey-out; keep the 15s visual degrade. If the last
  successful poll is older than this threshold, the recommendation is
  greyed and marked unreliable.
- **Never render a stale board as current.**
- **Never poll the projections host.** Projections are fetched once per
  process (§2).

These are two numbers. The poll interval is not the pick timer.

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
- **FPL** — budget-constrained knapsack with transfer costs, captaincy,
  chips. Shares the projection layer, almost none of the decision layer.
- **Bracket pools** — one-shot prediction where the optimum depends on
  the pool's other entries. Game theory, not valuation. Shares nearly
  nothing.

**Constraint on the design:** the shared layer is scoped to data
ingestion and projections. Each sport brings its own decision engine. Do
not generalize the "player value model" across all four — bracket pools
will break it.

---

## 11. Design risks and known limitations

**Open risks first, then mitigated.** Items marked **[mitigated]** drove
the v1 cuts above and are listed for the record.

### Open

1. **Decision-error evals cannot detect a wrong value model.** §9.2 tests
   internal consistency. A policy that faithfully implements a bad
   valuation passes every check. The golden set (§9.3) and the §7
   invariant are the only v1 defenses, and both rest on human judgement
   over a small number of cases. **This is the main limitation of the v1
   eval story.**
2. **Survival dispersion is a placeholder, not a measurement.** §8 fixes
   a family and a σ formula chosen for plausible shape. The default
   payload has no spread field. Coarse bands and an explicit label reduce
   the harm; they do not make it right. Independence is known-wrong and
   biases toward over-confident waiting on same-position players.
3. **The default forecast is an undocumented redistribution.**
   `api.sleeper.com/projections` is not in Sleeper's public docs, lives
   on a different host, and can change or vanish with no notice. The
   override file is the stated mitigation; it only helps if the operator
   already has one when the endpoint dies. Draft night is the worst time
   to discover this. **This is the main operational risk of v1.**
4. **An observed "inefficiency" may just be the market.** If a league
   prices a position a certain way every year, that price *is* the
   equilibrium. Distinguishing a mispricing from a stable local
   equilibrium is unaddressed, and is a precondition for ever building
   §4.
5. **The outcome-replay target may be wrong.** §9.4 scores on optimal
   weekly lineup summed over the season, which ignores playoff-week
   timing and games missed. A player who produced but was unavailable in
   the weeks that decided the season is not a good pick.
6. **The greedy replacement algorithm may not converge in the format it
   targets.** §7 runs two passes and asserts an invariant. Superflex is
   the most likely place for that invariant to break, and the spec's
   answer is "investigate before drafting" — which is honest, but it is
   not a fix.
7. **The v1 scope may still not fit before a near-term draft date.** The
   fallback is a static ranked sheet from the same valuation engine. No
   scope-cut date is defined.

### Accepted deliberately

8. **Replaying a slot does not produce an independent sample.** Other
   drafters' choices are held fixed while the policy's vary, and a real
   different pick would change the board downstream. For one person's
   tool the narrow question in §9.4 is enough.
9. **The default forecast is Rotowire's, taken from an unofficial host.**
   Personal, non-commercial, read-only. Still the Internal-API risk class
   applied to a read. Accepted in §2; disclosed in §13.

### Mitigated

10. **Single-season market models are near-worthless.** Fitting
    positional pricing from one or two prior drafts captures a few
    managers' idiosyncrasies, not a market. **[deferred, §4]**
11. **Backtests leak.** **[§9.4 is conditional and reports NOT PERFORMED
    rather than a caveated number]**
12. **The pick objective was undefined**, leaving §9.2 without a
    referent. **[written as a function in §5]**

Player-ID mapping is not on this list. The default path and the override
path are both keyed by Sleeper `player_id`. Name matching is not in v1.

---

## 12. Open questions

- Can a projection file dated before a past draft be recovered? Determines
  whether §9.4 runs at all. Timebox the hunt. Snapshots of the
  undocumented endpoint are unlikely; a saved override is the realistic
  source.
- What is the scope-cut date, and what exactly is the static fallback
  sheet?

Closed this revision:

- **Are standalone mock draft IDs readable via the public API?** Yes. The
  documented `GET /draft/{id}`, `/picks`, and `/traded_picks` return 200
  with `league_id` null. Scoring is not on the draft object, so a named
  other league is required. This is the cheapest remaining integration
  test for the read → recommend loop.
- **Which ADP sources publish a per-player pick-dispersion?** None found
  that are a pick-number spread. The default payload has no `stdev`.
  Expert-rank spreads from third-party consensus files are the wrong
  quantity. §8's placeholder and §11.2 stay open on purpose.

---

## 13. Ethics

Some leagues prohibit automated assistance. Users should disclose to
their league before drafting.

Projections and lineup math are equivalent to widely-used public tools
and are not meaningfully novel. v1's default forecast is Rotowire
counting stats, redistributed through an unofficial Sleeper host, plus
the platform's own ADP. That is **not** the same as "a file the user
already had." Disclose the source. The general disclosure above does not
cover it, and neither does "the platform showed me this in its own UI."

**A market model fitted on a league's own draft history (§4) is different
in kind.** It is analysis of specific people's behavior derived from
their records, and some will object on grounds that do not apply to
player projections. It is also likely the largest edge. **Should §4 ever
be built, users should disclose it specifically** — the general
disclosure above does not cover it.

The tool must not require or encourage committing a league's data —
including other managers' identities and transaction histories — to a
shared repository.
