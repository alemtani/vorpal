# Fixtures

Redacted JSON recorded by `tools/record_fixtures.py`. Source league ids are
not stored here. Player ids are Sleeper ids (NFL players, not managers).

## Scenarios

| File | What |
|---|---|
| `sleeper/draft_snake_redraft.json` + `league_snake_redraft.json` + `picks_snake_redraft.json` | League-attached snake redraft. Has K and DEF slots. |
| `sleeper/draft_mock_standalone.json` + `picks_mock_standalone.json` | Standalone mock. `league_id` is JSON `null`. |
| `sleeper/draft_superflex.json` + `league_superflex.json` + `picks_superflex.json` | Superflex (`SUPER_FLEX` / `slots_super_flex`). Has K, no DEF. |
| `sleeper/draft_mid_draft.json` + `picks_mid_draft.json` | Mid-draft picks. Status on the wire was `paused`. |
| `sleeper/user_operator.json` | Synthetic operator only. |
| `sleeper/players.json` | Subset of `GET /players/nfl`. No `bye` field on the wire. |
| `projections/season_regular.json` | Legacy Sleeper/Rotowire season totals. Not the v1 stats source. |
| `fantasypros/projections_week0.json` | FantasyPros season totals (`week=0`). Counting stats plus `points_*` to refuse. |
| `fantasypros/adp_ppr.json` | FantasyPros ADP (`type=ADP`, PPR, `position=ALL`). |
| `fantasypros/consensus_rankings_ppr.json` | Live overall PPR ECR (`position=ALL`). `rank_ecr` is overall draft order. |
| `fantasypros/consensus_rankings_ppr_{qb,rb,wr,te,k,dst}.json` | Positional lists. Parse-join tests only. Not the runtime ECR source. |
| `fantasypros/consensus_rankings_op.json` | Live superflex overall (`position=OP`). |
