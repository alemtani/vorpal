"""Board states to run the gates against.

A gate needs a board to judge. This builds them two ways.

`sample_adp_order` and friends fake a draft: players come off the board
in average-draft-position order with some noise, because that is roughly
how a real room drafts. Stop after N picks and you have a plausible board
at pick N. Vary the noise and you get many of them.

`hostile_states` is the opposite — five boards hand-built to be awkward.
An empty starter slot in the last rounds, a roster stacking one bye week,
a run on a position, a board where every VOLS is within a point, and a
draft where we do not know which seat is ours. These are the situations
where a policy that looks fine on average falls over.

Nothing here samples from the model. A test set the model helped write
cannot measure the model.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from vorpal.contracts import (
    Banner,
    BoardRow,
    DraftState,
    LeagueConfig,
    Need,
    Payload,
    RecentPick,
    Replacement,
    RosterPlayer,
    Slot,
)

_SLOTS: tuple[Slot, ...] = (
    Slot.QB,
    Slot.RB,
    Slot.RB,
    Slot.WR,
    Slot.WR,
    Slot.TE,
    Slot.FLEX,
    Slot.K,
    Slot.DEF,
    Slot.BN,
)


def sample_adp_order(
    rows: Sequence[BoardRow],
    *,
    noise: float,
    rng: random.Random,
) -> tuple[BoardRow, ...]:
    """Sort by ADP plus Gaussian noise. `noise` is the stdev in ADP units.

    Tie-break is player_id. `noise=0` is exact ADP order. Never samples
    from a model.
    """
    keyed = [
        (row.adp + (rng.gauss(0.0, noise) if noise else 0.0), row.player_id, row)
        for row in rows
    ]
    keyed.sort()
    return tuple(item[2] for item in keyed)


def remaining_board(
    rows: Sequence[BoardRow],
    order: Sequence[BoardRow],
    n_picked: int,
) -> tuple[BoardRow, ...]:
    """Rows still on the board after the first `n_picked` of `order`."""
    taken = {row.player_id for row in order[:n_picked]}
    return tuple(row for row in rows if row.player_id not in taken)


def sample_board_states(
    rows: Sequence[BoardRow],
    *,
    noise: float,
    rng: random.Random,
    n_picks: int,
) -> tuple[tuple[BoardRow, ...], ...]:
    """Successive remaining boards after ADP-order-plus-noise picks."""
    order = sample_adp_order(rows, noise=noise, rng=rng)
    return tuple(remaining_board(rows, order, n) for n in range(n_picks + 1))


def hostile_states() -> dict[str, Payload]:
    """Hostile boards: empty starter, bye stack, run, compressed VOLS, unknown seat."""
    return {
        "empty_starter_late": _empty_starter_late(),
        "bye_stack": _bye_stack(),
        "position_run": _position_run(),
        "vols_compressed": _vols_compressed(),
        "seat_unknown": _seat_unknown(),
    }


def _empty_starter_late() -> Payload:
    return _payload(
        pick_no=160,
        needs={
            "QB": Need(filled=1, required=1),
            "RB": Need(filled=2, required=2),
            "WR": Need(filled=2, required=2),
            "TE": Need(filled=0, required=1),
            "FLEX": Need(filled=1, required=1),
            "K": Need(filled=1, required=1),
            "DEF": Need(filled=1, required=1),
        },
        roster=(
            RosterPlayer(player_id="held-rb", name="held-rb", position="RB", bye=7),
        ),
    )


def _bye_stack() -> Payload:
    roster = (
        RosterPlayer(player_id="held-rb", name="held-rb", position="RB", bye=9),
        RosterPlayer(player_id="held-wr", name="held-wr", position="WR", bye=9),
    )
    board = (
        _row("rb-stack", position="RB", vols=20.0, adp=40.0, ecr=25, bye=9),
        _row("wr-stack", position="WR", vols=18.0, adp=42.0, ecr=28, bye=9),
        _row("te-other", position="TE", vols=10.0, adp=60.0, ecr=40, bye=12),
    )
    return _payload(roster=roster, board=board, hint="rb-stack")


def _position_run() -> Payload:
    recent = tuple(
        RecentPick(player_id=f"wr-taken-{i}", position="WR", pick_no=20 + i)
        for i in range(5)
    )
    return _payload(recent=recent, pick_no=25)


def _vols_compressed() -> Payload:
    board = (
        _row("a", position="RB", vols=1.0, adp=80.0, ecr=70, bye=6),
        _row("b", position="WR", vols=0.6, adp=82.0, ecr=74, bye=7),
        _row("c", position="TE", vols=0.2, adp=90.0, ecr=80, bye=8),
        _row("d", position="RB", vols=0.0, adp=95.0, ecr=88, bye=9),
    )
    return _payload(board=board, hint="a", pick_no=120)


def _seat_unknown() -> Payload:
    config = _config(slot=None)
    state = DraftState(
        pick_no=24,
        user_roster=(),
        needs={"RB": Need(filled=0, required=2)},
        weekly=(),
        recent=(),
        next_user_pick=None,
        picks_until_next=None,
        between=None,
    )
    return Payload(
        config=config,
        state=state,
        replacement={"RB": Replacement(player_id="repl", points=100.0)},
        hint_argmax_vols="rb1",
        board=_default_board(),
    )


def _payload(
    *,
    pick_no: int = 24,
    needs: dict[str, Need] | None = None,
    roster: tuple[RosterPlayer, ...] = (),
    board: tuple[BoardRow, ...] | None = None,
    hint: str = "rb1",
    recent: tuple[RecentPick, ...] = (),
    slot: int | None = 4,
) -> Payload:
    if needs is None:
        needs = {"TE": Need(filled=0, required=1), "RB": Need(filled=1, required=2)}
    if board is None:
        board = _default_board()
    return Payload(
        config=_config(slot=slot),
        state=DraftState(
            pick_no=pick_no,
            user_roster=roster,
            needs=needs,
            weekly=(),
            recent=recent,
            next_user_pick=pick_no + 1 if slot is not None else None,
            picks_until_next=1 if slot is not None else None,
            between=None,
        ),
        replacement={"RB": Replacement(player_id="repl", points=100.0)},
        hint_argmax_vols=hint,
        board=board,
    )


def _config(*, slot: int | None = 4) -> LeagueConfig:
    return LeagueConfig(
        teams=12,
        rounds=15,
        slots=_SLOTS,
        scoring={"rec": 1.0},
        scoring_summary="PPR",
        banners=(Banner(code="board_capped", message="board is capped"),),
        slot=slot,
        draft_id="draft_eval",
        status="drafting",
    )


def _default_board() -> tuple[BoardRow, ...]:
    return (
        _row("rb1", position="RB", vols=80.0, adp=1.5, ecr=1, bye=9),
        _row("wr1", position="WR", vols=60.0, adp=3.0, ecr=5, bye=5),
        _row("te1", position="TE", vols=25.0, adp=40.0, ecr=30, bye=12),
    )


def _row(
    player_id: str,
    *,
    position: str,
    vols: float,
    adp: float,
    ecr: int,
    bye: int,
) -> BoardRow:
    legal: dict[str, tuple[Slot, ...]] = {
        "RB": (Slot.RB, Slot.FLEX, Slot.BN),
        "WR": (Slot.WR, Slot.FLEX, Slot.BN),
        "TE": (Slot.TE, Slot.FLEX, Slot.BN),
        "QB": (Slot.QB, Slot.SUPER_FLEX, Slot.BN),
        "K": (Slot.K, Slot.BN),
        "DEF": (Slot.DEF, Slot.BN),
    }
    return BoardRow(
        player_id=player_id,
        name=player_id,
        position=position,
        points=100.0 + vols,
        vols=vols,
        delta_starter_points=vols / 2.0,
        adp=adp,
        legal_slots=legal.get(position, (Slot.BN,)),
        bye=bye,
        ecr=ecr,
        ecr_min=ecr,
        ecr_max=ecr + 5,
        ecr_std=1.0,
    )
