"""One command: read the draft, value the pool, ask the model, write the board.

Wiring only. Every number on the page is computed in a module — `resolve`,
`ingest`, `valuation`, `payload`, `model`, `board`. If something here starts
looking like a feature, it belongs in one of those instead.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from vorpal.board import Frame, run_loop
from vorpal.contracts import (
    Banner,
    Draft,
    DraftState,
    EcrRow,
    Host,
    Payload,
    Pick,
    Player,
    Proposal,
    Slot,
    StatRow,
)
from vorpal.errors import (
    DataRefusal,
    PlatformError,
    UnsupportedLeague,
    UserRefusal,
    VorpalError,
)
from vorpal.ingest import load_forecast
from vorpal.model import AnthropicTransport, propose
from vorpal.payload import build_payload, build_rows, build_state
from vorpal.platform import LeagueClient
from vorpal.platform.presets import PRESETS, preset_league
from vorpal.resolve import Resolved, resolve
from vorpal.sleeper import SleeperClient
from vorpal.valuation import ScoredPlayer, compute_vols, score_player

FP_KEY_ENV = "FANTASYPROS_API_KEY"
DEFAULT_OUTPUT = Path("board.html")
FP_MIN_INTERVAL_S = 1.1

# The model runs only when this seat is on the clock (`picks_until_next == 0`).
# A window of 2 used to pre-call on the picks in front; that is three bills
# per operator pick and a stale rec shown as current. Other people's picks
# get the calculator.

# Each class keeps its own word. Collapsing them costs the operator the one
# thing the message is for: whether a better file, a retry, or a different
# league fixes it.
REFUSAL_LABELS: tuple[tuple[type[VorpalError], str], ...] = (
    (UnsupportedLeague, "unsupported league"),
    (DataRefusal, "data refusal"),
    (PlatformError, "platform error"),
    (UserRefusal, "user refusal"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vorpal",
        description="Build a draft board. The model recommends; you click.",
    )
    parser.add_argument("--draft-id", required=True, help="Sleeper draft id")
    parser.add_argument(
        "--operator",
        required=True,
        help="your Sleeper username or user_id",
    )
    scoring = parser.add_mutually_exclusive_group()
    scoring.add_argument(
        "--scoring-league-id",
        default=None,
        help="league to borrow scoring from; required for a standalone mock",
    )
    scoring.add_argument(
        "--scoring",
        default=None,
        choices=PRESETS,
        help="borrow a canonical Sleeper default scoring table for a standalone "
        "mock, instead of a league. Slots still come from the mock; superflex "
        "is read from the mock's slots, not from the preset",
    )
    parser.add_argument(
        "--slot",
        type=int,
        default=None,
        help="your 1-based draft slot; only read when the draft order is partial",
    )
    parser.add_argument(
        "--override",
        type=Path,
        default=None,
        help="CSV of stats and ADP to use when FantasyPros is down",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"board file to write (default {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--players-cache",
        type=Path,
        default=None,
        help="where to cache GET /players (default is under your home directory)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    client: LeagueClient | None = None,
    transport: object | None = None,
    sleep=time.sleep,
    now=time.monotonic,
) -> int:
    """Run one draft. Returns 0, or 2 with a refusal on stderr."""
    args = build_parser().parse_args(argv)
    owned = client is None
    host_client = client if client is not None else _client(args)
    try:
        _run(
            args,
            host_client,
            transport if transport is not None else AnthropicTransport(),
            sleep=sleep,
            now=now,
        )
    except VorpalError as exc:
        print(f"{_label(exc)}: {exc.message}", file=sys.stderr)
        return 2
    finally:
        if owned:
            host_client.close()
    return 0


def _client(args: argparse.Namespace) -> LeagueClient:
    return SleeperClient(players_cache_path=args.players_cache)


def _label(exc: VorpalError) -> str:
    for kind, label in REFUSAL_LABELS:
        if isinstance(exc, kind):
            return label
    return "error"


def _run(
    args: argparse.Namespace,
    client: LeagueClient,
    transport,
    *,
    sleep,
    now,
) -> None:
    draft = client.get_draft(args.draft_id)
    picks = client.get_picks(args.draft_id)
    operator = client.get_user(args.operator)
    league = client.get_league(draft.league_id) if draft.league_id else None
    if args.scoring is not None:
        scoring_league = preset_league(args.scoring, draft.season, draft.host)
    elif args.scoring_league_id is not None:
        scoring_league = client.get_league(args.scoring_league_id)
    else:
        scoring_league = None

    # Resolve twice on purpose. The ADP variant decides which forecast to
    # fetch, and the fetched columns decide the unknown-key banner, which
    # LeagueConfig freezes. Resolve is pure, so the second call is free.
    seed = resolve(
        draft,
        operator=operator,
        league=league,
        scoring_league=scoring_league,
        explicit_slot=args.slot,
        picks=picks,
    )
    players = client.get_players()
    stat_rows, ecr_rows, forecast_banners = load_forecast(
        draft.season,
        seed.config.adp_variant,
        ecr_scoring=seed.config.ecr_scoring,
        superflex=seed.ecr_position == "OP",
        host_players=players,
        override_path=args.override,
        fp_api_key=os.environ.get(FP_KEY_ENV),
        scoring=seed.config.scoring,
        min_interval_s=FP_MIN_INTERVAL_S,
    )
    resolved = resolve(
        draft,
        operator=operator,
        league=league,
        scoring_league=scoring_league,
        explicit_slot=args.slot,
        picks=picks,
        stat_columns=frozenset(key for row in stat_rows for key in row.stats),
    )
    banners = resolved.config.banners + forecast_banners
    _print_banners(banners)

    pool = _pool(stat_rows, ecr_rows, players, resolved, draft.host)
    adp = {row.player_id: row.adp for row in stat_rows if row.adp is not None}
    ecr = {row.player_id: row for row in ecr_rows}

    frames = _Frames(_Proposals(transport))

    def recompute(live: Draft, live_picks: tuple[Pick, ...]) -> Frame:
        return frames.get(
            live,
            live_picks,
            resolved=resolved,
            pool=pool,
            adp=adp,
            ecr=ecr,
            extra=forecast_banners,
        )

    run_loop(
        _BoundClient(client, args.draft_id),
        recompute,
        args.out,
        now=now,
        sleep=sleep,
    )


class _Frames:
    """One computed board per pick. A poll that changes nothing computes nothing.

    The loop polls every 3s and the pick number moves at most once a poll,
    usually not at all. VOLS over the pool, the row join, and the payload
    are the same page until someone picks, so build them once and hand the
    same frame back. ``status`` and ``pick_timer`` are on the page too, so
    a change in either is a new key. Page age is not: ``run_loop`` renders
    that from its own clock, so a cached frame still ages on screen.
    """

    __slots__ = ("_frame", "_key", "_proposals")

    def __init__(self, proposals: _Proposals) -> None:
        self._proposals = proposals
        self._key: tuple[int, str, int | None] | None = None
        self._frame: Frame | None = None

    def get(
        self,
        draft: Draft,
        picks: tuple[Pick, ...],
        *,
        resolved: Resolved,
        pool: Mapping[str, ScoredPlayer],
        adp: Mapping[str, float],
        ecr: Mapping[str, EcrRow],
        extra: tuple[Banner, ...],
    ) -> Frame:
        key = (len(picks), draft.status, draft.pick_timer)
        if self._frame is not None and key == self._key:
            return self._frame
        frame = _frame(
            draft,
            picks,
            resolved=resolved,
            pool=pool,
            adp=adp,
            ecr=ecr,
            proposals=self._proposals,
            extra=extra,
        )
        self._key = key
        self._frame = frame
        return frame


class _Proposals:
    """Decides when the model runs. Draft night is mostly other people's picks.

    ``recompute`` fires on every poll — 3s while the draft is live. The model
    runs only when this seat is on the clock. One pick away still waits.
    Between turns the page shows the calculator, not a stale rec.
    """

    __slots__ = ("_banners", "_pick_no", "_proposal", "_transport")

    def __init__(self, transport) -> None:
        self._transport = transport
        self._proposal: Proposal | None = None
        self._banners: tuple[Banner, ...] = ()
        self._pick_no: int | None = None

    def for_payload(self, payload: Payload) -> tuple[Proposal, tuple[Banner, ...]]:
        """The proposal to show for this payload, and any banners it carries."""
        pick_no = payload.state.pick_no
        if not self._on_clock(payload.state):
            return self._placeholder(payload)
        if self._proposal is not None and pick_no == self._pick_no:
            return self._proposal, self._banners
        return self._call(payload, pick_no)

    def _on_clock(self, state: DraftState) -> bool:
        # No seat means no clock. Answer every new pick so the page is not empty.
        # Past the last pick, picks_until_next is None, so snapshots still call.
        return state.picks_until_next is None or state.picks_until_next == 0

    def _call(
        self, payload: Payload, pick_no: int
    ) -> tuple[Proposal, tuple[Banner, ...]]:
        result = propose(payload, self._transport)
        banners: tuple[Banner, ...] = ()
        if result.degraded:
            banners = tuple(
                Banner(code=f"violation_{violation.code}", message=violation.message)
                for violation in result.violations
            )
        self._proposal = result.proposal
        self._banners = banners
        self._pick_no = pick_no
        return result.proposal, banners

    def _placeholder(self, payload: Payload) -> tuple[Proposal, tuple[Banner, ...]]:
        """Calculator pick. No model. Used on everyone else's turn."""
        rec = next(
            row for row in payload.board if row.player_id == payload.hint_argmax_vols
        )
        alts = tuple(
            row.player_id for row in payload.board if row.player_id != rec.player_id
        )[:2]
        return (
            Proposal(
                player_id=rec.player_id,
                alternatives=alts,
                slot_filled=rec.legal_slots[0],
                coin_flip=False,
                why="Not your pick. Calculator until you are on the clock.",
                flags=(),
            ),
            (),
        )


class _BoundClient:
    """S1's client bound to one draft id. The poll loop takes no id."""

    __slots__ = ("_client", "_draft_id")

    def __init__(self, client: LeagueClient, draft_id: str) -> None:
        self._client = client
        self._draft_id = draft_id

    def get_draft(self) -> Draft:
        return self._client.get_draft(self._draft_id)

    def get_picks(self) -> tuple[Pick, ...]:
        return self._client.get_picks(self._draft_id)


def _print_banners(banners: Sequence[Banner]) -> None:
    """Banners reach the operator before the first board, never after."""
    for banner in banners:
        print(f"banner {banner.code}: {banner.message}", file=sys.stderr)


def _pool(
    stat_rows: Sequence[StatRow],
    ecr_rows: Sequence[EcrRow],
    players: Mapping[str, Player],
    resolved: Resolved,
    host: Host,
) -> dict[str, ScoredPlayer]:
    """Score every projected player once. Keepers are already off the board."""
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


def _frame(
    draft: Draft,
    picks: tuple[Pick, ...],
    *,
    resolved: Resolved,
    pool: Mapping[str, ScoredPlayer],
    adp: Mapping[str, float],
    ecr: Mapping[str, EcrRow],
    proposals: _Proposals,
    extra: tuple[Banner, ...],
) -> Frame:
    """One board. The only thing that changes between polls is the picks."""
    drafted = {pick.player_id for pick in picks}
    available = frozenset(pool) - drafted
    slots: tuple[Slot, ...] = resolved.config.slots
    values = compute_vols(
        [pool[player_id] for player_id in sorted(available)],
        slots,
        resolved.config.teams,
    )
    state = build_state(
        pick_no=len(picks) + 1,
        slots=slots,
        teams=resolved.config.teams,
        rounds=resolved.config.rounds,
        seat=resolved.seat,
        picks=picks,
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
    # The page reads status and pick_timer off the config; the loop reads them
    # off the draft. Copy them across or the two disagree.
    config = replace(resolved.config, status=draft.status, pick_timer=draft.pick_timer)
    payload = build_payload(config, state, values.replacement, rows)
    proposal, proposal_banners = proposals.for_payload(payload)
    return Frame(payload=payload, proposal=proposal, banners=extra + proposal_banners)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
