# The golden set

**12 cases**, hand-built, hand-justified. Each one is a board, a set of
players a human says must not be the pick, a set the pick or an
alternative must name, and one sentence saying why.

Spec section 8 puts it plainly: *the model is the policy, and this small
human set is the main eval limit*. Twelve cases is small. What follows is
what they cover and, at more length, what they do not.

## Read this first

Every verdict here is a **floor**. A model that passes all twelve is not
thereby good — it has only avoided twelve mistakes that need no model to
spot. Nothing in this set rewards a good pick; there is no case whose
verdict is "this was the best available choice", because that judgement is
contested and a binary gate cannot hold it.

Nothing here came off a league. Every player id is invented and readable
(`k-early` is a kicker, `te-third` is the tight end you already have two
of). No manager, no league id, no host id.

## The cases

| Case | Situation | Verdict |
|---|---|---|
| `kicker_round_two` | early_round | forbid the kicker at pick 21 |
| `defense_round_three` | early_round | forbid the defense at pick 28, 10-team |
| `third_te_while_wr_empty` | roster_fit | forbid a third TE while both WR slots are empty |
| `backup_qb_in_one_qb_league` | roster_fit | forbid a second QB with one QB slot |
| `bye_stack` | bye_stack | forbid a fourth week-9 player; require the bye-5 equal |
| `superflex_qb_run` | superflex_scarcity | require one of the last two startable QBs |
| `empty_starter_late` | empty_starter_late | two empty slots, two picks left: require K or DEF |
| `second_kicker_last_rounds` | empty_starter_late | same board, K slot filled: forbid the second K |
| `te_cliff` | tier_cliff | require the TE above a 37-point cliff |
| `position_run` | position_run | five WRs in six picks: require one of the last two |
| `vols_compressed` | vols_compressed | every VOLS inside 1.5: require a wide-spread row |
| `seat_unknown` | seat_unknown | no next pick: require the best starter, forbid the defense |

Two of these are a **pair on purpose**. `empty_starter_late` and
`second_kicker_last_rounds` carry the same round, the same two rounds
remaining and overlapping boards. The only difference is whether the
kicker slot is filled, and that single fact flips the verdict on the same
two players. A model that has learned "no kickers" rather than "fill your
starting slots" passes one and fails the other.

## Discriminating power

Spec section 5: a gate where the model and `argmax_vols` post the same
rate measures nothing. Run cold, the calculator baseline fails the golden
gates on **3 of 12**:

- `third_te_while_wr_empty` — VOLS is global and does not know you hold
  two tight ends already. `delta_starter_points` does, and the case sets
  it to zero for that row.
- `bye_stack` — VOLS does not read the weekly vector.
- `empty_starter_late` — VOLS ranks a bench receiver over a kicker who is
  the difference between a filled starting slot and a zero.

The other nine, the calculator passes. That is honest and it is the
ceiling on what this set can tell you about the model: **three cases of
separation**. Do not read a pass rate on the other nine as evidence the
model is doing anything.

`test_argmax_vols_does_not_pass_the_whole_set` pins that set of three by
name, so a case that quietly stops separating the two fails a test
instead of going unnoticed.

## What this set does not cover

Written out, because a list of what a test suite checks is worth much
less than a list of what it does not.

**Size and statistics.** Twelve cases. One changed verdict moves the pass
rate by eight points. There is no confidence interval and there cannot be
one: this set cannot tell a model that is right 90% of the time from one
that is right 95% of the time, and reporting a rate to two significant
figures off twelve boards would be a lie about precision.

**Contested picks.** Every verdict is one a human can defend in a
sentence. Real draft-night decisions mostly are not — wait-or-take,
running back versus receiver at the same VOLS, a discounted returning
starter. None of that is here. The regret fixtures
(`tests/regret/`) are the only measurement of wait-or-take, and they are
three drafts.

**Real numbers.** Every board is hand-written. The VOLS values, the
gaps between tiers and the ECR spreads are plausible, not recorded. A
model failure that only appears in the shape of a real FantasyPros
distribution will not appear here.

**Format breadth.** Ten- and fourteen-team boards appear once each and
everything else is twelve. One superflex case. No auction, no keeper, no
dynasty, no IDP — those are refusals, not evals. No TE-premium scoring,
no two-flex board, no `OP` slot, no `WRRB_FLEX` or `REC_FLEX`. One host's
conventions throughout.

**Missing-data boards.** No case ships a board with `ecr` absent, and
none exercises the `ecr_missing` banner, an unclassified scoring key, or
an override-CSV board. Those paths are tested for behaviour elsewhere;
they have no golden verdict.

**Flags.** The golden gates are set membership. They say nothing about
whether the model set `UPSIDE`, `POSITION_RUN` or `BYE_STACK` correctly,
and `test_flags_are_not_part_of_a_golden_verdict` pins that separation.
The XOR gates cover the two flags that have a right answer; the other
four are unmeasured.

**Positions.** No case whose required pick is a defense on its own merit,
none about a quarterback in a one-QB league beyond forbidding a backup,
and none about the K or DEF deferral rule (spec section 4) other than
through the two late cases.

**Anything after the draft.** Lineups, waivers, trades. Out of v1.

## One finding, pinned as a test

`bye_hole` compares alternatives only in the recommendation's own bye
week. In `bye_stack`, one receiver slot is empty and one receiver is
rostered, so *whichever* receiver we add, the week he is off leaves that
slot empty and the other receiver would have filled it. The gate fails
both picks. It is symmetric and it cannot see a stack.

The human verdict reads the whole 18-week vector and separates them
easily. `test_bye_hole_gate_cannot_see_a_stack` holds that finding in
place so it stays visible to whoever revisits the gate.
