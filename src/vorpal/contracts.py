"""Module-boundary types. Field names come from recorded fixtures and SPEC.md §4."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Host(StrEnum):
    """League platform. v1 implements Sleeper; ESPN is a later adapter."""

    SLEEPER = "sleeper"
    ESPN = "espn"


class LeagueFormat(StrEnum):
    """Scoring-league format. Adapters map host-specific codes onto this."""

    REDRAFT = "redraft"
    KEEPER = "keeper"
    DYNASTY = "dynasty"
    UNKNOWN = "unknown"


class AdpVariant(StrEnum):
    """Which ADP board to read. Hosts map this onto their wire keys."""

    TWO_QB = "2qb"
    PPR = "ppr"
    HALF_PPR = "half_ppr"
    STD = "std"


class Slot(StrEnum):
    """Canonical slot codes. Adapters map host wire (`DEF`, `D/ST`) onto these."""

    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"
    FLEX = "FLEX"
    SUPER_FLEX = "SUPER_FLEX"
    OP = "OP"
    BN = "BN"
    WRRB_FLEX = "WRRB_FLEX"
    REC_FLEX = "REC_FLEX"
    DL = "DL"
    LB = "LB"
    DB = "DB"
    IDP_FLEX = "IDP_FLEX"


class Flag(StrEnum):
    ECR_DISAGREE = "ECR_DISAGREE"
    BYE_STACK = "BYE_STACK"
    POSITION_RUN = "POSITION_RUN"
    EMPTY_STARTER = "EMPTY_STARTER"
    UPSIDE = "UPSIDE"
    VOLS_DISSENT = "VOLS_DISSENT"


class Gate(StrEnum):
    SCHEMA = "schema"
    GOLDEN_FORBID = "golden_forbid"
    GOLDEN_REQUIRE = "golden_require"
    VOLS_DISSENT = "vols_dissent"
    ECR_DISSENT = "ecr_dissent"
    ECR_SANITY = "ecr_sanity"
    BYE_HOLE = "bye_hole"
    STABILITY = "stability"
    VOLS_INVARIANT = "vols_invariant"
    REGRET = "regret"
    REPLAY = "replay"


class GateOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_PERFORMED = "NOT_PERFORMED"


IDP_SLOTS: tuple[str, ...] = (
    Slot.DL.value,
    Slot.LB.value,
    Slot.DB.value,
    Slot.IDP_FLEX.value,
)
PAYLOAD_KEYS = {"config", "state", "replacement", "hint_argmax_vols", "board"}
PAYLOAD_CONFIG_KEYS = {"teams", "rounds", "slot", "slots", "scoring_summary", "banners"}
PROPOSAL_KEYS = {
    "player_id",
    "alternatives",
    "slot_filled",
    "coin_flip",
    "why",
    "flags",
}


@dataclass(frozen=True, slots=True)
class Banner:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class Seat:
    user_id: str
    slot: int
    roster_id: int | None


@dataclass(frozen=True, slots=True)
class User:
    user_id: str
    username: str
    display_name: str
    is_bot: bool


@dataclass(frozen=True, slots=True)
class Player:
    """Host-native id plus which league host it belongs to."""

    player_id: str
    host: Host
    first_name: str
    last_name: str
    name: str
    position: str
    team: str | None
    fantasy_positions: tuple[str, ...]
    active: bool | None
    status: str | None
    injury_status: str | None
    years_exp: int | None
    number: int | None
    bye: int | None


@dataclass(frozen=True, slots=True)
class StatRow:
    player_id: str
    source: str
    week: int | None
    season: str
    stats: dict[str, float]
    adp: float | None
    gp: float | None
    market_only: bool


@dataclass(frozen=True, slots=True)
class EcrRow:
    """Ranks after join to a host player id. Yahoo ids stay on the FP JSON."""

    player_id: str
    name: str
    team: str | None
    position: str
    bye: int | None
    rank_ecr: int
    rank_min: int
    rank_max: int
    rank_std: float


@dataclass(frozen=True, slots=True)
class OverrideRow:
    player_id: str
    stats: dict[str, float]
    adp: float
    adp_stdev: float | None = None
    name: str | None = None
    team: str | None = None
    pos: str | None = None


@dataclass(frozen=True, slots=True)
class Pick:
    draft_id: str
    player_id: str
    picked_by: str
    roster_id: int | None
    round: int
    draft_slot: int
    pick_no: int
    is_keeper: bool | None
    position: str | None
    team: str | None
    first_name: str | None
    last_name: str | None


@dataclass(frozen=True, slots=True)
class SlotCounts:
    """Starter and bench counts. `bn` is None when the host omitted it."""

    qb: int = 0
    rb: int = 0
    wr: int = 0
    te: int = 0
    k: int = 0
    defense: int = 0
    flex: int = 0
    super_flex: int = 0
    op: int = 0
    bn: int | None = None


@dataclass(frozen=True, slots=True)
class Draft:
    """Host-agnostic draft. A LeagueHost adapter fills this from wire JSON."""

    host: Host
    draft_id: str
    type: str
    status: str
    sport: str
    season: str
    season_type: str
    league_id: str | None
    start_time: int | None
    teams: int
    rounds: int
    pick_timer: int | None
    reversal_round: int
    slot_counts: SlotCounts
    scoring_label: str | None
    draft_order: dict[str, int] | None
    slot_to_roster_id: dict[int, int]


@dataclass(frozen=True, slots=True)
class League:
    """Host-agnostic league. Scoring and roster slots are already tables."""

    host: Host
    league_id: str
    draft_id: str
    season: str
    status: str
    sport: str
    season_type: str
    total_rosters: int
    roster_positions: tuple[Slot, ...]
    scoring: dict[str, float]
    format: LeagueFormat
    max_keepers: int
    taxi_slots: int
    num_teams: int


@dataclass(frozen=True, slots=True)
class LeagueConfig:
    teams: int
    rounds: int
    slots: tuple[Slot, ...]
    scoring: dict[str, float]
    scoring_summary: str
    banners: tuple[Banner, ...]
    slot: int | None = None
    draft_id: str = ""
    league_id: str | None = None
    scoring_league_id: str | None = None
    season: str = ""
    draft_type: str = "snake"
    status: str = "pre_draft"
    pick_timer: int | None = None
    reversal_round: int = 0
    adp_variant: AdpVariant = AdpVariant.PPR
    ecr_scoring: str = "PPR"


@dataclass(frozen=True, slots=True)
class Need:
    filled: int
    required: int


@dataclass(frozen=True, slots=True)
class RosterPlayer:
    player_id: str
    name: str
    position: str
    bye: int | None


@dataclass(frozen=True, slots=True)
class WeeklyCell:
    week: int
    starter_points: float
    empty: tuple[Slot, ...]


@dataclass(frozen=True, slots=True)
class RecentPick:
    player_id: str
    position: str
    pick_no: int


@dataclass(frozen=True, slots=True)
class BetweenTeam:
    slot: int
    roster: dict[str, int]
    needs: dict[str, Need]


@dataclass(frozen=True, slots=True)
class DraftState:
    pick_no: int
    user_roster: tuple[RosterPlayer, ...]
    needs: dict[str, Need]
    weekly: tuple[WeeklyCell, ...]
    recent: tuple[RecentPick, ...]
    next_user_pick: int | None = None
    picks_until_next: int | None = None
    between: tuple[BetweenTeam, ...] | None = None


@dataclass(frozen=True, slots=True)
class Replacement:
    player_id: str
    points: float


@dataclass(frozen=True, slots=True)
class BoardRow:
    player_id: str
    name: str
    position: str
    points: float
    vols: float
    delta_starter_points: float
    adp: float
    legal_slots: tuple[Slot, ...]
    bye: int | None = None
    gp: float | None = None
    ecr: int | None = None
    ecr_min: int | None = None
    ecr_max: int | None = None
    ecr_std: float | None = None


@dataclass(frozen=True, slots=True)
class GateResult:
    gate: Gate
    outcome: GateOutcome
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Payload:
    config: LeagueConfig
    state: DraftState
    replacement: dict[str, Replacement]
    hint_argmax_vols: str
    board: tuple[BoardRow, ...]

    def to_dict(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "teams": self.config.teams,
            "rounds": self.config.rounds,
            "slot": self.config.slot,
            "slots": [slot.value for slot in self.config.slots],
            "scoring_summary": self.config.scoring_summary,
            "banners": [banner.to_dict() for banner in self.config.banners],
        }
        state: dict[str, Any] = {
            "pick_no": self.state.pick_no,
            "user_roster": [
                {
                    "player_id": player.player_id,
                    "name": player.name,
                    "position": player.position,
                    "bye": player.bye,
                }
                for player in self.state.user_roster
            ],
            "needs": {
                slot: {"filled": need.filled, "required": need.required}
                for slot, need in self.state.needs.items()
            },
            "weekly": [
                {
                    "week": cell.week,
                    "starter_points": cell.starter_points,
                    "empty": [slot.value for slot in cell.empty],
                }
                for cell in self.state.weekly
            ],
            "recent": [
                {
                    "player_id": pick.player_id,
                    "position": pick.position,
                    "pick_no": pick.pick_no,
                }
                for pick in self.state.recent
            ],
        }
        if self.state.next_user_pick is not None:
            state["next_user_pick"] = self.state.next_user_pick
        if self.state.picks_until_next is not None:
            state["picks_until_next"] = self.state.picks_until_next
        if self.state.between is not None:
            state["between"] = [
                {
                    "slot": team.slot,
                    "roster": dict(team.roster),
                    "needs": {
                        slot: {"filled": need.filled, "required": need.required}
                        for slot, need in team.needs.items()
                    },
                }
                for team in self.state.between
            ]
        return {
            "config": config,
            "state": state,
            "replacement": {
                pos: {"player_id": row.player_id, "points": row.points}
                for pos, row in self.replacement.items()
            },
            "hint_argmax_vols": self.hint_argmax_vols,
            "board": [_board_row_to_dict(row) for row in self.board],
        }


@dataclass(frozen=True, slots=True)
class Proposal:
    player_id: str
    alternatives: tuple[str, ...]
    slot_filled: Slot
    coin_flip: bool
    why: str
    flags: tuple[Flag, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "alternatives": list(self.alternatives),
            "slot_filled": self.slot_filled.value,
            "coin_flip": self.coin_flip,
            "why": self.why,
            "flags": [flag.value for flag in self.flags],
        }


@dataclass(frozen=True, slots=True)
class Violation:
    """One SPEC.md section 4 rule the model broke. Fails the call, not the run."""

    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class Recommendation:
    """What the operator sees. A degraded pick still carries its violations.

    `degraded` means the model's proposal never validated and `proposal` is the
    calculator answer instead. Evals read `violations`; draft night reads
    `proposal` and surfaces `violations` as banners.
    """

    proposal: Proposal
    violations: tuple[Violation, ...]
    degraded: bool
    attempts: int


def _board_row_to_dict(row: BoardRow) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "player_id": row.player_id,
        "name": row.name,
        "position": row.position,
        "points": row.points,
        "vols": row.vols,
        "delta_starter_points": row.delta_starter_points,
        "adp": row.adp,
        "legal_slots": [slot.value for slot in row.legal_slots],
    }
    if row.bye is not None:
        payload["bye"] = row.bye
    if row.gp is not None:
        payload["gp"] = row.gp
    if row.ecr is not None:
        payload["ecr"] = row.ecr
    if row.ecr_min is not None:
        payload["ecr_min"] = row.ecr_min
    if row.ecr_max is not None:
        payload["ecr_max"] = row.ecr_max
    if row.ecr_std is not None:
        payload["ecr_std"] = row.ecr_std
    return payload
