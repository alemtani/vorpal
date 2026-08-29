"""Replay a completed draft to one seat's pick and freeze the board.

The regret gate asks one question: did the player we recommended survive
to our next turn while a player we listed as an alternative did not? If
so we could have had both and we took them in the wrong order.

Answering it needs no model and no survival curve. A completed draft is
an ordered list of picks. Everything before our pick was gone; everything
taken between our pick and our next one was gone by then; everything else
was still sitting there. That is arithmetic on a list, and it is why this
module has no probabilities in it.

**The frozen-board assumption.** We substitute our own pick and leave the
other eleven teams' picks exactly as recorded. They would have drafted
differently in a world where we took someone else. That is a real
limitation of the replay and it is the reason this is a *floor* on
wait-or-take, not a simulation. The one place it bites hardest is the
player we actually took: in the counterfactual nobody took him, so he
stays available, and `available_at_next` says so.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from vorpal.evals import GateFixtures

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "sleeper"


def snake_pick(teams: int, slot: int, round_no: int) -> int:
    """Pick number for a seat in a snake draft with `reversal_round == 0`."""
    base = (round_no - 1) * teams
    return base + (slot if round_no % 2 else teams + 1 - slot)


@dataclass(frozen=True, slots=True)
class RegretFixture:
    """One seat, one pick, and the record of what happened next.

    Player ids are host ids for NFL players. There is no manager, no
    league, no seat owner and no pick timestamp in here: a seat is an
    integer between 1 and `teams`, which identifies nobody.
    """

    name: str
    draft_id: str
    season: str
    teams: int
    rounds: int
    draft_slot: int
    round_no: int
    pick_no: int
    next_user_pick: int
    actually_picked: str
    drafted_before: tuple[str, ...]
    taken_between: tuple[str, ...]
    universe: tuple[str, ...]
    provenance: str
    era: str

    def board_at_pick(self, board_ids: Iterable[str]) -> frozenset[str]:
        """Which of `board_ids` were undrafted when this seat was on the clock."""
        gone = set(self.drafted_before)
        return frozenset(pid for pid in board_ids if pid not in gone)

    def available_at_next(self, board_ids: Iterable[str]) -> frozenset[str]:
        """Which of `board_ids` were still undrafted at this seat's next turn.

        A player who was never drafted in this draft at all was available
        the whole time, so passing the whole board in and filtering is
        correct — the recorded picks are the only ids that can be gone.
        """
        gone = set(self.drafted_before) | set(self.taken_between)
        return frozenset(pid for pid in board_ids if pid not in gone)

    def gate_fixtures(self, board_ids: Iterable[str]) -> GateFixtures:
        """`GateFixtures` with the regret field filled and nothing else."""
        return GateFixtures(available_at_next=self.available_at_next(board_ids))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def load_picks(draft: str) -> tuple[dict, ...]:
    """The recorded, redacted picks for one draft, in pick order."""
    body = json.loads((RECORDED / f"picks_{draft}.json").read_text())
    return tuple(sorted(body, key=lambda pick: pick["pick_no"]))


def load_draft(draft: str) -> dict:
    return json.loads((RECORDED / f"draft_{draft}.json").read_text())


def replay(
    *,
    name: str,
    draft: str,
    draft_slot: int,
    round_no: int,
    provenance: str,
    era: str,
) -> RegretFixture:
    """Build a regret fixture from a recorded completed draft.

    Reads the same redacted bytes every other test reads, so the fixture
    is derived and not asserted: `test_regret.py` rebuilds it and
    compares.
    """
    header = load_draft(draft)
    picks = load_picks(draft)
    teams = header["settings"]["teams"]
    rounds = header["settings"]["rounds"]
    if header["status"] != "complete":
        raise ValueError(f"{draft} is not a completed draft")
    if round_no >= rounds:
        raise ValueError(f"{draft} round {round_no} has no next user pick")

    pick_no = snake_pick(teams, draft_slot, round_no)
    next_user_pick = snake_pick(teams, draft_slot, round_no + 1)
    mine = _one(picks, pick_no)
    if mine["draft_slot"] != draft_slot:
        raise ValueError(f"pick {pick_no} is not seat {draft_slot}")

    return RegretFixture(
        name=name,
        draft_id=header["draft_id"],
        season=header["season"],
        teams=teams,
        rounds=rounds,
        draft_slot=draft_slot,
        round_no=round_no,
        pick_no=pick_no,
        next_user_pick=next_user_pick,
        actually_picked=mine["player_id"],
        drafted_before=_ids(picks, lambda n: n < pick_no),
        taken_between=_ids(picks, lambda n: pick_no < n < next_user_pick),
        universe=tuple(sorted({pick["player_id"] for pick in picks})),
        provenance=provenance,
        era=era,
    )


def _one(picks: Sequence[dict], pick_no: int) -> dict:
    for pick in picks:
        if pick["pick_no"] == pick_no:
            return pick
    raise ValueError(f"no pick {pick_no} in this draft")


def _ids(picks: Sequence[dict], keep) -> tuple[str, ...]:
    return tuple(pick["player_id"] for pick in picks if keep(pick["pick_no"]))


def load_fixture(name: str) -> RegretFixture:
    body = json.loads((FIXTURES / f"{name}.json").read_text())
    return RegretFixture(
        **{
            key: tuple(value) if isinstance(value, list) else value
            for key, value in body.items()
        }
    )


def all_fixtures() -> tuple[RegretFixture, ...]:
    return tuple(load_fixture(path.stem) for path in sorted(FIXTURES.glob("*.json")))
