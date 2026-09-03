"""Contracts match SPEC.md section 4 key sets and recorded wire names."""

from __future__ import annotations

import dataclasses
from typing import get_args

import pytest

from vorpal.contracts import (
    IDENTITY_KEYS,
    IDP_SLOTS,
    PAYLOAD_CONFIG_KEYS,
    PAYLOAD_KEYS,
    PROPOSAL_KEYS,
    AdpVariant,
    Banner,
    BetweenTeam,
    BoardRow,
    Draft,
    DraftState,
    EcrRow,
    Flag,
    Gate,
    GateOutcome,
    GateResult,
    Host,
    League,
    LeagueConfig,
    LeagueFormat,
    Need,
    OverrideRow,
    Payload,
    Pick,
    Player,
    Proposal,
    RecentPick,
    Replacement,
    RosterPlayer,
    Seat,
    Slot,
    SlotCounts,
    StatRow,
    User,
    WeeklyCell,
)

# SPEC.md section 4 — In
SPEC_PAYLOAD_KEYS = {"config", "state", "replacement", "hint_argmax_vols", "board"}
SPEC_CONFIG_KEYS = {"teams", "rounds", "slot", "slots", "scoring_summary", "banners"}
SPEC_STATE_REQUIRED = {"pick_no", "user_roster", "needs", "weekly", "recent"}
SPEC_STATE_SEAT = {"next_user_pick", "picks_until_next", "between"}
SPEC_USER_ROSTER_KEYS = {"player_id", "name", "position", "bye"}
SPEC_NEED_KEYS = {"filled", "required"}
SPEC_WEEKLY_KEYS = {"week", "starter_points", "empty"}
SPEC_RECENT_KEYS = {"player_id", "position", "pick_no"}
SPEC_BETWEEN_KEYS = {"slot", "roster", "needs"}
SPEC_REPLACEMENT_KEYS = {"player_id", "points"}
SPEC_BOARD_REQUIRED = {
    "player_id",
    "name",
    "position",
    "points",
    "vols",
    "delta_starter_points",
    "adp",
    "legal_slots",
}
SPEC_BOARD_OPTIONAL = {"bye", "gp", "ecr", "ecr_min", "ecr_max", "ecr_std"}
SPEC_PROPOSAL_KEYS = {
    "player_id",
    "alternatives",
    "slot_filled",
    "coin_flip",
    "why",
    "flags",
}
SPEC_FLAGS = {
    "ECR_DISAGREE",
    "BYE_STACK",
    "POSITION_RUN",
    "EMPTY_STARTER",
    "UPSIDE",
    "VOLS_DISSENT",
}


def _fields(cls: type) -> set[str]:
    return {item.name for item in dataclasses.fields(cls)}


def _board_row(**overrides: object) -> BoardRow:
    values: dict[str, object] = {
        "player_id": "4866",
        "name": "Saquon Barkley",
        "position": "RB",
        "points": 280.0,
        "vols": 40.0,
        "delta_starter_points": 12.0,
        "adp": 1.5,
        "legal_slots": (Slot.RB, Slot.FLEX),
    }
    values.update(overrides)
    return BoardRow(**values)  # type: ignore[arg-type]


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
        scoring={"rec": 1.0, "pass_td": 4.0, "pass_yd": 0.04},
        scoring_summary="PPR, 4pt pass TD",
        banners=(Banner(code="board_capped", message="board is capped"),),
        slot=slot,
        draft_id="draft_snake_redraft",
        league_id="league_snake_redraft",
        scoring_league_id="league_snake_redraft",
        season="2025",
        draft_type="snake",
        status="complete",
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


def _payload(*, with_seat: bool = True, with_optionals: bool = True) -> Payload:
    row = _board_row(
        bye=9 if with_optionals else None,
        gp=16.0 if with_optionals else None,
        ecr=2 if with_optionals else None,
        ecr_min=1 if with_optionals else None,
        ecr_max=8 if with_optionals else None,
        ecr_std=1.4 if with_optionals else None,
    )
    return Payload(
        config=_config(slot=2 if with_seat else None),
        state=_state(with_seat=with_seat),
        replacement={"RB": Replacement(player_id="999", points=120.0)},
        hint_argmax_vols="4866",
        board=(row,),
    )


def test_payload_and_proposal_module_constants_match_spec_section_4() -> None:
    assert PAYLOAD_KEYS == SPEC_PAYLOAD_KEYS
    assert PAYLOAD_CONFIG_KEYS == SPEC_CONFIG_KEYS
    assert PROPOSAL_KEYS == SPEC_PROPOSAL_KEYS


def test_payload_to_dict_key_set_matches_spec_when_seat_is_known() -> None:
    data = _payload(with_seat=True, with_optionals=True).to_dict()
    assert set(data) == SPEC_PAYLOAD_KEYS
    assert set(data["config"]) == SPEC_CONFIG_KEYS
    assert set(data["state"]) == SPEC_STATE_REQUIRED | SPEC_STATE_SEAT
    assert set(data["state"]["user_roster"][0]) == SPEC_USER_ROSTER_KEYS
    assert set(data["state"]["needs"]["RB"]) == SPEC_NEED_KEYS
    assert set(data["state"]["weekly"][0]) == SPEC_WEEKLY_KEYS
    assert set(data["state"]["recent"][0]) == SPEC_RECENT_KEYS
    assert set(data["state"]["between"][0]) == SPEC_BETWEEN_KEYS
    assert set(next(iter(data["replacement"].values()))) == SPEC_REPLACEMENT_KEYS
    assert SPEC_BOARD_REQUIRED <= set(data["board"][0])
    assert SPEC_BOARD_OPTIONAL <= set(data["board"][0])


def test_payload_omits_seat_keys_when_the_seat_is_unknown() -> None:
    data = _payload(with_seat=False, with_optionals=False).to_dict()
    assert set(data["state"]) == SPEC_STATE_REQUIRED
    assert "next_user_pick" not in data["state"]
    assert "picks_until_next" not in data["state"]
    assert "between" not in data["state"]
    board_keys = set(data["board"][0])
    assert board_keys == SPEC_BOARD_REQUIRED
    assert data["config"]["slot"] is None


def test_proposal_to_dict_key_set_matches_spec() -> None:
    proposal = Proposal(
        player_id="4866",
        alternatives=("7564",),
        slot_filled=Slot.RB,
        coin_flip=False,
        why="fills RB",
        flags=(Flag.VOLS_DISSENT, Flag.ECR_DISAGREE),
    )
    data = proposal.to_dict()
    assert set(data) == SPEC_PROPOSAL_KEYS
    assert data["flags"] == ["VOLS_DISSENT", "ECR_DISAGREE"]
    assert data["slot_filled"] == "RB"
    assert data["coin_flip"] is False


def test_flag_enum_is_the_closed_set_from_the_spec() -> None:
    assert {flag.value for flag in Flag} == SPEC_FLAGS


def test_slot_codes_come_from_the_wire_not_the_prose() -> None:
    assert Slot.SUPER_FLEX.value == "SUPER_FLEX"
    assert Slot.DEF.value == "DEF"
    assert Slot.K.value == "K"
    assert Slot.FLEX.value == "FLEX"
    assert Slot.OP.value == "OP"
    assert Slot.BN.value == "BN"
    assert "DST" not in Slot.__members__
    for code in IDP_SLOTS:
        assert Slot(code)
        assert code in {slot.value for slot in Slot}


def test_adp_variant_is_host_agnostic() -> None:
    assert {item.value for item in AdpVariant} == {"2qb", "ppr", "half_ppr", "std"}


def test_types_are_frozen_and_slotted() -> None:
    player = Player(
        player_id="4866",
        host=Host.SLEEPER,
        first_name="Saquon",
        last_name="Barkley",
        name="Saquon Barkley",
        position="RB",
        team="PHI",
        fantasy_positions=("RB",),
        active=True,
        status="Active",
        injury_status=None,
        years_exp=7,
        number=26,
        bye=None,
    )
    assert player.__slots__
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        player.team = "DAL"  # type: ignore[misc]


def test_recorded_boundary_types_expose_host_agnostic_field_names() -> None:
    assert {
        "host",
        "draft_id",
        "type",
        "status",
        "league_id",
        "slot_counts",
        "draft_order",
    } <= _fields(Draft)
    assert {
        "host",
        "league_id",
        "roster_positions",
        "scoring",
        "format",
        "max_keepers",
        "taxi_slots",
    } <= _fields(League)
    assert {"player_id", "host"} <= _fields(Player)
    assert "yahoo_id" not in _fields(Player)
    assert "espn_id" not in _fields(Player)
    assert set(Host) == {Host.SLEEPER, Host.ESPN}
    assert set(LeagueFormat) == {
        LeagueFormat.REDRAFT,
        LeagueFormat.KEEPER,
        LeagueFormat.DYNASTY,
        LeagueFormat.UNKNOWN,
    }
    assert {"user_id", "username", "display_name", "is_bot"} <= _fields(User)
    assert {
        "player_id",
        "picked_by",
        "roster_id",
        "round",
        "draft_slot",
        "pick_no",
        "is_keeper",
    } <= _fields(Pick)
    assert {
        "player_id",
        "host",
        "position",
        "team",
        "bye",
    } <= _fields(Player)
    assert "search_rank" not in _fields(Player)
    assert {"player_id", "source", "week", "stats", "adp", "gp", "market_only"} <= (
        _fields(StatRow)
    )
    assert "adp_ppr" not in _fields(StatRow)
    assert {
        "player_id",
        "name",
        "rank_ecr",
        "rank_min",
        "rank_max",
        "rank_std",
    } <= _fields(EcrRow)
    assert "player_yahoo_id" not in _fields(EcrRow)
    assert {"player_id", "stats", "adp"} <= _fields(OverrideRow)
    assert {"user_id", "slot", "roster_id"} <= _fields(Seat)


def test_identity_keys_are_generic_contract_fields() -> None:
    fields = (
        _fields(User)
        | _fields(Pick)
        | _fields(Player)
        | _fields(LeagueConfig)
        | _fields(Draft)
        | _fields(League)
        | _fields(BoardRow)
        | _fields(RosterPlayer)
        | _fields(Seat)
    )
    assert IDENTITY_KEYS <= fields
    assert "player_id" not in IDENTITY_KEYS


def test_stat_row_can_hold_counting_keys_and_mark_market_only() -> None:
    counting = StatRow(
        player_id="10213",
        source="rotowire",
        week=None,
        season="2026",
        stats={"rec": 46.0, "rec_yd": 582.0, "rec_td": 3.0},
        adp=203.7,
        gp=18.0,
        market_only=False,
    )
    market = StatRow(
        player_id="2",
        source="rotowire",
        week=None,
        season="2026",
        stats={},
        adp=200.0,
        gp=17.0,
        market_only=True,
    )
    assert counting.market_only is False
    assert market.market_only is True
    assert "pts_ppr" not in counting.stats


def test_ecr_row_is_joined_to_a_host_player_id() -> None:
    row = EcrRow(
        player_id="6794",
        name="Justin Jefferson",
        team="MIN",
        position="WR",
        bye=None,
        rank_ecr=1,
        rank_min=1,
        rank_max=4,
        rank_std=0.43,
    )
    assert row.player_id == "6794"
    assert row.rank_ecr == 1


def test_override_row_optional_fields() -> None:
    required = OverrideRow(player_id="4866", stats={"rush_yd": 1400.0}, adp=1.5)
    full = OverrideRow(
        player_id="4866",
        stats={"rush_yd": 1400.0},
        adp=1.5,
        adp_stdev=4.0,
        name="Saquon Barkley",
        team="PHI",
        pos="RB",
    )
    assert required.adp_stdev is None
    assert full.adp_stdev == 4.0


def test_pick_allows_null_keeper_empty_picked_by_and_null_roster() -> None:
    pick = Pick(
        draft_id="draft_mock_standalone",
        player_id="9221",
        picked_by="",
        roster_id=None,
        round=1,
        draft_slot=1,
        pick_no=1,
        is_keeper=None,
        position="RB",
        team="DET",
        first_name="Jahmyr",
        last_name="Gibbs",
    )
    assert pick.roster_id is None
    assert pick.picked_by == ""
    assert pick.is_keeper is None


def test_gate_result_is_binary_or_not_performed() -> None:
    assert {outcome.value for outcome in GateOutcome} == {
        "PASS",
        "FAIL",
        "NOT_PERFORMED",
    }
    assert len(list(Gate)) == 11
    passed = GateResult(gate=Gate.SCHEMA, outcome=GateOutcome.PASS, reason=None)
    failed = GateResult(
        gate=Gate.VOLS_DISSENT, outcome=GateOutcome.FAIL, reason="silent dissent"
    )
    skipped = GateResult(
        gate=Gate.ECR_SANITY, outcome=GateOutcome.NOT_PERFORMED, reason="no ECR"
    )
    assert passed.outcome is GateOutcome.PASS
    assert failed.reason == "silent dissent"
    assert skipped.outcome is GateOutcome.NOT_PERFORMED


def test_seat_roster_id_may_be_null_on_a_standalone_mock() -> None:
    seat = Seat(user_id="user_operator", slot=1, roster_id=None)
    assert seat.roster_id is None
    assert seat.slot == 1


def test_banner_serialises_code_and_message() -> None:
    banner = Banner(code="ecr_missing", message="FantasyPros is down")
    assert banner.to_dict() == {"code": "ecr_missing", "message": "FantasyPros is down"}


def test_draft_and_league_and_user_construct_from_recorded_names() -> None:
    draft = Draft(
        host=Host.SLEEPER,
        draft_id="draft_snake_redraft",
        type="snake",
        status="complete",
        sport="nfl",
        season="2025",
        season_type="regular",
        league_id="league_snake_redraft",
        start_time=1756858531257,
        teams=12,
        rounds=15,
        pick_timer=60,
        reversal_round=0,
        slot_counts=SlotCounts(k=1, defense=1, bn=5),
        scoring_label="ppr",
        draft_order={"user_operator": 2},
        slot_to_roster_id={1: 2},
    )
    league = League(
        host=Host.SLEEPER,
        league_id="league_snake_redraft",
        draft_id="draft_snake_redraft",
        season="2025",
        status="complete",
        sport="nfl",
        season_type="regular",
        total_rosters=12,
        roster_positions=(Slot.QB, Slot.RB, Slot.K, Slot.DEF, Slot.BN),
        scoring={"rec": 1.0},
        format=LeagueFormat.REDRAFT,
        max_keepers=1,
        taxi_slots=0,
        num_teams=12,
    )
    user = User(
        user_id="user_operator",
        username="operator",
        display_name="Operator",
        is_bot=False,
    )
    assert draft.league_id == league.league_id
    assert user.user_id == "user_operator"
    assert Slot.DEF in league.roster_positions


def test_weekly_cell_and_replacement_and_board_row_optionals() -> None:
    cell = WeeklyCell(week=1, starter_points=20.0, empty=())
    assert cell.empty == ()
    replacement = Replacement(player_id="x", points=100.0)
    assert replacement.points == 100.0
    row = _board_row(bye=None, gp=None)
    assert row.bye is None
    assert row.ecr is None


def test_get_args_slot_union_covers_idp_for_typing_callers() -> None:
    # Keep a runtime assertion that IDP codes stay on the enum.
    assert get_args(str) == ()
    assert Slot.DL in Slot
    assert Slot.LB in Slot
    assert Slot.DB in Slot
    assert Slot.IDP_FLEX in Slot
