# vorpal

Fantasy draft agent. Code builds the board. The model recommends. You click.

> *"One, two! One, two! And through and through / The vorpal blade went snicker-snack!"*

## Status

v1 is implemented. Sleeper redraft, FantasyPros forecast, VOLS board, one
model rec per pick. You click. Contract: [docs/SPEC.md](docs/SPEC.md).

Eleven binary eval gates. CI replays recorded golden answers and fails the
build if a rec hits a forbid or misses a require. It does not call the
model. The four-column runner (`evals/run.py`) is local, not CI.

Configured by draft ID and operator identity. Scoring from a league (the
draft's own, or a borrowed one for mocks). Stats and ADP from the platform.
ECR from FantasyPros. Nothing about any league is hardcoded.

## Principles

1. **Recommend, don't click.** The model emits a proposal. You act in
   Sleeper. The API is read-only.
2. **Numbers in, judgment out.** VOLS, ADP, ECR, spread, roster needs are
   computed. The model picks. Evals gate that pick.
3. **Buy the forecast, apply this league.** Counting stats, not someone
   else's fantasy-point total. A CSV can override the forecast.
4. **NFL redraft first.** Other sports are a constraint on what may be
   shared later, not current scope.
