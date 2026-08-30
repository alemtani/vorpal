# Cassettes

One recorded model answer per request, committed. `evals/run.py` replays
these. A default run spends nothing.

## The key is the request, not the fixture name

A file name here is `sha256` over the request `vorpal.model.build_request`
assembles: the board, the system prompt, the model id, the effort, the
max tokens, and the output schema. A name says which board we meant. A
hash says which question we asked.

That is the property that makes prompt work affordable. **Change a
prompt, change every key** — so the run tells you what went stale
instead of replaying an answer to a question we no longer ask. Transport
settings (retries, deadlines) stay out of the key: they cannot change
the answer.

## A miss is an error

Replay never falls through to a live call. A quiet live call on a miss is
how an eval suite becomes a bill. A miss names the key and tells you to
re-record.

Samples are walked in order and never wrap. `run_stability` asks the same
board five times and wants five draws; handing it draw one five times
would report a spread that was never measured. Running past the last
recorded sample is the same error as never having recorded at all.

## Recording

```sh
uv run python -m evals.run --record            # everything
uv run python -m evals.run --only golden --record
```

`--record` is the only thing that spends. It fills a key up to the number
of calls that run actually makes, and writes after each call, so a crash
keeps what it paid for. A key that is already full costs nothing even
under `--record`.

Nothing re-records on a schedule. A cassette is evidence, and evidence
does not update itself. Re-record by hand when a prompt changes.

## Reading a file

Each file holds the assembled `request` beside the `samples`. The request
is what makes a diff legible and what tells you why a miss missed.
