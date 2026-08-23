# vorpal

Fantasy draft agent. Code builds the board. The model recommends. You click.

> *"One, two! One, two! And through and through / The vorpal blade went snicker-snack!"*

## Status

Pre-implementation. See [docs/SPEC.md](docs/SPEC.md).

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
