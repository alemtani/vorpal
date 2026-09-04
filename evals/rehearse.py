# ruff: noqa: E501
"""Dress rehearsal: live CLI against a real mock, timed against pick_timer.

Does not write league ids to the report files. Pass scoring-league-id on the
command line; it is required when the mock has league_id null, unless you
borrow a preset table with --scoring instead.

The flags here mirror `vorpal.cli.build_parser`. A flag the operator types on
draft night must be one the rehearsal can run, so --fast, --scoring, and
--trace pass straight through. Keep the two parsers in step.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vorpal.cli import main  # noqa: E402
from vorpal.model import AnthropicTransport  # noqa: E402
from vorpal.platform.presets import PRESETS  # noqa: E402
from vorpal.sleeper import SleeperClient  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "_cache" / "rehearsal"


class TimedTransport:
    def __init__(self, inner, events: list) -> None:
        self.inner = inner
        self.events = events
        self.t0 = time.monotonic()

    def complete(self, payload: dict) -> dict:
        start = time.monotonic()
        pick_no = None
        try:
            pick_no = payload.get("state", {}).get("pick_no")
        except Exception:
            pick_no = None
        try:
            out = self.inner.complete(payload)
        except Exception as exc:
            self.events.append(
                {
                    "t": time.monotonic() - self.t0,
                    "kind": "model_error",
                    "seconds": time.monotonic() - start,
                    "pick_no": pick_no,
                    "error": type(exc).__name__,
                }
            )
            raise
        self.events.append(
            {
                "t": time.monotonic() - self.t0,
                "kind": "model_ok",
                "seconds": time.monotonic() - start,
                "pick_no": pick_no,
                "rec": out.get("player_id") if isinstance(out, dict) else None,
            }
        )
        print(
            f"[rehearse] model {time.monotonic() - start:.1f}s pick_no={pick_no} rec={out.get('player_id') if isinstance(out, dict) else None}",
            flush=True,
        )
        return out


class TimedClient:
    def __init__(self, inner: SleeperClient, events: list) -> None:
        self.inner = inner
        self.events = events
        self.t0 = time.monotonic()

    def _mark(self, kind: str, **extra) -> None:
        row = {"t": time.monotonic() - self.t0, "kind": kind, **extra}
        self.events.append(row)
        print(f"[rehearse] {kind} t={row['t']:.1f}s {extra}", flush=True)

    def get_draft(self, draft_id: str):
        draft = self.inner.get_draft(draft_id)
        self._mark(
            "get_draft",
            status=draft.status,
            pick_timer=draft.pick_timer,
            teams=draft.teams,
        )
        return draft

    def get_picks(self, draft_id: str):
        picks = self.inner.get_picks(draft_id)
        self._mark("get_picks", n=len(picks))
        return picks

    def get_league(self, league_id: str):
        league = self.inner.get_league(league_id)
        self._mark("get_league")
        return league

    def get_user(self, name_or_id: str):
        user = self.inner.get_user(name_or_id)
        self._mark("get_user")
        return user

    def get_players(self):
        players = self.inner.get_players()
        self._mark("get_players", n=len(players))
        return players

    def close(self) -> None:
        self.inner.close()


def main_argv(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--operator", required=True)
    # Same pair as the CLI: a league to borrow from, or a preset table. Never both.
    scoring = parser.add_mutually_exclusive_group()
    scoring.add_argument("--scoring-league-id", default=None)
    scoring.add_argument("--scoring", default=None, choices=PRESETS)
    parser.add_argument("--slot", type=int, default=None)
    parser.add_argument(
        "--fast",
        action="store_true",
        help="rehearse fast mode, including its fallback to standard speed",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="send propose traces to LangSmith. Needs LANGSMITH_API_KEY",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=900.0,
        help="stop the poll loop after this many seconds",
    )
    args, _unknown = parser.parse_known_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    t0 = time.monotonic()
    deadline = t0 + args.max_seconds
    board = OUT_DIR / "board.html"

    inner = SleeperClient(players_cache_path=HERE / "_cache" / "sleeper_players.json")
    client = TimedClient(inner, events)
    transport = TimedTransport(AnthropicTransport(fast=args.fast), events)

    cli_argv = [
        "--draft-id",
        args.draft_id,
        "--operator",
        args.operator,
        "--out",
        str(board),
        "--players-cache",
        str(HERE / "_cache" / "sleeper_players.json"),
    ]
    if args.scoring_league_id:
        cli_argv.extend(["--scoring-league-id", args.scoring_league_id])
    if args.scoring:
        cli_argv.extend(["--scoring", args.scoring])
    if args.slot is not None:
        cli_argv.extend(["--slot", str(args.slot)])
    if args.fast:
        cli_argv.append("--fast")
    if args.trace:
        cli_argv.append("--trace")

    def sleep(seconds: float) -> None:
        events.append({"t": time.monotonic() - t0, "kind": "sleep", "seconds": seconds})
        # Bound the wait so --max-seconds is honoured.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise KeyboardInterrupt
        time.sleep(min(seconds, remaining))
        if time.monotonic() >= deadline:
            raise KeyboardInterrupt

    print(f"[rehearse] start max={args.max_seconds}s", flush=True)
    code = 0
    try:
        code = main(
            cli_argv,
            client=client,
            transport=transport,
            sleep=sleep,
            now=time.monotonic,
        )
    except KeyboardInterrupt:
        print("[rehearse] stopped on deadline or interrupt", flush=True)
        code = 0
    wall = time.monotonic() - t0
    events.append(
        {"t": wall, "kind": "done", "code": code, "board_exists": board.exists()}
    )
    (OUT_DIR / "events.json").write_text(json.dumps(events, indent=2) + "\n")
    print(f"[rehearse] wall {wall:.1f}s code={code} board={board.exists()}", flush=True)
    model_times = [e["seconds"] for e in events if e.get("kind") == "model_ok"]
    if model_times:
        print(
            f"[rehearse] model calls {len(model_times)} "
            f"min={min(model_times):.1f}s max={max(model_times):.1f}s "
            f"mean={sum(model_times) / len(model_times):.1f}s",
            flush=True,
        )
    return code


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY unset", file=sys.stderr)
        raise SystemExit(2)
    if not os.environ.get("FANTASYPROS_API_KEY"):
        print("FANTASYPROS_API_KEY unset", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main_argv())
