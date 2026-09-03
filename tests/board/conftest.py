"""Builders injected as fixtures so tests do not need the `tests` package."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from vorpal.contracts import (
    AdpVariant,
    Banner,
    BoardRow,
    Draft,
    DraftState,
    Flag,
    Host,
    LeagueConfig,
    Need,
    Payload,
    Pick,
    Proposal,
    RecentPick,
    Replacement,
    RosterPlayer,
    Slot,
    SlotCounts,
    WeeklyCell,
)


def _make_draft(
    *,
    status: str = "drafting",
    pick_timer: int | None = 60,
    draft_id: str = "draft_test",
) -> Draft:
    return Draft(
        host=Host.SLEEPER,
        draft_id=draft_id,
        type="snake",
        status=status,
        sport="nfl",
        season="2025",
        season_type="regular",
        league_id="league_test",
        start_time=None,
        teams=12,
        rounds=15,
        pick_timer=pick_timer,
        reversal_round=0,
        slot_counts=SlotCounts(qb=1, rb=2, wr=2, te=1, k=1, defense=1, flex=1, bn=5),
        scoring_label="ppr",
        draft_order={"user_operator": 2},
        slot_to_roster_id={1: 2, 2: 1},
    )


def _make_pick(*, pick_no: int = 1, player_id: str = "p1", draft_slot: int = 2) -> Pick:
    return Pick(
        draft_id="draft_test",
        player_id=player_id,
        picked_by="user_operator",
        roster_id=1,
        round=1,
        draft_slot=draft_slot,
        pick_no=pick_no,
        is_keeper=None,
        position="RB",
        team="PHI",
        first_name="A",
        last_name="Back",
    )


def _make_weekly() -> tuple[WeeklyCell, ...]:
    cells: list[WeeklyCell] = []
    for week in range(1, 19):
        if week == 9:
            cells.append(
                WeeklyCell(week=9, starter_points=0.0, empty=(Slot.RB, Slot.FLEX))
            )
        else:
            cells.append(WeeklyCell(week=week, starter_points=80.0 + week, empty=()))
    return tuple(cells)


def _make_row(
    *,
    player_id: str,
    name: str,
    position: str = "RB",
    points: float = 200.0,
    vols: float = 40.0,
    delta_starter_points: float = 12.0,
    adp: float = 8.0,
    legal_slots: tuple[Slot, ...] = (Slot.RB, Slot.FLEX),
    bye: int | None = 9,
    gp: float | None = None,
    ecr: int | None = 5,
) -> BoardRow:
    return BoardRow(
        player_id=player_id,
        name=name,
        position=position,
        points=points,
        vols=vols,
        delta_starter_points=delta_starter_points,
        adp=adp,
        legal_slots=legal_slots,
        bye=bye,
        gp=gp,
        ecr=ecr,
        ecr_min=ecr,
        ecr_max=None if ecr is None else ecr + 4,
        ecr_std=None if ecr is None else 1.2,
    )


def _make_config(
    *,
    status: str = "drafting",
    pick_timer: int | None = 60,
    banners: tuple[Banner, ...] = (
        Banner(code="board_capped", message="board is capped"),
    ),
    slot: int | None = 2,
) -> LeagueConfig:
    return LeagueConfig(
        teams=12,
        rounds=15,
        slots=(
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
        ),
        scoring={"rec": 1.0, "pass_td": 4.0},
        scoring_summary="PPR, 4pt pass TD",
        banners=banners,
        slot=slot,
        draft_id="draft_test",
        league_id="league_test",
        scoring_league_id="league_test",
        season="2025",
        draft_type="snake",
        status=status,
        pick_timer=pick_timer,
        reversal_round=0,
        adp_variant=AdpVariant.PPR,
        ecr_scoring="PPR",
    )


def _make_payload(
    *,
    status: str = "drafting",
    pick_timer: int | None = 60,
    config_banners: tuple[Banner, ...] | None = None,
    board: tuple[BoardRow, ...] | None = None,
    weekly: tuple[WeeklyCell, ...] | None = None,
    slot: int | None = 2,
    pick_no: int = 48,
    next_user_pick: int | None = 49,
    picks_until_next: int | None = 1,
) -> Payload:
    rows = board or (
        _make_row(
            player_id="p1",
            name="A Back",
            vols=40.0,
            delta_starter_points=12.0,
            points=280.0,
            gp=16.0,
            adp=1.5,
        ),
        _make_row(
            player_id="p2",
            name="B Receiver",
            position="WR",
            vols=30.0,
            delta_starter_points=8.0,
            points=240.0,
            gp=17.0,
            adp=12.0,
            legal_slots=(Slot.WR, Slot.FLEX),
            bye=6,
        ),
        _make_row(
            player_id="p3",
            name="C Tight",
            position="TE",
            vols=10.0,
            delta_starter_points=3.0,
            points=140.0,
            gp=None,
            adp=40.0,
            legal_slots=(Slot.TE, Slot.FLEX),
            bye=10,
            ecr=None,
        ),
    )
    banners = (
        (Banner(code="board_capped", message="board is capped"),)
        if config_banners is None
        else config_banners
    )
    need = Need(filled=1, required=2)
    return Payload(
        config=_make_config(
            status=status, pick_timer=pick_timer, banners=banners, slot=slot
        ),
        state=DraftState(
            pick_no=pick_no,
            user_roster=(
                RosterPlayer(player_id="p0", name="Held Back", position="RB", bye=9),
            ),
            needs={"RB": need, "FLEX": Need(filled=0, required=1)},
            weekly=weekly if weekly is not None else _make_weekly(),
            recent=(RecentPick(player_id="px", position="WR", pick_no=47),),
            next_user_pick=next_user_pick,
            picks_until_next=picks_until_next,
            between=None,
        ),
        replacement={"RB": Replacement(player_id="rep", points=120.0)},
        hint_argmax_vols="p1",
        board=rows,
    )


def _make_proposal(
    *,
    player_id: str = "p1",
    alternatives: tuple[str, ...] = ("p2",),
    slot_filled: Slot = Slot.RB,
    coin_flip: bool = False,
    why: str = "fills the empty RB and beats replacement",
    flags: tuple[Flag, ...] = (Flag.VOLS_DISSENT, Flag.BYE_STACK),
) -> Proposal:
    return Proposal(
        player_id=player_id,
        alternatives=alternatives,
        slot_filled=slot_filled,
        coin_flip=coin_flip,
        why=why,
        flags=flags,
    )


@pytest.fixture
def make_draft() -> Callable[..., Draft]:
    return _make_draft


@pytest.fixture
def make_pick() -> Callable[..., Pick]:
    return _make_pick


@pytest.fixture
def make_row() -> Callable[..., BoardRow]:
    return _make_row


@pytest.fixture
def make_payload() -> Callable[..., Payload]:
    return _make_payload


@pytest.fixture
def make_proposal() -> Callable[..., Proposal]:
    return _make_proposal
