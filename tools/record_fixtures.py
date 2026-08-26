"""Record redacted Sleeper, projection, and FantasyPros fixtures.

Source IDs are CLI/env only. They are never written to tests/fixtures/.
Re-run:

    uv run python tools/record_fixtures.py \\
      --snake-draft DRAFT_ID --snake-league LEAGUE_ID \\
      --mock-draft DRAFT_ID \\
      --superflex-draft DRAFT_ID --superflex-league LEAGUE_ID \\
      --mid-draft DRAFT_ID \\
      --operator-username USERNAME
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

OPERATOR_USER_ID = "user_operator"
SLEEPER_APP = "https://api.sleeper.app/v1"
SLEEPER_COM = "https://api.sleeper.com"
FANTASYPROS = "https://api.fantasypros.com/public/v2/json"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
FP_PPR_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
FP_IMAGE_KEYS = ("player_image_url", "player_square_image_url")
ADP_PREFIX = "adp"
PTS_PREFIX = "pts_"
FP_MIN_INTERVAL_S = 1.1

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def bind_user_id(
    real: str,
    operator_real_id: str | None,
    user_map: dict[str, str],
) -> str:
    if not real:
        return real
    if real in user_map:
        return user_map[real]
    if operator_real_id and real == operator_real_id:
        user_map[real] = OPERATOR_USER_ID
        return OPERATOR_USER_ID
    n = 1 + sum(1 for value in user_map.values() if value != OPERATOR_USER_ID)
    synthetic = f"user_{n:02d}"
    user_map[real] = synthetic
    return synthetic


def redact_league(
    league: dict[str, Any],
    *,
    synthetic_league_id: str,
    synthetic_draft_id: str,
    operator_real_id: str | None,
    user_map: dict[str, str],
) -> dict[str, Any]:
    out = json.loads(json.dumps(league))
    out["name"] = "League"
    out["league_id"] = synthetic_league_id
    out["draft_id"] = synthetic_draft_id
    out["previous_league_id"] = None
    out["last_author_display_name"] = None
    out["last_author_id"] = None
    out["last_author_avatar"] = None
    out["avatar"] = None
    out["last_message_id"] = None
    out["last_pinned_message_id"] = None
    out["last_read_id"] = None
    out["group_id"] = None
    if isinstance(out.get("metadata"), dict):
        meta = dict(out["metadata"])
        for key in ("latest_league_winner_roster_id",):
            meta.pop(key, None)
        out["metadata"] = meta
    _ = operator_real_id
    _ = user_map
    return out


def redact_draft(
    draft: dict[str, Any],
    *,
    synthetic_draft_id: str,
    synthetic_league_id: str | None,
    operator_real_id: str | None,
    user_map: dict[str, str],
) -> dict[str, Any]:
    out = json.loads(json.dumps(draft))
    out["draft_id"] = synthetic_draft_id
    out["league_id"] = synthetic_league_id
    out["last_message_id"] = None
    metadata = dict(out.get("metadata") or {})
    if "name" in metadata:
        metadata["name"] = "Draft"
    out["metadata"] = metadata
    order = out.get("draft_order") or {}
    if isinstance(order, dict):
        out["draft_order"] = {
            bind_user_id(uid, operator_real_id, user_map): slot
            for uid, slot in order.items()
        }
    creators = out.get("creators")
    if isinstance(creators, list):
        out["creators"] = [
            bind_user_id(str(uid), operator_real_id, user_map) for uid in creators
        ]
    return out


def redact_picks(
    picks: list[dict[str, Any]],
    *,
    synthetic_draft_id: str,
    operator_real_id: str | None,
    user_map: dict[str, str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pick in picks:
        row = json.loads(json.dumps(pick))
        row["draft_id"] = synthetic_draft_id
        picked_by = row.get("picked_by")
        if picked_by:
            row["picked_by"] = bind_user_id(str(picked_by), operator_real_id, user_map)
        else:
            row["picked_by"] = picked_by if picked_by is None else ""
        reactions = row.get("reactions")
        if isinstance(reactions, dict):
            row["reactions"] = {
                bind_user_id(str(uid), operator_real_id, user_map): emoji
                for uid, emoji in reactions.items()
            }
        out.append(row)
    return out


def redact_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": OPERATOR_USER_ID,
        "username": "operator",
        "display_name": "Operator",
        "avatar": None,
        "is_bot": bool(user.get("is_bot", False)),
    }


def keep_then_cap_by_group(
    items: list[Any],
    *,
    id_of: Any,
    group_of: Any,
    keep_ids: set[str],
    per_group: int,
    sort_key: Any = None,
) -> list[Any]:
    """Keep every item whose id is in keep_ids, then up to N more per group.

    Used by both player and projection fixture subsets.
    """
    ordered = sorted(items, key=sort_key) if sort_key is not None else list(items)
    out: list[Any] = []
    seen: set[str] = set()
    for item in ordered:
        ident = id_of(item)
        if not ident:
            continue
        if ident in keep_ids and ident not in seen:
            seen.add(ident)
            out.append(item)
    added: dict[Any, int] = {}
    for item in ordered:
        ident = id_of(item)
        if not ident or ident in seen:
            continue
        group = group_of(item)
        if added.get(group, 0) >= per_group:
            continue
        seen.add(ident)
        out.append(item)
        added[group] = added.get(group, 0) + 1
    return out


def subset_players(
    players: dict[str, Any],
    keep_ids: set[str],
    per_position: int = 8,
) -> dict[str, Any]:
    """Keep drafted ids, then up to ``per_position`` extra players per position."""

    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, int]:
        _pid, row = item
        yahoo = 0 if row.get("yahoo_id") not in (None, "") else 1
        rank = row.get("search_rank")
        search_rank = rank if isinstance(rank, int) else 999_999
        return (yahoo, search_rank)

    rows = [(pid, row) for pid, row in players.items() if isinstance(row, dict)]
    picked = keep_then_cap_by_group(
        rows,
        id_of=lambda item: item[0],
        group_of=lambda item: str(item[1].get("position") or ""),
        keep_ids=keep_ids,
        per_group=per_position,
        sort_key=sort_key,
    )
    return {pid: row for pid, row in picked}


def _is_market_only(stats: dict[str, Any]) -> bool:
    for key in stats:
        if key.startswith(ADP_PREFIX) or key.startswith(PTS_PREFIX) or key == "gp":
            continue
        return False
    return True


def subset_projections(
    rows: list[dict[str, Any]],
    keep_ids: set[str],
    per_position: int = 8,
) -> list[dict[str, Any]]:
    """Keep drafted ids, then up to N counting and N market-only rows per position."""

    def group_of(row: dict[str, Any]) -> tuple[str, str]:
        pos = str((row.get("player") or {}).get("position") or "")
        kind = "market" if _is_market_only(row.get("stats") or {}) else "counting"
        return (pos, kind)

    return keep_then_cap_by_group(
        rows,
        id_of=lambda row: str(row.get("player_id") or ""),
        group_of=group_of,
        keep_ids=keep_ids,
        per_group=per_position,
    )


def redact_fantasypros(payload: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(payload))
    for row in out.get("players") or []:
        if isinstance(row, dict):
            for key in FP_IMAGE_KEYS:
                row.pop(key, None)
    return out


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def fetch_json(client: httpx.Client, url: str) -> Any:
    response = client.get(url, timeout=120.0)
    response.raise_for_status()
    return response.json()


def _collect_player_ids(picks: list[dict[str, Any]]) -> set[str]:
    return {str(pick["player_id"]) for pick in picks if pick.get("player_id")}


def _unverified_ecr(
    players: dict[str, Any], *, scoring: str, position: str
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    ranked = [
        row
        for row in players.values()
        if isinstance(row, dict) and row.get("yahoo_id") not in (None, "")
    ]
    ranked.sort(
        key=lambda row: (
            row.get("search_rank")
            if isinstance(row.get("search_rank"), int)
            else 999_999
        )
    )
    for index, row in enumerate(ranked[:40], start=1):
        pos = str(row.get("position") or "WR")
        rows.append(
            {
                "player_id": int(row["player_id"])
                if str(row["player_id"]).isdigit()
                else index,
                "player_name": row.get("full_name")
                or f"{row.get('first_name', '')} {row.get('last_name', '')}".strip(),
                "player_team_id": row.get("team"),
                "player_position_id": pos,
                "player_positions": pos,
                "player_yahoo_id": str(row["yahoo_id"]),
                "player_bye_week": None,
                "rank_ecr": index,
                "rank_min": str(max(1, index - 2)),
                "rank_max": str(index + 4),
                "rank_ave": f"{index}.00",
                "rank_std": "2.00",
                "pos_rank": f"{pos}{index}",
            }
        )
    return {
        "sport": "NFL",
        "type": "Preseason",
        "year": "2026",
        "week": "0",
        "position_id": position,
        "scoring": scoring,
        "filters": None,
        "count": len(rows),
        "total_experts": 0,
        "last_updated": "unverified",
        "players": rows,
    }


def record(args: argparse.Namespace) -> list[str]:
    notes: list[str] = []
    fixtures = Path(args.out).resolve()
    headers = {"User-Agent": BROWSER_UA}
    user_map: dict[str, str] = {}
    operator_real_id: str | None = None
    all_picks: list[dict[str, Any]] = []

    with httpx.Client(headers=headers, follow_redirects=True) as client:
        user = fetch_json(client, f"{SLEEPER_APP}/user/{args.operator_username}")
        operator_real_id = str(user["user_id"])
        write_json(fixtures / "sleeper" / "user_operator.json", redact_user(user))

        scenarios = [
            (
                "snake_redraft",
                args.snake_draft,
                args.snake_league,
                "draft_snake_redraft",
                "league_snake_redraft",
            ),
            (
                "mock_standalone",
                args.mock_draft,
                None,
                "draft_mock_standalone",
                None,
            ),
            (
                "superflex",
                args.superflex_draft,
                args.superflex_league,
                "draft_superflex",
                "league_superflex",
            ),
            (
                "mid_draft",
                args.mid_draft,
                None,
                "draft_mid_draft",
                None,
            ),
        ]
        for name, draft_id, league_id, synth_draft, synth_league in scenarios:
            draft = fetch_json(client, f"{SLEEPER_APP}/draft/{draft_id}")
            picks = fetch_json(client, f"{SLEEPER_APP}/draft/{draft_id}/picks")
            if not isinstance(picks, list):
                raise SystemExit(f"{name} picks were not a list")
            redacted_draft = redact_draft(
                draft,
                synthetic_draft_id=synth_draft,
                synthetic_league_id=synth_league,
                operator_real_id=operator_real_id,
                user_map=user_map,
            )
            redacted_picks = redact_picks(
                picks,
                synthetic_draft_id=synth_draft,
                operator_real_id=operator_real_id,
                user_map=user_map,
            )
            write_json(fixtures / "sleeper" / f"draft_{name}.json", redacted_draft)
            write_json(fixtures / "sleeper" / f"picks_{name}.json", redacted_picks)
            all_picks.extend(picks)
            if league_id:
                league = fetch_json(client, f"{SLEEPER_APP}/league/{league_id}")
                write_json(
                    fixtures / "sleeper" / f"league_{name}.json",
                    redact_league(
                        league,
                        synthetic_league_id=synth_league or f"league_{name}",
                        synthetic_draft_id=synth_draft,
                        operator_real_id=operator_real_id,
                        user_map=user_map,
                    ),
                )

        print("fetching /players/nfl (~5MB, once)", file=sys.stderr)
        players = fetch_json(client, f"{SLEEPER_APP}/players/nfl")
        keep_ids = _collect_player_ids(all_picks)
        player_subset = subset_players(players, keep_ids=keep_ids, per_position=8)
        write_json(fixtures / "sleeper" / "players.json", player_subset)

        params = "&".join(f"position[]={pos}" for pos in POSITIONS)
        proj_url = (
            f"{SLEEPER_COM}/projections/nfl/{args.season}?season_type=regular&{params}"
        )
        print(f"fetching {proj_url}", file=sys.stderr)
        projections = fetch_json(client, proj_url)
        if not isinstance(projections, list):
            raise SystemExit("projections response was not a list")
        write_json(
            fixtures / "projections" / "season_regular.json",
            subset_projections(projections, keep_ids=keep_ids, per_position=6),
        )

        fp_notes = record_fantasypros(
            client,
            fixtures=fixtures,
            season=args.season,
            fp_key=args.fp_key or os.environ.get("FANTASYPROS_API_KEY"),
            headers=headers,
            player_subset=player_subset,
        )
        notes.extend(fp_notes)
    return notes


def record_fantasypros(
    client: httpx.Client,
    *,
    fixtures: Path,
    season: str,
    fp_key: str | None,
    headers: dict[str, str],
    player_subset: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []
    jobs = [
        ("PPR", pos, f"consensus_rankings_ppr_{pos.lower()}.json")
        for pos in FP_PPR_POSITIONS
    ]
    jobs.append(("PPR", "OP", "consensus_rankings_op.json"))
    fp_ok = False
    if fp_key:
        try:
            fp_headers = {**headers, "x-api-key": fp_key}
            for i, (scoring, position, filename) in enumerate(jobs):
                if i:
                    time.sleep(FP_MIN_INTERVAL_S)
                url = (
                    f"{FANTASYPROS}/nfl/{season}/consensus-rankings"
                    f"?position={position}&scoring={scoring}"
                )
                print(f"fetching {url}", file=sys.stderr)
                response = client.get(url, headers=fp_headers, timeout=60.0)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise SystemExit(f"FantasyPros {position} was not an object")
                write_json(
                    fixtures / "fantasypros" / filename,
                    redact_fantasypros(payload),
                )
            unverified = fixtures / "fantasypros" / "UNVERIFIED"
            if unverified.exists():
                unverified.unlink()
            stale = fixtures / "fantasypros" / "consensus_rankings_ppr.json"
            if stale.exists():
                stale.unlink()
            fp_ok = True
        except httpx.HTTPError as exc:
            notes.append(
                f"FantasyPros live fetch failed ({exc}). Wrote unverified fixtures."
            )
    if not fp_ok:
        if not fp_key:
            notes.append(
                "FantasyPros returned no live payload (no FANTASYPROS_API_KEY). "
                "Wrote unverified fixtures from the documented v2 shape."
            )
        subset = player_subset or {}
        write_json(
            fixtures / "fantasypros" / "consensus_rankings_ppr_qb.json",
            _unverified_ecr(subset, scoring="PPR", position="QB"),
        )
        write_json(
            fixtures / "fantasypros" / "consensus_rankings_op.json",
            _unverified_ecr(subset, scoring="PPR", position="OP"),
        )
        (fixtures / "fantasypros" / "UNVERIFIED").write_text(
            "Hand-written from the documented FantasyPros v2 "
            "consensus-rankings shape.\n"
            "Live fetch was not possible. Do not treat ranks as live ECR.\n",
            encoding="utf-8",
        )
    return notes


def _env_or_arg(value: str | None, env_name: str, flag: str) -> str:
    if value:
        return value
    env = os.environ.get(env_name)
    if env:
        return env
    raise SystemExit(f"missing {flag} (or set {env_name})")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snake-draft", default=os.environ.get("VORPAL_SNAKE_DRAFT"))
    parser.add_argument("--snake-league", default=os.environ.get("VORPAL_SNAKE_LEAGUE"))
    parser.add_argument("--mock-draft", default=os.environ.get("VORPAL_MOCK_DRAFT"))
    parser.add_argument(
        "--superflex-draft", default=os.environ.get("VORPAL_SUPERFLEX_DRAFT")
    )
    parser.add_argument(
        "--superflex-league", default=os.environ.get("VORPAL_SUPERFLEX_LEAGUE")
    )
    parser.add_argument("--mid-draft", default=os.environ.get("VORPAL_MID_DRAFT"))
    parser.add_argument(
        "--operator-username",
        default=os.environ.get("VORPAL_OPERATOR_USERNAME"),
    )
    parser.add_argument("--season", default="2026")
    parser.add_argument("--fp-key", default=os.environ.get("FANTASYPROS_API_KEY"))
    parser.add_argument("--out", default=str(FIXTURES))
    parser.add_argument(
        "--fp-only",
        action="store_true",
        help="Record only FantasyPros fixtures. Skips Sleeper and projections.",
    )
    args = parser.parse_args(argv)
    if args.fp_only:
        return args
    args.snake_draft = _env_or_arg(
        args.snake_draft, "VORPAL_SNAKE_DRAFT", "--snake-draft"
    )
    args.snake_league = _env_or_arg(
        args.snake_league, "VORPAL_SNAKE_LEAGUE", "--snake-league"
    )
    args.mock_draft = _env_or_arg(args.mock_draft, "VORPAL_MOCK_DRAFT", "--mock-draft")
    args.superflex_draft = _env_or_arg(
        args.superflex_draft, "VORPAL_SUPERFLEX_DRAFT", "--superflex-draft"
    )
    args.superflex_league = _env_or_arg(
        args.superflex_league, "VORPAL_SUPERFLEX_LEAGUE", "--superflex-league"
    )
    args.mid_draft = _env_or_arg(args.mid_draft, "VORPAL_MID_DRAFT", "--mid-draft")
    args.operator_username = _env_or_arg(
        args.operator_username, "VORPAL_OPERATOR_USERNAME", "--operator-username"
    )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.fp_only:
        fixtures = Path(args.out).resolve()
        headers = {"User-Agent": BROWSER_UA}
        with httpx.Client(headers=headers, follow_redirects=True) as client:
            notes = record_fantasypros(
                client,
                fixtures=fixtures,
                season=args.season,
                fp_key=args.fp_key or os.environ.get("FANTASYPROS_API_KEY"),
                headers=headers,
                player_subset=None,
            )
    else:
        notes = record(args)
    for note in notes:
        print(note, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
