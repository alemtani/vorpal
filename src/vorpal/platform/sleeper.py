"""Sleeper adapter. Maps recorded api.sleeper.app JSON onto generic contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from vorpal.contracts import (
    Draft,
    Host,
    League,
    LeagueFormat,
    Pick,
    Player,
    Slot,
    SlotCounts,
    User,
)
from vorpal.errors import PlatformError
from vorpal.platform.base import LeagueHost

_SLEEPER_FORMAT = {
    0: LeagueFormat.REDRAFT,
    1: LeagueFormat.KEEPER,
    2: LeagueFormat.DYNASTY,
}

_SLOT_SETTING = {
    "slots_qb": "qb",
    "slots_rb": "rb",
    "slots_wr": "wr",
    "slots_te": "te",
    "slots_k": "k",
    "slots_def": "defense",
    "slots_flex": "flex",
    "slots_super_flex": "super_flex",
    "slots_op": "op",
}


def _require_mapping(payload: Any, what: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PlatformError(f"Sleeper {what} is not an object")
    return cast(dict[str, Any], payload)


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _as_int(value: Any, what: str, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise PlatformError(f"Sleeper {what} is missing")
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PlatformError(f"Sleeper {what} is not an int") from exc


def _as_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PlatformError("Sleeper int field is not an int") from exc


class SleeperHost(LeagueHost):
    """v1 league host. ESPN would be a sibling class, not a branch in this file."""

    @property
    def name(self) -> str:
        return Host.SLEEPER.value

    def parse_draft(self, payload: Any) -> Draft:
        raw = _require_mapping(payload, "draft")
        settings = raw.get("settings")
        if not isinstance(settings, dict):
            raise PlatformError("Sleeper draft settings is not an object")
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        counts: dict[str, int] = {}
        for wire_key, field in _SLOT_SETTING.items():
            if wire_key in settings:
                counts[field] = _as_int(settings[wire_key], wire_key, default=0)
        bn = (
            _as_int(settings["slots_bn"], "slots_bn")
            if "slots_bn" in settings
            else None
        )
        order_raw = raw.get("draft_order")
        draft_order: dict[str, int] | None
        if order_raw is None:
            draft_order = None
        elif isinstance(order_raw, dict):
            draft_order = {
                str(uid): _as_int(slot, "draft_order slot")
                for uid, slot in order_raw.items()
            }
        else:
            raise PlatformError("Sleeper draft_order is not an object")
        slot_map_raw = raw.get("slot_to_roster_id")
        if slot_map_raw is None:
            slot_map_raw = {}
        elif not isinstance(slot_map_raw, dict):
            raise PlatformError("Sleeper slot_to_roster_id is not an object")
        slot_to_roster = {
            _as_int(slot, "slot_to_roster_id key"): _as_int(roster, "slot_to_roster_id")
            for slot, roster in slot_map_raw.items()
        }
        league_id = raw.get("league_id")
        return Draft(
            host=Host.SLEEPER,
            draft_id=str(raw.get("draft_id") or ""),
            type=str(raw.get("type") or ""),
            status=str(raw.get("status") or ""),
            sport=str(raw.get("sport") or ""),
            season=str(raw.get("season") or ""),
            season_type=str(raw.get("season_type") or ""),
            league_id=None if league_id is None else str(league_id),
            start_time=_as_int_or_none(raw.get("start_time")),
            teams=_as_int(settings.get("teams"), "teams"),
            rounds=_as_int(settings.get("rounds"), "rounds"),
            pick_timer=_as_int_or_none(settings.get("pick_timer")),
            reversal_round=_as_int(settings.get("reversal_round"), "reversal_round", 0),
            slot_counts=SlotCounts(
                qb=counts.get("qb", 0),
                rb=counts.get("rb", 0),
                wr=counts.get("wr", 0),
                te=counts.get("te", 0),
                k=counts.get("k", 0),
                defense=counts.get("defense", 0),
                flex=counts.get("flex", 0),
                super_flex=counts.get("super_flex", 0),
                op=counts.get("op", 0),
                bn=bn,
            ),
            scoring_label=_optional_str(metadata.get("scoring_type")),
            draft_order=draft_order,
            slot_to_roster_id=slot_to_roster,
        )

    def parse_league(self, payload: Any) -> League:
        raw = _require_mapping(payload, "league")
        settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
        type_raw = settings.get("type")
        if type_raw is None:
            fmt = LeagueFormat.UNKNOWN
        else:
            fmt = _SLEEPER_FORMAT.get(
                _as_int(type_raw, "settings.type"), LeagueFormat.UNKNOWN
            )
        positions_raw = raw.get("roster_positions")
        if positions_raw is None:
            positions_raw = []
        elif not isinstance(positions_raw, list):
            raise PlatformError("Sleeper roster_positions is not a list")
        positions: list[Slot] = []
        for code in positions_raw:
            try:
                positions.append(Slot(str(code)))
            except ValueError as exc:
                raise PlatformError(f"Sleeper unknown slot code {code!r}") from exc
        scoring_raw = raw.get("scoring_settings")
        if scoring_raw is None:
            scoring_raw = {}
        elif not isinstance(scoring_raw, dict):
            raise PlatformError("Sleeper scoring_settings is not an object")
        scoring = {str(key): float(value) for key, value in scoring_raw.items()}
        return League(
            host=Host.SLEEPER,
            league_id=str(raw.get("league_id") or ""),
            draft_id=str(raw.get("draft_id") or ""),
            season=str(raw.get("season") or ""),
            status=str(raw.get("status") or ""),
            sport=str(raw.get("sport") or ""),
            season_type=str(raw.get("season_type") or ""),
            total_rosters=_as_int(raw.get("total_rosters"), "total_rosters", 0),
            roster_positions=tuple(positions),
            scoring=scoring,
            format=fmt,
            max_keepers=_as_int(settings.get("max_keepers"), "max_keepers", 0),
            taxi_slots=_as_int(settings.get("taxi_slots"), "taxi_slots", 0),
            num_teams=_as_int(settings.get("num_teams"), "num_teams", 0),
        )

    def parse_picks(self, payload: Any) -> tuple[Pick, ...]:
        if not isinstance(payload, list):
            raise PlatformError("Sleeper picks is not a list")
        picks: list[Pick] = []
        for row in payload:
            if not isinstance(row, dict):
                raise PlatformError("Sleeper pick is not an object")
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            keeper = row.get("is_keeper")
            if keeper is None:
                is_keeper = None
            else:
                is_keeper = bool(keeper)
            picks.append(
                Pick(
                    draft_id=str(row.get("draft_id") or ""),
                    player_id=str(row.get("player_id") or ""),
                    picked_by=""
                    if row.get("picked_by") is None
                    else str(row.get("picked_by")),
                    roster_id=_as_int_or_none(row.get("roster_id")),
                    round=_as_int(row.get("round"), "round", 0),
                    draft_slot=_as_int(row.get("draft_slot"), "draft_slot", 0),
                    pick_no=_as_int(row.get("pick_no"), "pick_no", 0),
                    is_keeper=is_keeper,
                    position=_optional_str(meta.get("position")),
                    team=_optional_str(meta.get("team")),
                    first_name=_optional_str(meta.get("first_name")),
                    last_name=_optional_str(meta.get("last_name")),
                )
            )
        return tuple(picks)

    def parse_players(self, payload: Any) -> dict[str, Player]:
        if not isinstance(payload, dict):
            raise PlatformError("Sleeper players is not an object")
        out: dict[str, Player] = {}
        for pid, row in payload.items():
            if not isinstance(row, dict):
                raise PlatformError("Sleeper player is not an object")
            out[str(pid)] = self._player(row)
        return out

    def parse_user(self, payload: Any) -> User:
        raw = _require_mapping(payload, "user")
        return User(
            user_id=str(raw.get("user_id") or ""),
            username=str(raw.get("username") or ""),
            display_name=str(raw.get("display_name") or ""),
            is_bot=bool(raw.get("is_bot", False)),
        )

    def _player(self, row: Mapping[str, Any]) -> Player:
        first = str(row.get("first_name") or "")
        last = str(row.get("last_name") or "")
        full = row.get("full_name")
        name = str(full) if full else f"{first} {last}".strip()
        fantasy = row.get("fantasy_positions") or []
        if not isinstance(fantasy, list):
            fantasy = []
        return Player(
            player_id=str(row.get("player_id") or ""),
            host=Host.SLEEPER,
            first_name=first,
            last_name=last,
            name=name,
            position=str(row.get("position") or ""),
            team=_optional_str(row.get("team")),
            fantasy_positions=tuple(str(item) for item in fantasy),
            active=row.get("active") if isinstance(row.get("active"), bool) else None,
            status=_optional_str(row.get("status")),
            injury_status=_optional_str(row.get("injury_status")),
            years_exp=_as_int_or_none(row.get("years_exp")),
            number=_as_int_or_none(row.get("number")),
            search_rank=_as_int_or_none(row.get("search_rank")),
            bye=None,
        )
