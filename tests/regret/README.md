# Regret fixtures

**Four seats across three completed drafts.** Each one freezes a real
board at one seat's pick and records who was still there at that seat's
next turn.

The regret gate is the only measurement this tool has of wait-or-take,
which spec section 1 hands to the model outright. It needs no survival
model and no judge: a completed draft is an ordered list, and who
survived twenty picks is arithmetic on that list.

| Fixture | Draft | Season | Seat | Pick | Next | Taken between |
|---|---|---|---|---|---|---|
| `snake_redraft_seat02_r03` | 12-team PPR redraft | 2025 | 2 | 26 | 47 | 20 |
| `snake_redraft_seat02_r09` | same draft, later | 2025 | 2 | 98 | 119 | 20 |
| `superflex_seat07_r02` | 12-team superflex | 2026 | 7 | 18 | 31 | 12 |
| `mock_standalone_seat06_r05` | standalone mock | 2026 | 6 | 54 | 67 | 12 |

## Derived, not written

`build.py` replays the recorded picks. `test_regret.py` rebuilds every
file and compares it byte for byte with what is committed, so a fixture
cannot drift from the record it claims to be.

```sh
uv run python tests/regret/build.py     # regenerate
uv run pytest tests/regret              # check they still match
```

## Redaction

Other people's drafts fall under the same no-commit rule as our own
league (AGENTS.md). A fixture holds NFL player ids, pick numbers, a seat
number between 1 and 12, and prose we wrote. It holds no manager, no seat
owner, no league id, no timestamp, and none of the `picked_by`,
`roster_id`, `metadata` or `reactions` fields the wire carries.

A seat is an integer. It identifies nobody.

`test_no_manager_and_no_league_in_the_file` enumerates the allowed fields
and searches the file text for the shape a leaked seat owner would take.
Redaction is a claim; that test is the check.

The `draft_id` values (`draft_snake_redraft`, …) are the synthetic ids
the seed wrote when it recorded the fixtures. The real ids are not in
this repository.

## Their board is their ADP era

Every fixture carries an `era` field and it is not decoration. Survival
in a 2025 room is a fact about the 2025 market: which players that room
believed in, in the order that season's consensus put them. Read across
to a different season and it becomes a forecast, which is exactly what
this gate exists to avoid being.

The superflex fixture is the sharpest case. Quarterback survival in
superflex is the most format-specific number in this directory and means
nothing in a one-QB league.

The mock is the weakest record, and says so in its own `provenance`: 32
of its 192 picks were made by the platform's autopick rather than by a
person, so it partly measures the platform's ranking rather than a room.
It is kept because a room drafting close to raw ADP is a different
failure mode to measure against, not because it is as good as the other
two.

## The frozen-board assumption

We substitute our pick and leave the other eleven teams' picks exactly as
recorded. In a world where we took somebody else, they would have drafted
differently. That makes this a **floor** on wait-or-take, not a
simulation.

The assumption bites hardest on the player we actually took: in the
counterfactual nobody took him, so `available_at_next` keeps him
available. That is deliberate and
`test_our_own_pick_stays_available_in_the_counterfactual` pins it.

## What these fixtures do not cover

- **Three drafts.** Two of them are the same draft at two picks, so the
  independent rooms number is three, not four. Nothing here supports
  fitting anything. Spec section 7 says VONA waits until the regret set
  holds enough drafts to fit survival; four seats is not that, and it is
  not close.
- **One host, one sport, snake only.** No auction, no linear, no
  reversal round, no keeper.
- **Two seasons.** 2025 and 2026 preseason. No older era, so nothing
  here shows how fast a market's survival pattern goes stale.
- **Mid-round picks only.** No round one, where nothing has happened yet,
  and no final round, where there is no next turn to survive to.
- **Nothing about whether the pick was good.** The gate fails one shape
  only: we recommended a player who kept, and listed an alternative who
  did not. A pick that was wrong but where both players survived passes,
  and should — nothing was lost.

## What S10 calls

```python
from replay import all_fixtures, load_fixture

fixture = load_fixture("snake_redraft_seat02_r03")
board_ids = [row.player_id for row in payload.board]

fixture.board_at_pick(board_ids)  # undrafted when the seat was on the clock
fixture.available_at_next(board_ids)  # still undrafted at its next turn
fixture.gate_fixtures(board_ids)  # GateFixtures with available_at_next set
```

Pass the **whole board** in, not a drafted set. A player this room never
took was available the entire time, and filtering the board is what keeps
him so.
