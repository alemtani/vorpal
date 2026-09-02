# CLAUDE.md

Read `AGENTS.md` first. It holds the rules: what this tool does, what it
must never do, how work is tracked, and the facts agents get wrong.
This file is the working detail — commands and layout. When the two
disagree, `AGENTS.md` wins.

`docs/SPEC.md` is the contract. Do not invent behavior it does not specify.

## Commands

```sh
uv run pytest                  # full suite, 99% coverage gate
uv run pytest tests/valuation  # one package
uv run pytest -m invariant     # VOLS replacement-rank invariant
uv run ruff check .            # lint
uv run ruff format .           # format, markdown code blocks included
```

`ruff format` runs over `.md` too. Format the docs you touch, or CI fails
on a handoff you never opened.

Markers: `invariant` and `golden` failures are model problems, not code
bugs. `live` hits the network and never runs in CI.

## Layout

| Path | Holds |
|---|---|
| `contracts.py` | Generic types. Host wire names never appear here. |
| `errors.py` | Every error is a `VorpalError`. stderr, exit 2. |
| `platform/` | `LeagueHost` adapter base, and `scoring_keys.py` — the one host key table. |
| `sleeper/` | Sleeper transport. The only package that knows Sleeper's HTTP. |
| `ingest/` | FantasyPros forecast: stats, ADP, ECR, bye, override CSV. |
| `resolve/` | Slots, scoring source, seat, refusals, banners. |
| `valuation/` | Scoring, two-pass VOLS, weekly vector, marginal value. Pure. No IO. |

Read `docs/handoffs/` for package signatures from the v1 build. New work
does not write `SN.md`.

## The shape to keep

FantasyPros supplies the numbers. A league is a key mapping plus its draft
settings. Valuation is pure functions over a table — no network, no IO, no
host. See "A league is a table, not a branch" in `AGENTS.md`.

## Before you open a PR

Link the GitHub issue. If the next person cannot see it from the code,
put it in the PR body. Run the full suite, `ruff check`, and
`ruff format --check`. A PR that skips those is not finished.

`docs/PROOF.md` says which proof a change owes — a test, a golden/regret
case, a dress rehearsal, or a changed night-board snapshot. Carry it.
