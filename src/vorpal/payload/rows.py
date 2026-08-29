"""Board rows: join VOLS, the weekly delta, ADP, and ECR onto one table.

The delta is the expensive column — two 18-week fills per candidate — so the
cap runs first and only the survivors pay for it.
"""

from __future__ import annotations

from collections.abc import Container, Mapping, Sequence

from vorpal.contracts import BoardRow, EcrRow, Need, Slot
from vorpal.payload.assemble import cap_board
from vorpal.resolve.eligibility import legal_slots
from vorpal.valuation import ScoredPlayer, VolsResult, delta_starter_points


def build_rows(
    values: VolsResult,
    *,
    pool: Mapping[str, ScoredPlayer],
    available: Container[str],
    adp: Mapping[str, float],
    ecr: Mapping[str, EcrRow],
    roster: Sequence[ScoredPlayer],
    slots: Sequence[Slot],
    teams: int,
    rounds: int,
    pick_no: int,
    needs: Mapping[str, Need],
) -> tuple[BoardRow, ...]:
    """Every available valued player, capped, with `delta_starter_points` filled.

    Market-only rows never reach `values`, so they never reach the board. That
    is SPEC.md section 4: a player FantasyPros does not project is not a
    starting-slot candidate.
    """
    roster_slots = tuple(slots)
    provisional = tuple(
        _row(value, pool=pool, adp=adp, ecr=ecr, slots=roster_slots, delta=0.0)
        for value in values.values
        if value.player_id in available and value.player_id in pool
    )
    capped = cap_board(
        provisional,
        pick_no=pick_no,
        teams=teams,
        rounds=rounds,
        needs=needs,
    )
    by_id = values.value_by_id()
    return tuple(
        _row(
            by_id[row.player_id],
            pool=pool,
            adp=adp,
            ecr=ecr,
            slots=roster_slots,
            delta=delta_starter_points(roster, pool[row.player_id], roster_slots),
        )
        for row in capped
    )


def _row(
    value,
    *,
    pool: Mapping[str, ScoredPlayer],
    adp: Mapping[str, float],
    ecr: Mapping[str, EcrRow],
    slots: tuple[Slot, ...],
    delta: float,
) -> BoardRow:
    player = pool[value.player_id]
    rank = ecr.get(value.player_id)
    return BoardRow(
        player_id=value.player_id,
        name=player.name,
        position=value.position,
        points=value.points,
        vols=value.vols,
        delta_starter_points=delta,
        adp=adp.get(value.player_id, 0.0),
        legal_slots=legal_slots(value.position, slots),
        bye=player.bye,
        gp=player.gp,
        ecr=None if rank is None else rank.rank_ecr,
        ecr_min=None if rank is None else rank.rank_min,
        ecr_max=None if rank is None else rank.rank_max,
        ecr_std=None if rank is None else rank.rank_std,
    )
