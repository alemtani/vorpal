# ruff: noqa: E501
"""Build a payload at one pick from recorded drafts, or from a human mock.

This is the CLI's `_frame` arithmetic without the model call. S10 does not
touch `src/`. Forecast is fetched once per process; call `clear_caches`
between seasons.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from vorpal.contracts import (
    AdpVariant,
    Banner,
    Draft,
    EcrRow,
    Host,
    League,
    LeagueConfig,
    Pick,
    Player,
    Seat,
    Slot,
    StatRow,
    User,
)
from vorpal.ingest import load_forecast
from vorpal.payload import build_payload, build_rows, build_state
from vorpal.platform import SleeperHost
from vorpal.resolve import Resolved, resolve
from vorpal.sleeper import SleeperClient
from vorpal.valuation import (
    ScoredPlayer,
    compute_vols,
    hypothetical_replacement_ranks,
    replacement_rank_shifts,
    score_player,
)

ROOT = Path(__file__).resolve().parents[1]
SLEEPER_FIX = ROOT / "tests" / "fixtures" / "sleeper"
CACHE = Path(__file__).resolve().parent / "_cache"

# Map recorded regret draft_id stem -> (draft file stem, league file stem).
REGRET_SOURCES = {
    "draft_snake_redraft": ("snake_redraft", "snake_redraft"),
    "draft_superflex": ("superflex", "superflex"),
    "draft_mock_standalone": ("mock_standalone", None),
}

# Mock has no league. Borrow the recorded PPR table. The mock's own label is
# half_ppr; that is a banner, not a refusal. Report it.
MOCK_SCORING_LEAGUE = "snake_redraft"

_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)
_TEAM_ALIAS = {"JAC": "JAX", "JAX": "JAC", "WAS": "WSH", "WSH": "WAS"}


@dataclass(frozen=True, slots=True)
class BuiltBoard:
    """One frozen pick: the payload the model sees, plus rank deltas."""

    payload: object
    rank_delta: dict[str, int]
    season_used: str
    banners: tuple[str, ...]


def load_json(path: Path) -> object:
    return json.loads(path.read_text())


def parse_recorded(
    draft_stem: str, league_stem: str | None
) -> tuple[Draft, League | None, tuple[Pick, ...]]:
    host = SleeperHost()
    draft = host.parse_draft(load_json(SLEEPER_FIX / f"draft_{draft_stem}.json"))
    league = None
    if league_stem is not None:
        league = host.parse_league(
            load_json(SLEEPER_FIX / f"league_{league_stem}.json")
        )
    picks = host.parse_picks(load_json(SLEEPER_FIX / f"picks_{draft_stem}.json"))
    return draft, league, picks


def operator_for(draft: Draft, slot: int) -> User:
    """The redacted user_id that owns `slot` in draft_order."""
    if draft.draft_order:
        for user_id, owned in draft.draft_order.items():
            if owned == slot:
                return User(
                    user_id=user_id,
                    username=user_id,
                    display_name=user_id,
                    is_bot=False,
                )
    return User(
        user_id="unknown", username="unknown", display_name="unknown", is_bot=False
    )


def load_players(client: SleeperClient | None = None) -> dict[str, Player]:
    """Live /players, cached under evals/_cache. Recorded subset cannot join FP."""
    owned = client is None
    host_client = (
        client
        if client is not None
        else SleeperClient(players_cache_path=CACHE / "sleeper_players.json")
    )
    try:
        return host_client.get_players()
    finally:
        if owned:
            host_client.close()


def forecast_for(
    draft: Draft,
    resolved_seed: Resolved,
    players: Mapping[str, Player],
    *,
    fp_api_key: str | None,
    season_override: str | None = None,
) -> tuple[tuple[StatRow, ...], tuple[EcrRow, ...], tuple, str]:
    """FantasyPros for this draft. Fall back to 2026 if the draft season 404s."""
    from vorpal.errors import DataRefusal, PlatformError

    seasons = [season_override] if season_override else [draft.season]
    if draft.season != "2026" and "2026" not in seasons:
        seasons.append("2026")
    last_error: Exception | None = None
    for season in seasons:
        try:
            stats, ecr, banners = load_forecast(
                season,
                resolved_seed.config.adp_variant,
                ecr_scoring=resolved_seed.config.ecr_scoring,
                superflex=resolved_seed.ecr_position == "OP",
                host_players=players,
                fp_api_key=fp_api_key,
                scoring=resolved_seed.config.scoring,
                min_interval_s=1.1,
            )
            return stats, ecr, banners, season
        except (DataRefusal, PlatformError) as exc:
            last_error = exc
            from vorpal.ingest import clear_caches

            clear_caches()
    raise last_error or DataRefusal("forecast failed")


def score_pool(
    stat_rows: Sequence[StatRow],
    ecr_rows: Sequence[EcrRow],
    players: Mapping[str, Player],
    resolved: Resolved,
    host: Host,
) -> dict[str, ScoredPlayer]:
    byes = {row.player_id: row.bye for row in ecr_rows if row.bye is not None}
    pool: dict[str, ScoredPlayer] = {}
    for row in stat_rows:
        player = players.get(row.player_id)
        if player is None or row.player_id in resolved.keeper_ids:
            continue
        pool[row.player_id] = ScoredPlayer(
            player_id=row.player_id,
            position=player.position,
            points=score_player(
                player.position, row.stats, resolved.config.scoring, host=host
            ),
            market_only=row.market_only,
            gp=row.gp,
            bye=row.bye if row.bye is not None else byes.get(row.player_id),
            name=player.name,
        )
    return pool


def build_at_pick(
    *,
    resolved: Resolved,
    picks_before: Sequence[Pick],
    pool: Mapping[str, ScoredPlayer],
    adp: Mapping[str, float],
    ecr: Mapping[str, EcrRow],
    pick_no: int,
) -> BuiltBoard:
    drafted = {pick.player_id for pick in picks_before}
    available = frozenset(pool) - drafted
    slots: tuple[Slot, ...] = resolved.config.slots
    available_players = [pool[pid] for pid in sorted(available)]
    values = compute_vols(available_players, slots, resolved.config.teams)
    extra = hypothetical_replacement_ranks(
        available_players, slots, resolved.config.teams, values
    )
    delta = replacement_rank_shifts(values.replacement_ranks, extra)
    state = build_state(
        pick_no=pick_no,
        slots=slots,
        teams=resolved.config.teams,
        rounds=resolved.config.rounds,
        seat=resolved.seat,
        picks=picks_before,
        pool=pool,
    )
    rows = build_rows(
        values,
        pool=pool,
        available=available,
        adp=adp,
        ecr=ecr,
        roster=[
            pool[player.player_id]
            for player in state.user_roster
            if player.player_id in pool
        ],
        slots=slots,
        teams=resolved.config.teams,
        rounds=resolved.config.rounds,
        pick_no=state.pick_no,
        needs=state.needs,
    )
    payload = build_payload(resolved.config, state, values.replacement, rows)
    return BuiltBoard(
        payload=payload,
        rank_delta=delta,
        season_used="",
        banners=tuple(b.code for b in resolved.config.banners),
    )


def resolve_recorded(
    draft: Draft,
    *,
    league: League | None,
    scoring_league: League | None,
    operator: User,
    picks: tuple[Pick, ...],
    stat_columns: frozenset[str] | None = None,
) -> Resolved:
    return resolve(
        draft,
        operator=operator,
        league=league,
        scoring_league=scoring_league,
        picks=picks,
        stat_columns=stat_columns,
    )


def norm_name(name: str) -> str:
    stripped = _SUFFIX.sub("", name.strip())
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def match_player(
    name: str,
    position: str,
    team: str,
    players: Mapping[str, Player],
) -> Player | None:
    """Join a human-typed name onto a host player. Name+pos, team breaks ties."""
    want = norm_name(name)
    pos = position.upper()
    team_u = team.upper()
    aliases = {team_u, _TEAM_ALIAS.get(team_u, team_u)}
    same_pos: list[Player] = []
    for player in players.values():
        if player.position != pos and pos not in player.fantasy_positions:
            continue
        if player.position in {"K", "DEF"} and pos not in {
            player.position,
            "DEF",
            "DST",
        }:
            continue
        same_pos.append(player)
    exact = [p for p in same_pos if norm_name(p.name) == want]
    if not exact:
        # First+last without suffix already equal; try last-name match with first token.
        tokens = want
        exact = [p for p in same_pos if norm_name(p.name).startswith(tokens)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        by_team = [p for p in exact if (p.team or "").upper() in aliases]
        if len(by_team) == 1:
            return by_team[0]
        # Prefer the active row if one is.
        active = [p for p in (by_team or exact) if p.active is not False]
        if len(active) == 1:
            return active[0]
        return (by_team or exact)[0]
    # Last-name fallback: "Marvin Harrison" vs "Marvin Harrison Jr."
    last = norm_name(name.split()[-1]) if name.split() else ""
    first = norm_name(name.split()[0]) if name.split() else ""
    last_hits = [
        p
        for p in same_pos
        if norm_name(p.last_name) == last and norm_name(p.first_name).startswith(first)
    ]
    if len(last_hits) == 1:
        return last_hits[0]
    if len(last_hits) > 1:
        by_team = [p for p in last_hits if (p.team or "").upper() in aliases]
        return (by_team or last_hits)[0]
    return None


def superflex_scoring() -> dict[str, float]:
    """Recorded superflex league scoring. PPR. Used for the operator's mocks."""
    body = load_json(SLEEPER_FIX / "league_superflex.json")
    raw = body["scoring_settings"]
    return {str(k): float(v) for k, v in raw.items()}


def human_config(scoring: Mapping[str, float]) -> LeagueConfig:
    slots = tuple(
        Slot[code] if code != "SUPER_FLEX" else Slot.SUPER_FLEX
        for code in (
            "QB",
            "RB",
            "RB",
            "WR",
            "WR",
            "TE",
            "FLEX",
            "FLEX",
            "SUPER_FLEX",
            "BN",
            "BN",
            "BN",
            "BN",
            "BN",
        )
    )
    return LeagueConfig(
        teams=10,
        rounds=14,
        slots=slots,
        scoring=dict(scoring),
        scoring_summary="PPR superflex (borrowed recorded table)",
        banners=(
            Banner(
                code="human_mock",
                message="operator mock; scoring borrowed from recorded superflex",
            ),
        ),
        slot=1,
        draft_id="human",
        league_id=None,
        season="2026",
        adp_variant=AdpVariant.TWO_QB,
        ecr_scoring="PPR",
    )


def human_resolved(config: LeagueConfig) -> Resolved:
    return Resolved(
        config=config,
        seat=Seat(user_id="operator", slot=1, roster_id=1),
        ecr_position="OP",
        keeper_ids=frozenset(),
    )
