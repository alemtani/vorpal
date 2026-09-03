# Spec: LangSmith tracing, folded into skip capture

Status: needs-spec. Do not implement until this is accepted.
Tracks issue: #56. Folds in #44 / #29. Seed case: #57.

This spec is a scoping plan. The open questions from the #56 draft are
closed below, each with the decision and the reason. Where it revises the
issue's stated decisions, the reason says so.

## Why

Draft night makes one `propose` call per board change. When the operator
clicks a player the model did not recommend, that drift is the signal we
learn from. The #44 skip-capture flow already records the drift as a
durable, on-device artifact (a skips file plus a GitHub issue). This spec
adds a second, searchable view of the same event: the LangSmith run tree
behind the call.

The two are one feedback system, not two parallel sinks. One skip emits
both:

- the durable capture (#44): `board.skips.local.json` and a GitHub issue,
  player ids only, on-device;
- the LangSmith trace (#56): the run tree for the `propose` call, for
  error analysis after the draft.

The first defect worth a trace is already filed: #57, the model doubling
the dissent frame in `why`. That fix landed on `fix/dedupe-dissent-frame`.
This pipeline is what turns the *next* such defect into a case without a
live re-run.

LangSmith is the viewer. It records and replays LLM traces and groups a
retry into one run tree. We do not build our own viewer. This is a sink
for error analysis. It is not a gate and not a judge. `docs/PROOF.md`
holds the line: "Draft night traces `propose`, not recommend cassettes.
No LLM-as-judge." This spec keeps it.

## Scope

In scope:

- Trace every `propose` call on the draft-night path. One call is one run
  tree: a parent run plus one child per transport call (the retry is the
  second child).
- Parent run fields: redacted payload, the proposal, violation codes and
  messages, the degraded flag, attempts, and wall-clock latency.
- Child run fields: the raw proposal object, the model id and effort, and
  per-call latency.
- Stitch the human pick onto the parent run at draft complete, from the
  skip-capture join.
- Fold #44 in: one `FeedbackCollector` drives both sinks. Rename its
  sample recorder to end the name collision (below).

Out of scope:

- `recommend`, `run_stability`, and the eval path. Those replay cassettes;
  they need no live trace sink.
- Any change to what the operator sees on the clock. The board is the
  same. Tracing is a side effect of the call, not a view.
- LLM-as-judge, scoring, or an automated gate on a trace.
- Per-child `stop_reason`. `AnthropicTransport` already raises on
  `refusal` and `max_tokens`, so a child that returns a proposal always
  stopped normally. The informative stop reasons never reach a traced
  child. Capturing it would change the transport's return type for no
  signal. Left out.

## Decisions (open questions, closed)

**1. Where the parent run is created.** In `model/`, invoked from the
feedback seam. Not inside `propose`, not in `loop.py`.

The trace code lives in a new `model/tracing.py`, next to `call.py`, which
already imports `anthropic`. This honors the issue's "the sink lives in
`model/`". `valuation/` is untouched and imports no sink.

But the parent run is *created* one layer up, at the `_Proposals._call`
seam in `cli.py` that #44 already built. That seam holds the `payload`,
the assembled `Recommendation` (`degraded`, `violations`, `attempts`), and
the samples. `propose` in `call.py` stays byte-for-byte unchanged, so the
cassette key and the eval path do not move. The draft asked call.py vs
loop.py; the answer is neither — the seam is the cli/feedback layer, and
the reusable code sits in `model/tracing.py`.

**2. `why` is sent raw, and player names stay.** A trace is read by a
human. Player names and ids are public NFL data and stay in the trace,
unredacted — the whole point of #57 is to read "we passed Loveland", not
"we passed 12517". `why` is free text; it stays raw too. See "Redaction"
for the one thing that is dropped: drafter and league identity, never a
player. Raw `why` off-device is the accepted tradeoff. See retention.

**3. Trace every call; the skip drives the durable capture.** Volume is
tiny: at most about sixteen on-clock picks per draft, one or two calls
each. A call where the operator agreed is still a case (#29, PROOF). So
the LangSmith trace fires on every `propose` call. The GitHub issue and
the skips file fire only on a skip, exactly as #44 has it. One feedback
system: trace records every call, skip records the drift.

**4. One project, tagged per draft.** `LANGSMITH_PROJECT` defaults to
`vorpal-draft`. Each process run gets a random `draft_session` id,
generated at start, and every run tree carries it as LangSmith metadata
and a tag. Reading one draft after the fact is a filter on that tag.
Per-draft projects proliferate and need cleanup; a tag gives the same
grouping for one env var. The host `draft_id` is an `IDENTITY_KEY` and is
never the project or the tag; the session id is random and carries no
identity.

**5. Submit per call, fire-and-forget, off the render path.** Returning
the rec never waits on the trace. The feedback seam hands the trace to the
sink and moves on; the sink builds and submits the run tree on a
background thread. The render draws from the `Recommendation` that
`propose` already returned. Per-call submit is safer against a mid-draft
crash than batching at complete. Only the `human_pick` patch is deferred
to complete, where there is no clock to block.

**6. Retention: LangSmith is additive; the local copy already exists.**
The durable on-device record is the #44 skips file plus the #22 snapshot,
both player ids only. LangSmith is the searchable viewer on top. No new
local store is needed. The only free text leaving the process is `why`
(public player names). No league id, draft id, or manager name leaves the
process.

## The name collision

#44 introduced `board.feedback.TracingTransport`: a wrapper that buffers
raw samples for the durable capture. It does not trace to any sink. The
#56 draft proposed a second `TracingTransport` for LangSmith. Two classes
of one name is the collision to remove.

Decision: there is exactly one `TracingTransport`, and it is the buffering
wrapper. Move it from `board/feedback.py` to `model/tracing.py` and rename
it `SampleRecorder`. It stays a pure `Transport`: it wraps an inner
transport, records `(sample, latency_ms)` per `complete`, and returns the
response unchanged. It imports no LangSmith. The LangSmith emission is a
separate function in the same module (below). `propose` still cannot tell
the wrapper from the real transport.

## Design

Three pieces. Two are new code in `model/tracing.py`. One is a change to
the #44 feedback layer.

### 1. `SampleRecorder` (moved, renamed from #44)

`model/tracing.py`. A `Transport` wrapper.

- `__init__(inner)`: holds the inner transport.
- `complete(payload)`: times the inner call, appends
  `(raw_sample, latency_ms)`, returns the raw sample unchanged.
- `take()`: returns and clears the buffered pairs.

It adds per-call latency to what #44's wrapper already buffered. No
LangSmith import.

### 2. `TraceSink` (new)

`model/tracing.py`. The LangSmith emitter. Guarded optional import.

- Construction reads config once: `enabled()` is true only when
  `VORPAL_TRACING` is on **and** `LANGSMITH_API_KEY` is set **and**
  `langsmith` imports. Otherwise every method is a no-op.
- `log(pick_no, payload, recommendation, samples, latency_ms) -> None`:
  builds one run tree and posts it best-effort.
  - Parent run: redacted `payload`, redacted `proposal`, `violations`
    (codes and messages), `degraded`, `attempts`, `latency_ms`, and the
    `draft_session` tag. `why` is inside the proposal, sent raw.
  - One child per buffered sample: the raw proposal object, `model` id,
    `effort`, per-call latency. `MODEL_ID` and `EFFORT` are the `call.py`
    constants.
  - Stores `pick_no -> run_id` so `patch_human_pick` can find the parent.
- `log` returns immediately; the build and submit run on a background
  thread (decision 5).
- `patch_human_pick(pick_no, human_pick) -> None`: updates the stored
  parent run with the player id. Best-effort; a down sink drops the patch.

Every method wraps the SDK in `try/except`: connect, log, flush, patch. A
raise is caught, logged to stderr, and swallowed. Tracing never changes
the proposal and never raises on the pick clock. When `enabled()` is
false there is no run tree at all.

### Redaction: drop the drafters, keep the players

A player is public. A drafter is not. The trace drops league and manager
identity and nothing else. Player ids, player names, stats, ADP, ECR,
VOLS, slots, scoring, and pick numbers all stay.

The drop set is a documented subset of the one `IDENTITY_KEYS` table, not
a second denylist:

```
TRACE_DROP = IDENTITY_KEYS - {"name", "first_name", "last_name"}
```

That is: drop `league_id`, `scoring_league_id`, `draft_id`, `picked_by`,
`display_name`, `username`, `user_id`. Keep the three name keys, which on
the board rows are the player's name. Manager identity never rides on
those keys; it rides on `display_name`, `username`, `picked_by`, and
`user_id`, which are dropped. A new identity field goes on `IDENTITY_KEYS`
and, unless it is a player-name key, the trace drops it for free.

`human_pick` is a player id. No league id, draft id, or manager name
leaves the process; player names do, on purpose.

This splits from the durable #22/#44 snapshot on purpose. That artifact
stays player-ids-only, per AGENTS.md and PROOF.md: it is the machine-read
seed for an eval case, where the id is the stable join key and a name
would drift. The trace is human-read in LangSmith, where the name is what
makes a defect legible. Names for the human view, ids for the case. If you
later want the snapshot to carry names too, that is a separate change to
AGENTS.md, not this spec.

### 3. Feedback layer folds both sinks (#44 change)

`board/feedback.py`. `FeedbackCollector` gains a `TraceSink` and the full
`Recommendation`, not just the `{degraded, payload, samples}` dict #44
built.

- The `_Proposals._call` seam in `cli.py` times `propose`, and passes the
  `payload`, the `Recommendation`, the recorder's `take()` output, and the
  latency to the collector.
- On each call: the collector calls `trace_sink.log(...)` (every call) and
  keeps the durable trace dict for the skips file (unchanged shape plus
  `violations` and `attempts`, so the issue body carries them too).
- At complete, in `finish`: for each skip, call
  `trace_sink.patch_human_pick(pick_no, human_pick)` before opening the
  GitHub issue. Both patch and issue are best-effort.

`cli.py` wires a `SampleRecorder` around the transport and a `TraceSink`
built from the environment. Both default to the no-op path when tracing is
off.

## Dependency and config

- `langsmith` is optional. Add a `[project.optional-dependencies]`
  `tracing` extra. The core install stays `anthropic` + `httpx`.
- Env:
  - `LANGSMITH_API_KEY`: the key. Unset means tracing is off.
  - `LANGSMITH_PROJECT`: the project. Default `vorpal-draft`.
  - `VORPAL_TRACING`: an explicit on/off gate, default off. Tracing needs
    the gate on **and** the key set. This stops a stray key in a shell
    from tracing a test run.
- CI never traces. The gate is off by default, tests do not set the key,
  and `live` stays the only marker that touches the network. A test traces
  only when it builds a `TraceSink` around a stub on purpose.

## Implementation tasks

Two PRs, one design. Small commits, per AGENTS.md.

**PR A — land #44 to this spec's shape (durable capture, rung 0).**

1. Move the buffering wrapper to `model/tracing.py` as `SampleRecorder`;
   add per-call latency; delete `board.feedback.TracingTransport`.
2. Widen the trace dict the feedback layer keeps to include `violations`
   and `attempts`. Update the issue body.
3. Update imports in `cli.py` and the #44 tests.
4. Merge. This is the durable half, on-device, no network.

**PR B — add the LangSmith sink (#56, rung 0).**

1. Add the `tracing` extra to `pyproject.toml`.
2. Add `TraceSink` to `model/tracing.py`: config gate, run-tree build,
   `patch_human_pick`, best-effort guards, the `draft_session` tag.
3. Time `propose` at the `_Proposals._call` seam; pass the
   `Recommendation` and latency into the collector.
4. Wire the collector to call `log` on every call and `patch_human_pick`
   per skip at complete.
5. Build the `TraceSink` from the environment in `cli.py`; default no-op.

## Proof owed

Rung 0 (`docs/PROOF.md`). The change touches the transport seam, not the
operator's view and not the model's judgment on a pick. Unit tests only.
No golden, regret, snapshot, or rehearsal.

Tests to write (TDD, fail first):

1. Tracing off (no key, or gate off, or `langsmith` absent) is a no-op.
   `propose` returns the same `Recommendation` and calls the inner
   transport directly. No run tree.
2. A `TraceSink` whose SDK raises at `log` does not fail the call. The
   proposal returns; the error goes to stderr.
3. `SampleRecorder.complete` returns the inner response unchanged and
   buffers one `(sample, latency)` pair per call.
4. The traced payload drops drafters, keeps players. Assert against a
   payload carrying a `league_id`, a `username`, and a player-row `name`:
   `league_id` and `username` are gone, `name` and `player_id` remain.
5. The retry path logs one parent with two children and `attempts == 2`.
6. The degraded path records `degraded == True` and the violation codes on
   the parent.
7. `log` does not block on the sink: a slow or hanging submit does not
   delay the return of the `Recommendation`. Assert the rec returns before
   the sink's submit completes (a stub that blocks on an event the test
   controls).
8. `patch_human_pick` on a down sink drops the patch and does not raise;
   the on-clock trace is already logged.
9. A skip fires both sinks: the durable skips file gains a record **and**
   `patch_human_pick` is called for that pick. Agreement fires the trace
   but no skip record and no patch.

Gates: `uv run pytest` at 99% coverage, `ruff check`, `ruff format
--check` (Markdown included). New code does not lower coverage or exclude
itself.

The first real trace is the seed for a later regret case (#29), not part
of these PRs.
