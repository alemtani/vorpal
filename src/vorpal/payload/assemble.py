"""Cap the board and assemble a Payload. No network."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace

from vorpal.contracts import (
    Banner,
    BoardRow,
    DraftState,
    LeagueConfig,
    Need,
    Payload,
    Replacement,
    Slot,
)
from vorpal.errors import DataRefusal
from vorpal.valuation.slots import ELIGIBLE

TOP_OVERALL = 50
TOP_PER_POSITION = 10
FILLED_DEPTH = 2
DEPTH_PER_NEED = 2
LATE_ROUNDS = 2

# Nobody drafts these before the last rounds, and ten of each is a fifth of a
# board. Their VOLS is near zero, so nothing else surfaces them either: this
# clause is the only way a kicker reaches the board, and it waits until the
# rounds where a kicker is actually the pick.
DEFERRED_POSITIONS = frozenset({"K", "DEF", "DST"})

BOARD_CAPPED = Banner(
    code="board_capped",
    message="board is capped; do not read scarcity from this list",
)


def remaining_need(needs: Mapping[str, Need], position: str) -> int:
    """Unfilled starter need across every slot `position` can fill.

    A FLEX need counts for RB, WR, and TE alike: any of them can take that seat,
    so any of them is still worth board depth.
    """
    total = 0
    for slot_name, need in needs.items():
        try:
            slot = Slot(slot_name)
        except ValueError:
            continue
        # BN is absent from ELIGIBLE on purpose: bench is not a starter need,
        # and counting it would give every position the same depth.
        allowed = ELIGIBLE.get(slot)
        if allowed is None or position not in allowed:
            continue
        total += max(0, need.required - need.filled)
    return total


def position_depth(
    position: str,
    *,
    needs: Mapping[str, Need],
    picks_left: int,
    teams: int,
) -> int:
    """How many of this position could still start for you. See SPEC.md §4."""
    remaining = remaining_need(needs, position)
    if position in DEFERRED_POSITIONS:
        if remaining <= 0 or picks_left > LATE_ROUNDS * teams:
            return 0
        return remaining
    if remaining <= 0:
        return FILLED_DEPTH
    return min(TOP_PER_POSITION, FILLED_DEPTH + DEPTH_PER_NEED * remaining)


def cap_board(
    rows: Sequence[BoardRow],
    *,
    pick_no: int,
    teams: int,
    rounds: int,
    needs: Mapping[str, Need],
) -> tuple[BoardRow, ...]:
    """Union of top 50 by VOLS and slot-aware depth per position.

    There is deliberately no ADP arm. ADP goes stale as the draft runs, and by
    the late rounds nearly every player left has an ADP behind the clock — so an
    ADP window stops selecting anybody in particular. `adp` still ships on every
    board row; it is the model's input, not the cap's.
    """
    ranked = sorted(rows, key=lambda row: (-row.vols, row.player_id))
    keep: dict[str, BoardRow] = {}
    for row in ranked[:TOP_OVERALL]:
        keep[row.player_id] = row
    by_position: dict[str, list[BoardRow]] = defaultdict(list)
    for row in ranked:
        by_position[row.position].append(row)
    picks_left = max(0, teams * rounds - pick_no)
    for position, group in by_position.items():
        depth = position_depth(
            position, needs=needs, picks_left=picks_left, teams=teams
        )
        for row in group[:depth]:
            keep[row.player_id] = row
    return tuple(sorted(keep.values(), key=lambda row: (-row.vols, row.player_id)))


def build_payload(
    config: LeagueConfig,
    state: DraftState,
    replacement: dict[str, Replacement],
    rows: Sequence[BoardRow],
) -> Payload:
    """Assemble the SPEC.md section 4 payload. Does not guess a seat."""
    capped = cap_board(
        rows,
        pick_no=state.pick_no,
        teams=config.teams,
        rounds=config.rounds,
        needs=state.needs,
    )
    if not capped:
        raise DataRefusal("board has no players")
    hint = capped[0].player_id
    banners = config.banners
    if all(banner.code != BOARD_CAPPED.code for banner in banners):
        banners = (*banners, BOARD_CAPPED)
    config = replace(config, banners=banners)
    if config.slot is None:
        state = replace(
            state,
            next_user_pick=None,
            picks_until_next=None,
            between=None,
        )
    return Payload(
        config=config,
        state=state,
        replacement=dict(replacement),
        hint_argmax_vols=hint,
        board=capped,
    )
