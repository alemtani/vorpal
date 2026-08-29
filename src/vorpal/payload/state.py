"""Draft state for the payload: snake arithmetic, roster, needs, between.

Everything here is a function of the resolved config plus the picks so far.
No network, no host, no model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vorpal.contracts import (
    BetweenTeam,
    DraftState,
    Need,
    Pick,
    RecentPick,
    RosterPlayer,
    Seat,
    Slot,
)
from vorpal.valuation import ScoredPlayer, fill_starters
from vorpal.valuation.slots import greedy_fill, starter_counts

RECENT_PICKS = 5


def slot_on_the_clock(pick_no: int, teams: int) -> int:
    """Which draft slot owns `pick_no`. Snake: even rounds run backwards."""
    index = (pick_no - 1) % teams
    round_ = (pick_no - 1) // teams + 1
    return index + 1 if round_ % 2 == 1 else teams - index


def pick_no_for(*, round_: int, slot: int, teams: int) -> int:
    """The pick number a draft slot owns in one round."""
    offset = slot if round_ % 2 == 1 else teams - slot + 1
    return (round_ - 1) * teams + offset


def next_pick_for_slot(
    *, pick_no: int, slot: int, teams: int, rounds: int
) -> int | None:
    """First pick at or after `pick_no` that belongs to `slot`. None past the end."""
    for round_ in range(1, rounds + 1):
        candidate = pick_no_for(round_=round_, slot=slot, teams=teams)
        if candidate >= pick_no:
            return candidate
    return None


def needs_from(positions: Sequence[str], slots: Sequence[Slot]) -> dict[str, Need]:
    """Seat these positions into the starting slots and report what is short.

    Bench is not a need: `starter_counts` drops it, so a roster of ten never
    reads as fully seated.
    """
    counts = starter_counts(slots)
    ordered = [_Positioned(position) for position in positions]
    seated, _ = greedy_fill(ordered, counts)
    return {
        slot.value: Need(filled=len(seated.get(slot, ())), required=required)
        for slot, required in counts.items()
    }


class _Positioned:
    """A bare position, for a fill that only reads eligibility."""

    __slots__ = ("position",)

    def __init__(self, position: str) -> None:
        self.position = position


def build_state(
    *,
    pick_no: int,
    slots: Sequence[Slot],
    teams: int,
    rounds: int,
    seat: Seat | None,
    picks: Sequence[Pick],
    pool: Mapping[str, ScoredPlayer],
) -> DraftState:
    """Assemble SPEC.md section 4 `state`. Omits the seat fields when seat is None."""
    roster = _roster(picks, seat, pool)
    scored = tuple(_scored(pick, pool) for pick in _seat_picks(picks, seat))
    state = DraftState(
        pick_no=pick_no,
        user_roster=roster,
        needs=needs_from([player.position for player in roster], slots),
        weekly=fill_starters(scored, slots),
        recent=tuple(
            RecentPick(
                player_id=pick.player_id,
                position=_position(pick, pool),
                pick_no=pick.pick_no,
            )
            for pick in sorted(picks, key=lambda pick: pick.pick_no)[-RECENT_PICKS:]
        ),
    )
    if seat is None:
        return state
    next_pick = next_pick_for_slot(
        pick_no=pick_no, slot=seat.slot, teams=teams, rounds=rounds
    )
    if next_pick is None:
        return state
    return DraftState(
        pick_no=state.pick_no,
        user_roster=state.user_roster,
        needs=state.needs,
        weekly=state.weekly,
        recent=state.recent,
        next_user_pick=next_pick,
        picks_until_next=next_pick - pick_no,
        between=_between(
            picks=picks,
            pool=pool,
            slots=slots,
            teams=teams,
            first=pick_no,
            last=next_pick,
        ),
    )


def _seat_picks(picks: Sequence[Pick], seat: Seat | None) -> tuple[Pick, ...]:
    if seat is None:
        return ()
    return tuple(pick for pick in picks if pick.draft_slot == seat.slot)


def _position(pick: Pick, pool: Mapping[str, ScoredPlayer]) -> str:
    player = pool.get(pick.player_id)
    if player is not None:
        return player.position
    return pick.position or ""


def _name(pick: Pick, pool: Mapping[str, ScoredPlayer]) -> str:
    player = pool.get(pick.player_id)
    if player is not None and player.name:
        return player.name
    parts = [part for part in (pick.first_name, pick.last_name) if part]
    return " ".join(parts) if parts else pick.player_id


def _scored(pick: Pick, pool: Mapping[str, ScoredPlayer]) -> ScoredPlayer:
    player = pool.get(pick.player_id)
    if player is not None:
        return player
    # Drafted but unprojected: it still holds a slot, it just scores nothing.
    return ScoredPlayer(
        player_id=pick.player_id,
        position=_position(pick, pool),
        points=0.0,
        name=_name(pick, pool),
    )


def _roster(
    picks: Sequence[Pick], seat: Seat | None, pool: Mapping[str, ScoredPlayer]
) -> tuple[RosterPlayer, ...]:
    return tuple(
        RosterPlayer(
            player_id=pick.player_id,
            name=_name(pick, pool),
            position=_position(pick, pool),
            bye=None if (player := pool.get(pick.player_id)) is None else player.bye,
        )
        for pick in sorted(_seat_picks(picks, seat), key=lambda pick: pick.pick_no)
    )


def _between(
    *,
    picks: Sequence[Pick],
    pool: Mapping[str, ScoredPlayer],
    slots: Sequence[Slot],
    teams: int,
    first: int,
    last: int,
) -> tuple[BetweenTeam, ...]:
    """One row per team picking in [first, last). Their roster, their needs."""
    by_slot: dict[int, list[str]] = {}
    for pick in picks:
        by_slot.setdefault(pick.draft_slot, []).append(_position(pick, pool))
    out: list[BetweenTeam] = []
    seen: set[int] = set()
    for pick_no in range(first, last):
        slot = slot_on_the_clock(pick_no, teams)
        if slot in seen:
            continue
        seen.add(slot)
        positions = by_slot.get(slot, [])
        roster: dict[str, int] = {}
        for position in positions:
            roster[position] = roster.get(position, 0) + 1
        out.append(
            BetweenTeam(
                slot=slot,
                roster=roster,
                needs=needs_from(positions, slots),
            )
        )
    return tuple(out)
