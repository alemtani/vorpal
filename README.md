# vorpal

Fantasy sports decision support. Projections, valuation, and recommendations —
you make every move.

> *"One, two! One, two! And through and through / The vorpal blade went snicker-snack!"*

## Status

Pre-implementation. See [docs/SPEC.md](docs/SPEC.md).

Configured by league ID. Reads format, scoring, and roster shape from the
platform API — nothing about any league is hardcoded.

## Principles

1. **Recommendations, not actions.** Nothing executes without explicit
   approval. The executor is an interface; `manual` is the only
   implementation.
2. **Decision quality over outcomes.** A season is one noisy sample. Evals
   separate decision error from projection error.
3. **NFL first.** Other sports are a documented constraint on the
   architecture, not current scope.

## License

MIT
