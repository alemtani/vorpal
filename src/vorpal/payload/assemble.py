"""Cap the board and assemble a Payload. No network."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace

from vorpal.contracts import (
    Banner,
    BoardRow,
    DraftState,
    LeagueConfig,
    Payload,
    Replacement,
)
from vorpal.errors import DataRefusal

TOP_OVERALL = 50
TOP_PER_POSITION = 10
ADP_ROUNDS_AHEAD = 2

BOARD_CAPPED = Banner(
    code="board_capped",
    message="board is capped; do not read scarcity from this list",
)


def cap_board(
    rows: Sequence[BoardRow],
    *,
    pick_no: int,
    teams: int,
) -> tuple[BoardRow, ...]:
    """Keep the union of top 50, top 10 per position, and the next two ADP rounds."""
    ranked = sorted(rows, key=lambda row: (-row.vols, row.player_id))
    keep: dict[str, BoardRow] = {}
    for row in ranked[:TOP_OVERALL]:
        keep[row.player_id] = row
    by_position: dict[str, list[BoardRow]] = defaultdict(list)
    for row in ranked:
        by_position[row.position].append(row)
    for group in by_position.values():
        for row in group[:TOP_PER_POSITION]:
            keep[row.player_id] = row
    adp_hi = pick_no + ADP_ROUNDS_AHEAD * teams
    for row in ranked:
        if pick_no <= row.adp <= adp_hi:
            keep[row.player_id] = row
    return tuple(sorted(keep.values(), key=lambda row: (-row.vols, row.player_id)))


def build_payload(
    config: LeagueConfig,
    state: DraftState,
    replacement: dict[str, Replacement],
    rows: Sequence[BoardRow],
) -> Payload:
    """Assemble the SPEC.md section 4 payload. Does not guess a seat."""
    capped = cap_board(rows, pick_no=state.pick_no, teams=config.teams)
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
