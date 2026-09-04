---
name: draft-night
description: Run a live Sleeper draft or mock with vorpal, and watch it on the clock. Use when the operator says "kick off the mock", "start the draft", "let's run a mock draft", "run vorpal against draft <id>", or asks you to drive and monitor a real draft. Launches the CLI in the background, tails the log, and triages every banner and error as it lands.
---

# Draft night

You launch the tool and read the log. **The operator clicks in Sleeper.**

## Hard rules

Read `AGENTS.md` "Do not" before anything else. The three that bite here:

- **Never write to the host.** No pick, no autodraft, no browser driving the
  Sleeper UI. vorpal is read-only and so are you.
- **Never fetch FantasyPros by script or browser.** The operator drops CSVs, or
  the API key in `.env` does it.
- **Never edit code mid-draft.** A failing pick is a note for after. The only
  exception is the operator asking outright.

If a pick is on the clock, answering beats being thorough. Say the short thing.

## 1. Preflight

Run these together. All four must pass before you launch.

```sh
cd /Users/alemtani/projects/vorpal
git status --short && git log --oneline -1
uv sync --extra tracing
test -f .env && echo ".env present" || echo ".env MISSING"
gh auth status 2>&1 | head -3
```

- **`--extra tracing` is not optional.** Plain `uv sync` uninstalls `langsmith`,
  because it is declared only as the `tracing` extra. That is the whole cause of
  `langsmith: No module named 'langsmith'`. Never run bare `uv sync` here.
- No `.env`? `cp .env.example .env`, then the operator fills it in. Do not ask
  them to paste a key into the chat, and never read `.env` back to them.
- `gh` unauthenticated only costs the draft-complete issue. Note it, continue.

## 2. Ask what you cannot know

Never guess these. Ask in one message:

| Need | Notes |
|---|---|
| Draft id | Sleeper draft id, not the league id |
| Operator | their Sleeper username |
| Mock or real league | decides whether scoring must be lent |
| Scoring, mocks only | `ppr`, `half`, or `std` |

**A standalone mock has `league_id: null`,** so it carries no scoring table and
`--scoring` is required — without it the run refuses. A real league draft
resolves its own scoring; pass neither flag.

`--fast` is for a short mock clock. A real draft with a long timer does not need
it and it bills premium.

## 3. Launch

Background it. A draft runs for hours and a foreground run blocks the session.

```sh
PYTHONUNBUFFERED=1 uv run vorpal \
  --draft-id <id> --operator <name> [--scoring ppr] [--fast] [--trace] \
  2>&1 | tee ~/vorpal-draft.log
```

Use `Bash` with `run_in_background: true`.

`PYTHONUNBUFFERED=1` is required. Python block-buffers stdout through a pipe, so
without it lines sit unseen until the buffer fills — on a pick clock that is the
same as no log at all.

The board opens in a browser by itself, once, on the first page written. Tell the
operator to leave that tab up; it refreshes itself. Add `--no-open` only if they
ask.

## 4. Arm the watch

Immediately after launching, in the same turn:

```
Monitor(
  description: "errors and banners in the live draft log",
  persistent: true,
  timeout_ms: 3600000,
  command: 'touch ~/vorpal-draft.log; tail -F -n 0 ~/vorpal-draft.log 2>/dev/null | grep -E --line-buffered "banner |^env:|platform error|data refusal|unsupported league|user refusal|^error:|fast mode unavailable|langsmith|open board|github issue|Traceback|Exception|Error|FAILED|Killed|OOM|violation_|degraded|refused|Refus"'
)
```

The filter covers failure signatures, not just the happy path. A watch that greps
only for good news stays silent through a crash, and silence reads exactly like
"still drafting." If you widen it, widen it toward noise.

Only an interactive session holds a monitor. It dies with the session — say so if
the operator talks about starting a fresh one.

## 5. Triage

**Expected. Say nothing after the first mention.**

| Line | Meaning |
|---|---|
| `banner slots_from_mock`, `banner scoring_borrowed` | mocks only, by design |
| `banner unknown_scoring_keys`, `banner unmapped_scoring_keys` | 17 K and DST keys. FantasyPros ships no counting stats for them, so K and DST score ~0 and sort last. Real, permanent, not tonight's problem |
| `banner projection_join_miss`, `banner ecr_join_miss` | ~12 rows out of the pool |
| `banner ecr_team_mismatch` | stale team on one side after an offseason move. The rank is still the right player's |
| `board is capped` | by design |
| `env: loaded .env (...)` | names only, never values. Confirms the file was read |

**Act on these.**

| Line | Do |
|---|---|
| `unsupported league: ...` | Permanent. The format is out of v1. Stop; do not retry |
| `data refusal: ...` | A better file fixes it. Usually a stale or missing FantasyPros drop |
| `platform error: ...` | Sleeper or transport. The loop backs off 5s, 15s, 45s, then holds, and recovers on its own. Only speak up if it repeats past ~45s |
| `user refusal: ...` | Operator identity or seat. Check `--operator` and `--slot` |
| `fast mode unavailable (...); falling back to standard speed` | **Working as intended.** The run degrades instead of dying. Say it once so they know why recs slowed |
| `langsmith: ...` | Tracing only. Never blocks a draft. Note and move on |
| `open board: ...` | The browser did not start. Tell them the file path to open by hand |
| `violation_*` / `model_degraded` | The model's answer failed validation and the page is showing the calculator pick. Say it immediately — the rec on screen is not the model's |
| `Traceback` | Real crash. Report the whole thing |

## 6. While it runs

- Report only what changes what they do next. Quiet is the normal state.
- The model runs **only when their seat is on the clock**. Between turns the page
  shows the calculator and "Not your pick." That is not a bug.
- Poll is 3s while `drafting`, 15s otherwise. Never suggest polling faster.
- If they ask why a rec looks wrong, read the board and the `why`. Do not re-run
  the model and do not edit anything.

## 7. At complete

The loop writes the board once more and returns. It then:

- writes a redacted snapshot next to the board (`*.snapshot.local.json`),
- persists skip records for picks that differed from the rec,
- opens a why-not form, then a GitHub issue linking both.

**The why-not form never appears under the launch above.** It needs a TTY on
stdin, and backgrounding through `tee` does not give it one. That is not a
failure — the skips file still records every divergence, and the issue still
files. To answer the form, rerun the completed draft in the foreground.

Confirm the snapshot exists. It is the artifact that becomes a golden or regret
case later (`docs/PROOF.md`, "The unit of proof"). Never commit it — `private/`
and `*.local.json` are gitignored for a reason.

## 8. After

Offer, do not do:

- promote anything surprising to a golden or regret case (#26, #29),
- file an issue for a real defect, with the log line in the body,
- `uv run python -m evals.run --only human` to see what each policy would have
  said on the operator's mock.

Nothing here is a code change without the operator asking.
