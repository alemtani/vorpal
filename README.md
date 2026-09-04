# vorpal

Fantasy draft agent. Code builds the board. The model recommends. You click.

> *"One, two! One, two! And through and through / The vorpal blade went snicker-snack!"*

## Status

v1 is implemented. Sleeper redraft, FantasyPros forecast, VOLS board, one
model rec per pick. You click. Contract: [docs/SPEC.md](docs/SPEC.md).

Twelve binary eval gates. CI replays recorded golden answers and fails the
build on seven of them; the other five need a fixture the golden boards do
not carry, or wait on a gate bug (#31). CI does not call the model. The
four-column runner (`evals/run.py`) is local, not CI.

Configured by draft ID and operator identity. Scoring from a league (the
draft's own, or a borrowed one for mocks). Stats and ADP from the platform.
ECR from FantasyPros. Nothing about any league is hardcoded.

## Run a draft

One command reads the draft, values the pool, asks the model, and writes
`board.html`. The API is read-only. You still click in Sleeper.

First, install and set the two keys once:

```sh
uv sync
export ANTHROPIC_API_KEY=...     # the model rec; required for any real draft
export FANTASYPROS_API_KEY=...   # the forecast, or pass --override <csv> when FP is down
```

**Live draft.** A real league draft carries its own `league_id`, so scoring
resolves on its own. Pass only the draft id and your Sleeper name:

```sh
uv run vorpal --draft-id 1234567890 --operator your_sleeper_name
```

**Mock draft.** A standalone mock has no league, so you must lend it scoring.
Use a canonical preset (`std`, `half`, `ppr`):

```sh
uv run vorpal --draft-id 9876543210 --operator your_sleeper_name --scoring ppr --fast
```

Or borrow a real league's scoring instead of a preset:

```sh
uv run vorpal --draft-id 9876543210 --operator your_sleeper_name \
  --scoring-league-id 1112223334 --fast
```

`--scoring` and `--scoring-league-id` are mutually exclusive. Slots always
come from the mock itself. `--fast` buys a quicker rec for the short mock
clock; a real draft with a longer timer does not need it. Add `--slot N`
when the draft order is partial, and `--out <file>` to write elsewhere.

The board opens in your browser on its own, once, as soon as the first page
is written. The page refreshes itself from there, so leave the tab up. Pass
`--no-open` on a headless box, or when the tab is already open.

**Trace to LangSmith (optional).** Add `--trace` to send propose calls to
LangSmith. It needs `LANGSMITH_API_KEY`; without the key the run prints a
warning and continues untraced, so it never blocks a draft. `LANGSMITH_PROJECT`
is an optional label.

```sh
export LANGSMITH_API_KEY=...
export LANGSMITH_PROJECT=vorpal-draft-night   # optional

# live, traced
uv run vorpal --draft-id 1234567890 --operator your_sleeper_name --trace

# mock, traced
uv run vorpal --draft-id 9876543210 --operator your_sleeper_name \
  --scoring ppr --fast --trace
```

## Principles

1. **Recommend, don't click.** The model emits a proposal. You act in
   Sleeper. The API is read-only.
2. **Numbers in, judgment out.** VOLS, ADP, ECR, spread, roster needs are
   computed. The model picks. Evals gate that pick.
3. **Buy the forecast, apply this league.** Counting stats, not someone
   else's fantasy-point total. A CSV can override the forecast.
4. **NFL redraft first.** Other sports are a constraint on what may be
   shared later, not current scope.
