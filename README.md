# vorpal

Fantasy sports decision support. Projections, valuation, and recommendations —
you make every move.

> *"One, two! One, two! And through and through / The vorpal blade went snicker-snack!"*

## Status

Pre-implementation. See [docs/SPEC.md](docs/SPEC.md).

Configured by league ID. Reads format, scoring, and roster shape from the
platform API — nothing about any league is hardcoded.

## Principles

1. **Recommendations, not actions.** The tool emits proposals. You act in the
   platform. Nothing is automated on your behalf.
2. **Decision quality over outcomes.** A season is one noisy sample. Evals
   separate decision error from projection error, and only claim the ones the
   available data actually supports.
3. **Buy the forecast, build the scoring.** Projections come from a file you
   supply. The league-specific work — scoring, replacement levels, roster
   construction — is what the tool does.
4. **NFL redraft first.** Other sports and formats are a documented
   constraint on the architecture, not current scope.

## License

MIT
