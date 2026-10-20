# Season mode

In-season advice for one Sleeper league, sent by email from GitHub Actions.
Read-only. The human makes every move in Sleeper.

## Jobs

| Job | When (PT) | Sends |
|---|---|---|
| `lineup` | Wed 07:00 | Always |
| `lineup` | Thu–Mon 07:00, Thu 16:00, Sun 08:45, Sun 12:00, Mon 15:45 | Only when the advice changed |
| `waivers` | Tue 07:00 | Always |
| `trades` | Hourly | Only for an offer not yet emailed |
| `trade` | By hand | Always |

Crons are UTC and cover PDT and PST. Each job checks the PT hour.

## Forecast for one player, one week

1. **Opportunity model** (RB/WR/TE). Every game this season, weighted
   `0.5 ** (weeks ago / 4)`. Weighted targets, carries, red-zone targets,
   red-zone carries. Catch rate and yards per target shrink toward the
   position average with `k = 60` targets; yards per carry with `k = 120`
   carries. Expected TDs: `0.30·RZ tgt + 0.012·other tgt + 0.19·RZ car +
   0.005·other car`. TDs used: `0.75·expected + 0.25·actual`. The line is
   scored with the league's scoring table.
2. **Vendors.** Sleeper and ESPN weekly stat lines, scored with the
   league's table. Mean of the vendors that have the player.
3. **Blend.** `w·model + (1 − w)·vendor mean`, `w = 0.25` (2025
   backtest). The model weight scales by `min(1, role games / 3)`. A role
   game is a game where every same-position teammate who projects over 5
   points this week was also active.
4. **Status.** Bye, Out, IR, Suspended: 0. Doubtful ×0.25.
   Questionable ×0.85. QBs are vendor-only.

## Values

- **Lineup:** best legal lineup for the league's slots. Fill the most
  specific slots first.
- **Rest of season:** simulate weeks to 17. Each player misses a week with
  probability 0.08, and stays out 0–3 more weeks. Playoff weeks count 1.5×.
  Add/drop and trade gains are mean lineup points after − before, on the
  same random draws.
- **Hold rule:** never suggest dropping a player whose snap share and
  targets + carries rose in each of the last 2 games.
- **FAAB bid:** `median winning bid × gain / 20`, capped at 40% of the
  budget left.
- **Trade verdict:** ACCEPT if weeks to 14 gain > +5 and playoffs ≥ 0.
  DECLINE if weeks to 14 gain < 0. Else CLOSE CALL. FantasyCalc value is
  context only.

`vorpal season fit` re-runs the 2025 backtest that chose these constants.
