"""Builders for resolve tests. No network."""

from __future__ import annotations

import json
from pathlib import Path

from vorpal.contracts import (
    Draft,
    Host,
    League,
    LeagueFormat,
    Pick,
    Slot,
    SlotCounts,
    User,
)
from vorpal.platform import SleeperHost

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HOST = SleeperHost()

OPERATOR = User(
    user_id="user_operator",
    username="operator",
    display_name="Operator",
    is_bot=False,
)

# Counting keys that scoring tests can hit. Fixture tests use the recorded file.
COLUMNS = frozenset(
    {
        "pass_td",
        "pass_yd",
        "pass_int",
        "pass_2pt",
        "rush_td",
        "rush_yd",
        "rush_2pt",
        "rec",
        "rec_yd",
        "rec_td",
        "rec_2pt",
        "fum_lost",
        "fgm_50p",
        "fgm_40_49",
        "xpm",
        "xpmiss",
        "sack",
        "int",
        "fum_rec",
        "blk_kick",
        "pts_allow_0",
    }
)

STARTER_SLOTS = (
    Slot.QB,
    Slot.RB,
    Slot.RB,
    Slot.WR,
    Slot.WR,
    Slot.TE,
    Slot.FLEX,
    Slot.FLEX,
    Slot.K,
    Slot.DEF,
)

SCORING = {
    "pass_td": 4.0,
    "pass_yd": 0.04,
    "pass_int": -1.0,
    "rush_td": 6.0,
    "rush_yd": 0.1,
    "rec": 1.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "fum_lost": -2.0,
    "fgm_50p": 5.0,
    "xpm": 1.0,
    "sack": 1.0,
    "int": 2.0,
    "fum_rec": 2.0,
}


def load_json(relative: str) -> object:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def load_draft(name: str) -> Draft:
    return HOST.parse_draft(load_json(f"sleeper/{name}"))


def load_league(name: str) -> League:
    return HOST.parse_league(load_json(f"sleeper/{name}"))


def load_picks(name: str) -> tuple[Pick, ...]:
    return HOST.parse_picks(load_json(f"sleeper/{name}"))


def projection_columns() -> frozenset[str]:
    rows = load_json("projections/season_regular.json")
    keys: set[str] = set()
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        stats = row.get("stats")
        if isinstance(stats, dict):
            keys.update(str(key) for key in stats)
    return frozenset(
        key for key in keys if not key.startswith("pts_") and not key.startswith("adp_")
    )


def complete_order(*, teams: int = 12, operator_slot: int | None = 2) -> dict[str, int]:
    order: dict[str, int] = {}
    for slot in range(1, teams + 1):
        if operator_slot is not None and slot == operator_slot:
            order[OPERATOR.user_id] = slot
        else:
            order[f"user_{slot:02d}"] = slot
    return order


def make_counts(**overrides: int | None) -> SlotCounts:
    values: dict[str, int | None] = {
        "qb": 1,
        "rb": 2,
        "wr": 2,
        "te": 1,
        "k": 1,
        "defense": 1,
        "flex": 2,
        "super_flex": 0,
        "op": 0,
        "bn": 5,
    }
    values.update(overrides)
    return SlotCounts(**values)  # type: ignore[arg-type]


def make_draft(**overrides: object) -> Draft:
    teams = int(overrides.get("teams", 12))  # type: ignore[arg-type]
    values: dict[str, object] = {
        "host": Host.SLEEPER,
        "draft_id": "draft_x",
        "type": "snake",
        "status": "pre_draft",
        "sport": "nfl",
        "season": "2026",
        "season_type": "regular",
        "league_id": "league_x",
        "start_time": None,
        "teams": teams,
        "rounds": 15,
        "pick_timer": 60,
        "reversal_round": 0,
        "slot_counts": make_counts(),
        "scoring_label": "ppr",
        "draft_order": complete_order(teams=teams),
        "slot_to_roster_id": {i: i for i in range(1, teams + 1)},
    }
    values.update(overrides)
    return Draft(**values)  # type: ignore[arg-type]


def make_league(**overrides: object) -> League:
    values: dict[str, object] = {
        "host": Host.SLEEPER,
        "league_id": "league_x",
        "draft_id": "draft_x",
        "season": "2026",
        "status": "in_season",
        "sport": "nfl",
        "season_type": "regular",
        "total_rosters": 12,
        "roster_positions": STARTER_SLOTS + (Slot.BN,) * 5,
        "scoring": dict(SCORING),
        "format": LeagueFormat.REDRAFT,
        "max_keepers": 0,
        "taxi_slots": 0,
        "num_teams": 12,
    }
    values.update(overrides)
    return League(**values)  # type: ignore[arg-type]


def make_pick(**overrides: object) -> Pick:
    values: dict[str, object] = {
        "draft_id": "draft_x",
        "player_id": "1",
        "picked_by": "",
        "roster_id": 1,
        "round": 1,
        "draft_slot": 1,
        "pick_no": 1,
        "is_keeper": None,
        "position": "RB",
        "team": "PHI",
        "first_name": "A",
        "last_name": "B",
    }
    values.update(overrides)
    return Pick(**values)  # type: ignore[arg-type]
