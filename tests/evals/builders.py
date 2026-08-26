"""Builders for eval fixtures. Synthetic boards only — no host ids from a league."""

from __future__ import annotations

from vorpal.contracts import (
    Banner,
    BoardRow,
    DraftState,
    Flag,
    LeagueConfig,
    Need,
    Payload,
    Proposal,
    RecentPick,
    Replacement,
    RosterPlayer,
    Slot,
    WeeklyCell,
)


def board_row(
    player_id: str,
    *,
    name: str | None = None,
    position: str = "RB",
    points: float = 200.0,
    vols: float = 40.0,
    delta_starter_points: float = 10.0,
    adp: float = 20.0,
    legal_slots: tuple[Slot, ...] | None = None,
    bye: int | None = 9,
    gp: float | None = 17.0,
    ecr: int | None = 10,
    ecr_min: int | None = 8,
    ecr_max: int | None = 20,
    ecr_std: float | None = 2.0,
) -> BoardRow:
    if legal_slots is None:
        legal_slots = _default_legal_slots(position)
    return BoardRow(
        player_id=player_id,
        name=name or player_id,
        position=position,
        points=points,
        vols=vols,
        delta_starter_points=delta_starter_points,
        adp=adp,
        legal_slots=legal_slots,
        bye=bye,
        gp=gp,
        ecr=ecr,
        ecr_min=ecr_min,
        ecr_max=ecr_max,
        ecr_std=ecr_std,
    )


def _default_legal_slots(position: str) -> tuple[Slot, ...]:
    table: dict[str, tuple[Slot, ...]] = {
        "QB": (Slot.QB, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
        "RB": (Slot.RB, Slot.FLEX, Slot.WRRB_FLEX, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
        "WR": (
            Slot.WR,
            Slot.FLEX,
            Slot.WRRB_FLEX,
            Slot.REC_FLEX,
            Slot.SUPER_FLEX,
            Slot.OP,
            Slot.BN,
        ),
        "TE": (Slot.TE, Slot.FLEX, Slot.REC_FLEX, Slot.SUPER_FLEX, Slot.OP, Slot.BN),
        "K": (Slot.K, Slot.BN),
        "DEF": (Slot.DEF, Slot.BN),
    }
    return table.get(position, (Slot.BN,))


def make_config(
    *,
    teams: int = 12,
    rounds: int = 15,
    slot: int | None = 4,
    slots: tuple[Slot, ...] | None = None,
) -> LeagueConfig:
    if slots is None:
        slots = (
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
    return LeagueConfig(
        teams=teams,
        rounds=rounds,
        slots=slots,
        scoring={"rec": 1.0, "pass_td": 4.0},
        scoring_summary="PPR, 4pt pass TD",
        banners=(Banner(code="board_capped", message="board is capped"),),
        slot=slot,
        draft_id="draft_eval",
        league_id=None,
        season="2025",
        draft_type="snake",
        status="drafting",
        pick_timer=60,
        reversal_round=0,
    )


def make_state(
    *,
    pick_no: int = 24,
    user_roster: tuple[RosterPlayer, ...] = (),
    needs: dict[str, Need] | None = None,
    weekly: tuple[WeeklyCell, ...] = (),
    recent: tuple[RecentPick, ...] = (),
    next_user_pick: int | None = 25,
    picks_until_next: int | None = 1,
) -> DraftState:
    if needs is None:
        needs = {
            "QB": Need(filled=0, required=1),
            "RB": Need(filled=1, required=2),
            "WR": Need(filled=0, required=2),
            "TE": Need(filled=0, required=1),
            "FLEX": Need(filled=0, required=1),
            "K": Need(filled=0, required=1),
            "DEF": Need(filled=0, required=1),
        }
    return DraftState(
        pick_no=pick_no,
        user_roster=user_roster,
        needs=needs,
        weekly=weekly,
        recent=recent,
        next_user_pick=next_user_pick,
        picks_until_next=picks_until_next,
        between=None,
    )


def default_board() -> tuple[BoardRow, ...]:
    """Hint is rb1. Lowest ADP is rb1. Best ECR is rb1. A kicker sits last."""
    return (
        board_row(
            "rb1",
            position="RB",
            points=280.0,
            vols=80.0,
            adp=1.5,
            ecr=1,
            ecr_min=1,
            ecr_max=4,
            bye=9,
        ),
        board_row(
            "wr1",
            position="WR",
            points=250.0,
            vols=60.0,
            adp=3.0,
            ecr=5,
            ecr_min=2,
            ecr_max=9,
            bye=5,
        ),
        board_row(
            "rb2",
            position="RB",
            points=220.0,
            vols=40.0,
            adp=8.0,
            ecr=12,
            ecr_min=8,
            ecr_max=18,
            bye=9,
        ),
        board_row(
            "te1",
            position="TE",
            points=180.0,
            vols=25.0,
            adp=40.0,
            ecr=30,
            ecr_min=20,
            ecr_max=45,
            bye=12,
        ),
        board_row(
            "k1",
            position="K",
            points=120.0,
            vols=5.0,
            adp=140.0,
            ecr=200,
            ecr_min=150,
            ecr_max=220,
            bye=14,
        ),
    )


def make_payload(
    *,
    board: tuple[BoardRow, ...] | None = None,
    hint_argmax_vols: str = "rb1",
    config: LeagueConfig | None = None,
    state: DraftState | None = None,
    replacement: dict[str, Replacement] | None = None,
) -> Payload:
    if board is None:
        board = default_board()
    if config is None:
        config = make_config()
    if state is None:
        state = make_state(
            user_roster=(
                RosterPlayer(player_id="rb0", name="held-rb", position="RB", bye=7),
            )
        )
    if replacement is None:
        replacement = {"RB": Replacement(player_id="rb-repl", points=140.0)}
    return Payload(
        config=config,
        state=state,
        replacement=replacement,
        hint_argmax_vols=hint_argmax_vols,
        board=board,
    )


def make_proposal(
    player_id: str = "rb1",
    *,
    alternatives: tuple[str, ...] = ("wr1",),
    slot_filled: Slot = Slot.RB,
    coin_flip: bool = False,
    why: str = "test",
    flags: tuple[Flag, ...] = (),
) -> Proposal:
    return Proposal(
        player_id=player_id,
        alternatives=alternatives,
        slot_filled=slot_filled,
        coin_flip=coin_flip,
        why=why,
        flags=flags,
    )
