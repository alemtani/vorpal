"""Payload serialises to SPEC.md section 4. Seat is omitted, never guessed."""

from __future__ import annotations

from dataclasses import replace

import pytest

from vorpal.contracts import (
    PAYLOAD_CONFIG_KEYS,
    PAYLOAD_KEYS,
    AdpVariant,
    Banner,
    BetweenTeam,
    BoardRow,
    DraftState,
    LeagueConfig,
    Need,
    RecentPick,
    Replacement,
    RosterPlayer,
    Slot,
    WeeklyCell,
)
from vorpal.errors import DataRefusal
from vorpal.payload import BOARD_CAPPED, build_payload


def _row(
    player_id: str,
    *,
    name: str | None = None,
    position: str = "RB",
    vols: float,
    adp: float,
    ecr: int | None = None,
) -> BoardRow:
    slots = (Slot.RB, Slot.FLEX) if position == "RB" else (Slot[position],)
    return BoardRow(
        player_id=player_id,
        name=name or player_id,
        position=position,
        points=vols + 100.0,
        vols=vols,
        delta_starter_points=1.0,
        adp=adp,
        legal_slots=slots,
        bye=9,
        gp=17.0,
        ecr=ecr,
    )


def _config(*, slot: int | None = 2) -> LeagueConfig:
    return LeagueConfig(
        teams=12,
        rounds=15,
        slots=(
            Slot.QB,
            Slot.RB,
            Slot.WR,
            Slot.TE,
            Slot.FLEX,
            Slot.K,
            Slot.DEF,
            Slot.BN,
        ),
        scoring={"rec": 1.0},
        scoring_summary="PPR",
        banners=(Banner(code="keepers_possible", message="keepers possible"),),
        slot=slot,
        draft_id="draft_snake_redraft",
        league_id="league_snake_redraft",
        scoring_league_id="league_snake_redraft",
        season="2025",
        draft_type="snake",
        status="drafting",
        pick_timer=60,
        reversal_round=0,
        adp_variant=AdpVariant.PPR,
        ecr_scoring="PPR",
    )


def _state(*, with_seat: bool = True) -> DraftState:
    need = Need(filled=1, required=2)
    return DraftState(
        pick_no=48,
        user_roster=(
            RosterPlayer(player_id="4866", name="Saquon Barkley", position="RB", bye=9),
        ),
        needs={"RB": need},
        weekly=(WeeklyCell(week=9, starter_points=0.0, empty=(Slot.RB,)),),
        recent=(RecentPick(player_id="7564", position="WR", pick_no=47),),
        next_user_pick=49 if with_seat else None,
        picks_until_next=1 if with_seat else None,
        between=(BetweenTeam(slot=3, roster={"RB": 1}, needs={"RB": need}),)
        if with_seat
        else None,
    )


def _replacement() -> dict[str, Replacement]:
    return {"RB": Replacement(player_id="999", points=120.0)}


def _rows() -> tuple[BoardRow, BoardRow]:
    return (
        _row("4866", name="Saquon Barkley", vols=40.0, adp=1.5, ecr=1),
        _row("7564", name="Amon-Ra St. Brown", position="WR", vols=30.0, adp=8.0),
    )


def test_to_dict_key_set_matches_the_s0_contracts_constants() -> None:
    payload = build_payload(_config(), _state(), _replacement(), _rows())
    data = payload.to_dict()
    assert set(data) == PAYLOAD_KEYS
    assert set(data["config"]) == PAYLOAD_CONFIG_KEYS


def test_board_capped_banner_is_always_stated() -> None:
    payload = build_payload(_config(), _state(), _replacement(), _rows())
    codes = [banner.code for banner in payload.config.banners]
    assert BOARD_CAPPED.code in codes
    data = payload.to_dict()
    banner_codes = [item["code"] for item in data["config"]["banners"]]
    assert "board_capped" in banner_codes
    assert any("capped" in item["message"] for item in data["config"]["banners"])


def test_existing_banners_are_kept_when_the_cap_banner_is_added() -> None:
    payload = build_payload(_config(), _state(), _replacement(), _rows())
    codes = [banner.code for banner in payload.config.banners]
    assert "keepers_possible" in codes
    assert codes.count("board_capped") == 1


def test_hint_argmax_vols_is_the_calculator_max_on_the_capped_board() -> None:
    payload = build_payload(_config(), _state(), _replacement(), _rows())
    assert payload.hint_argmax_vols == "4866"
    assert payload.to_dict()["hint_argmax_vols"] == "4866"


def test_unknown_seat_omits_next_user_pick_picks_until_next_and_between() -> None:
    leaked = replace(
        _state(with_seat=False),
        next_user_pick=49,
        picks_until_next=1,
        between=_state(with_seat=True).between,
    )
    payload = build_payload(_config(slot=None), leaked, _replacement(), _rows())
    data = payload.to_dict()
    assert "next_user_pick" not in data["state"]
    assert "picks_until_next" not in data["state"]
    assert "between" not in data["state"]
    assert data["config"]["slot"] is None
    assert payload.state.next_user_pick is None
    assert payload.state.picks_until_next is None
    assert payload.state.between is None


def test_known_seat_keeps_next_user_pick_picks_until_next_and_between() -> None:
    payload = build_payload(
        _config(slot=2), _state(with_seat=True), _replacement(), _rows()
    )
    data = payload.to_dict()
    assert data["state"]["next_user_pick"] == 49
    assert data["state"]["picks_until_next"] == 1
    assert data["state"]["between"][0]["slot"] == 3


def test_payload_does_not_ship_a_survival_band() -> None:
    payload = build_payload(_config(), _state(), _replacement(), _rows())
    data = payload.to_dict()
    blob = str(data)
    for forbidden in ("survival", "sigma", "σ", "adp_stdev"):
        assert forbidden not in blob
    for row in data["board"]:
        assert "survival" not in row
        assert "band" not in row


def test_board_is_the_capped_ordered_list() -> None:
    high = _row("high", vols=50.0, adp=200.0)
    low = _row("low", vols=1.0, adp=200.0)
    payload = build_payload(_config(), _state(), _replacement(), (low, high))
    assert [row.player_id for row in payload.board] == ["high", "low"]


def test_empty_board_is_a_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="no players"):
        build_payload(_config(), _state(), _replacement(), ())


def test_cap_banner_is_not_duplicated_when_already_present() -> None:
    cfg = replace(_config(), banners=(BOARD_CAPPED, Banner(code="x", message="x")))
    payload = build_payload(cfg, _state(), _replacement(), _rows())
    codes = [banner.code for banner in payload.config.banners]
    assert codes.count("board_capped") == 1
