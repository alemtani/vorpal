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

### Setup, once

```sh
uv sync --extra tracing
```

`uv sync` makes `.venv` match `pyproject.toml` exactly — it installs what is
missing **and uninstalls anything not declared**. `langsmith` is an optional
extra, so a plain `uv sync` removes it and the next `--trace` run prints
`langsmith: No module named 'langsmith'`. Always pass `--extra tracing`.

Then copy the template and fill in your keys, once:

```sh
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

`.env.example` lists every key, what it is for, and which are optional.

`.env` is gitignored and is never committed. Every run reads it and prints the
key **names** it loaded, never the values. An exported key beats the file, so
`ANTHROPIC_API_KEY=other uv run vorpal ...` still overrides for one run.

The path is relative to where you run the command, so run from the repo root
or pass `--env /path/to/.env`. Exporting by hand still works and needs no file.

GitHub needs no token: the draft-complete issue shells out to `gh`, which uses
your existing `gh auth login`.

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
LangSmith. It needs `LANGSMITH_API_KEY` and the `tracing` extra; without either
the run prints a warning and continues untraced, so it never blocks a draft.

```sh
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
