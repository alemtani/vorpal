# ruff: noqa: E402, E501, I001
"""Live eval runner. Eleven gates, four policies, one report.

Three fixture families, four policies on each board:

- **golden** — 12 hand-built boards with a human forbid/require. Floor:
  did the rec avoid a mistake a stranger can name in one sentence?
- **regret** — 4 seats on completed public drafts. Wait-or-take: could
  we have had both names? Fail iff rec survived to our next pick and a
  listed alternative did not.
- **human** — 28 turns from the operator's own mocks. Agreement with
  what was clicked. No right answer. Not in the four-column table.

Policies, always in this order: model, argmax_vols, adp_follow,
ecr_follow. A gate where model and VOLS post the same rate has no
discriminating power (SPEC.md §5).

Eval path: `recommend` / `run_stability`. A violation is the score.
Draft night's `propose` is not used here.

Usage:
    uv run python -m evals.run
    uv run python -m evals.run --only golden
    uv run python -m evals.run --only regret
    uv run python -m evals.run --only human
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "tests" / "golden"))
sys.path.insert(0, str(ROOT / "tests" / "regret"))

from human_drafts import DRAFTS, SEAT, TEAMS, pick_no as snake_pick

from board import (  # noqa: E402
    CACHE,
    MOCK_SCORING_LEAGUE,
    REGRET_SOURCES,
    build_at_pick,
    forecast_for,
    human_config,
    human_resolved,
    load_players,
    match_player,
    operator_for,
    parse_recorded,
    resolve_recorded,
    score_pool,
    superflex_scoring,
)
from vorpal.contracts import (  # noqa: E402
    Gate,
    GateOutcome,
    GateResult,
    Payload,
    Proposal,
)
from vorpal.errors import PlatformError  # noqa: E402
from vorpal.evals import (  # noqa: E402
    BASELINES,
    GateFixtures,
    evaluate,
    render_report,
    score_results,
)
from vorpal.ingest import clear_caches  # noqa: E402
from vorpal.model import (  # noqa: E402
    AnthropicTransport,
    recommend,
    run_stability,
    validate_proposal,
)

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
REPORT = HERE / "REPORT.md"


@dataclass
class FixtureRun:
    name: str
    kind: str
    policy: str
    rec: str | None
    alts: tuple[str, ...]
    flags: tuple[str, ...]
    why: str
    coin_flip: bool
    error: str | None
    results: tuple[GateResult, ...]
    hint: str
    actually_picked: str | None = None
    case_why: str | None = None


class RetryTransport:
    """Retry transient model failures. Does not retry a scored violation."""

    def __init__(self, inner, retries: int = 6) -> None:
        self.inner = inner
        self.retries = retries

    def complete(self, payload: dict) -> dict:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                return self.inner.complete(payload)
            except PlatformError as exc:
                last = exc
                text = str(exc).lower()
                transient = any(
                    token in text
                    for token in ("429", "rate", "timeout", "overloaded", "529")
                )
                if not transient:
                    raise
                wait = min(60.0, 2.0**attempt)
                print(f"[retry] {exc}; sleeping {wait:.0f}s", flush=True)
                time.sleep(wait)
        assert last is not None
        raise last


class CaptureTransport:
    """Record every raw body so a raised recommend still leaves a proposal."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.raws: list[dict] = []

    def complete(self, payload: dict) -> dict:
        raw = self.inner.complete(payload)
        self.raws.append(raw if isinstance(raw, dict) else {"_non_object": True})
        return raw


class CachedTransport:
    """Replay saved raws. One file per fixture; never a sixth live call."""

    def __init__(self, raws: list[dict]) -> None:
        self.raws = list(raws)
        self.i = 0
        self.calls: list[dict] = []

    def complete(self, payload: dict) -> dict:
        self.calls.append(payload)
        if self.i >= len(self.raws):
            raise PlatformError("cache exhausted; will not open a live sixth call")
        raw = self.raws[self.i]
        self.i += 1
        return raw


def _payload_key(payload: Payload) -> str:
    blob = json.dumps(payload.to_dict(), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _cache_path(kind: str, name: str) -> Path:
    path = CACHE / kind
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{name}.json"


def ask_model(
    payload: Payload,
    live,
    *,
    kind: str,
    name: str,
    stability: bool,
) -> tuple[Proposal | None, tuple[str, ...] | None, str | None]:
    """One proposal and, when not a coin_flip, five ids.

    Uses `run_stability` when we need five. Does not call `propose`. A
    violation is captured and scored, never retried.
    """
    cache = _cache_path(kind, name)
    if cache.exists():
        saved = json.loads(cache.read_text())
        raws = saved["raws"]
        transport = CachedTransport(raws)
    else:
        transport = CaptureTransport(live)
        raws = transport.raws

    error: str | None = None
    proposal: Proposal | None = None
    five_ids: tuple[str, ...] | None = None

    try:
        if stability:
            five = run_stability(payload, transport)
            if five is None:
                # coin_flip on the first call. Recover that proposal from raws.
                proposal, _v = validate_proposal(payload, raws[0])
            else:
                proposal = five[0]
                five_ids = tuple(item.player_id for item in five)
        else:
            proposal = recommend(payload, transport)
    except PlatformError as exc:
        error = exc.message
        if raws:
            proposal, _v = validate_proposal(payload, raws[0])

    if not cache.exists() and raws:
        cache.write_text(
            json.dumps(
                {
                    "key": _payload_key(payload),
                    "raws": raws,
                    "error": error,
                    "coin_flip": bool(proposal and proposal.coin_flip),
                },
                indent=2,
            )
            + "\n"
        )
    return proposal, five_ids, error


def _result_row(
    *,
    name: str,
    kind: str,
    policy: str,
    payload: Payload,
    proposal: Proposal | None,
    error: str | None,
    fixtures: GateFixtures,
    actually_picked: str | None = None,
    case_why: str | None = None,
) -> FixtureRun:
    if proposal is None:
        scored = evaluate(payload, None, fixtures)
        scored = tuple(
            GateResult(Gate.SCHEMA, GateOutcome.FAIL, error or "no readable proposal")
            if row.gate is Gate.SCHEMA
            else row
            for row in scored
        )
        return FixtureRun(
            name=name,
            kind=kind,
            policy=policy,
            rec=None,
            alts=(),
            flags=(),
            why="",
            coin_flip=False,
            error=error,
            results=scored,
            hint=payload.hint_argmax_vols,
            actually_picked=actually_picked,
            case_why=case_why,
        )
    scored = evaluate(payload, proposal, fixtures)
    return FixtureRun(
        name=name,
        kind=kind,
        policy=policy,
        rec=proposal.player_id,
        alts=proposal.alternatives,
        flags=tuple(f.value for f in proposal.flags),
        why=proposal.why,
        coin_flip=proposal.coin_flip,
        error=error,
        results=scored,
        hint=payload.hint_argmax_vols,
        actually_picked=actually_picked,
        case_why=case_why,
    )


def run_policies(
    *,
    name: str,
    kind: str,
    payload: Payload,
    fixtures: GateFixtures,
    live,
    with_stability: bool,
    actually_picked: str | None = None,
    case_why: str | None = None,
) -> list[FixtureRun]:
    """Score the model and the three baselines on one board.

    Same payload, same gates. The model uses `recommend` (or
    `run_stability` for five ids). Baselines are deterministic:
    argmax_vols, adp_follow, ecr_follow. That is the four-column table.
    """
    out: list[FixtureRun] = []
    proposal, five_ids, error = ask_model(
        payload, live, kind=kind, name=name, stability=with_stability
    )
    model_fx = replace(fixtures, stability_ids=five_ids)
    out.append(
        _result_row(
            name=name,
            kind=kind,
            policy="model",
            payload=payload,
            proposal=proposal,
            error=error,
            fixtures=model_fx,
            actually_picked=actually_picked,
            case_why=case_why,
        )
    )
    for policy, fn in BASELINES.items():
        base = fn(payload)
        # Deterministic: five copies of the same id. coin_flip is always false.
        base_fx = replace(fixtures, stability_ids=(base.player_id,) * 5)
        out.append(
            _result_row(
                name=name,
                kind=kind,
                policy=policy,
                payload=payload,
                proposal=base,
                error=None,
                fixtures=base_fx,
                actually_picked=actually_picked,
                case_why=case_why,
            )
        )
    return out


def run_golden(live) -> list[FixtureRun]:
    """12 human verdicts. This family is in the four-column table.

    Each case forbids picks nobody needs a model to rule out, and
    requires that the rec or an alternative name one of a must-see set.
    `argmax_vols` already passes 9 of 12; only three cases can show the
    model is doing anything. pytest -m golden checks the cases, not the
    live model.
    """
    from cases import CASES

    runs: list[FixtureRun] = []
    for case in CASES:
        print(f"[golden] {case.name}", flush=True)
        # Hand-written boards have no full pool. VOLS invariant stays skipped.
        fixtures = case.fixtures()
        runs.extend(
            run_policies(
                name=case.name,
                kind="golden",
                payload=case.payload,
                fixtures=fixtures,
                live=live,
                with_stability=True,
                case_why=case.why,
            )
        )
    return runs


def run_regret(live, fp_key: str, players) -> list[FixtureRun]:
    """Wait-or-take on completed drafts. This family is in the table.

    Not "was the pick good." Fail iff rec was still available at our
    next pick and a listed alternative was gone — we could have had
    both. Golden forbid/require skip; there is no human verdict here.
    Frozen board: we substitute our rec and leave the other seats as
    recorded. Floor, not a simulation.
    """
    from replay import all_fixtures

    runs: list[FixtureRun] = []
    # Group by draft so the forecast is fetched once per recorded league.
    by_draft: dict[str, list] = {}
    for fixture in all_fixtures():
        by_draft.setdefault(fixture.draft_id, []).append(fixture)

    for draft_id, fixtures in by_draft.items():
        stem, league_stem = REGRET_SOURCES[draft_id]
        scoring_stem = league_stem if league_stem else MOCK_SCORING_LEAGUE
        draft, league, all_picks = parse_recorded(stem, league_stem)
        scoring_league = None
        if league is None:
            _, scoring_league, _ = parse_recorded(scoring_stem, scoring_stem)

        print(f"[regret] forecast for {draft_id} season={draft.season}", flush=True)
        clear_caches()
        operator = operator_for(draft, fixtures[0].draft_slot)
        seed = resolve_recorded(
            draft,
            league=league,
            scoring_league=scoring_league,
            operator=operator,
            picks=all_picks,
        )
        stats, ecr_rows, banners, season_used = forecast_for(
            draft, seed, players, fp_api_key=fp_key
        )
        print(
            f"[regret] season_used={season_used} stats={len(stats)} ecr={len(ecr_rows)} "
            f"banners={[b.code for b in banners]}",
            flush=True,
        )
        resolved = resolve_recorded(
            draft,
            league=league,
            scoring_league=scoring_league,
            operator=operator,
            picks=all_picks,
            stat_columns=frozenset(k for row in stats for k in row.stats),
        )
        pool = score_pool(stats, ecr_rows, players, resolved, draft.host)
        adp = {row.player_id: row.adp for row in stats if row.adp is not None}
        ecr = {row.player_id: row for row in ecr_rows}

        for fixture in fixtures:
            print(
                f"[regret] {fixture.name} pick={fixture.pick_no} era={fixture.era[:40]}...",
                flush=True,
            )
            before = tuple(p for p in all_picks if p.pick_no < fixture.pick_no)
            built = build_at_pick(
                resolved=resolved,
                picks_before=before,
                pool=pool,
                adp=adp,
                ecr=ecr,
                pick_no=fixture.pick_no,
            )
            payload: Payload = built.payload
            board_ids = [row.player_id for row in payload.board]
            gate_fx = replace(
                fixture.gate_fixtures(board_ids),
                replacement_rank_delta=built.rank_delta,
            )
            runs.extend(
                run_policies(
                    name=fixture.name,
                    kind="regret",
                    payload=payload,
                    fixtures=gate_fx,
                    live=live,
                    with_stability=True,
                    actually_picked=fixture.actually_picked,
                    case_why=fixture.provenance,
                )
            )
    return runs


def run_human(live, fp_key: str, players) -> list[FixtureRun]:
    """Replay the operator's two seat-1 mocks. Not in the four-column table.

    28 turns, freeze the board, ask what each policy would rec, record
    `actually_picked`. Agreement with a click, not a right/wrong
    verdict. No forbid/require, no per-pick why. Until a human writes
    one, keep these out of the pass-rate table.

    Recommend once; no fifth call. Stability on 14 picks times two
    drafts is 140 extra calls.
    """
    from types import SimpleNamespace

    from vorpal.contracts import Host
    from vorpal.contracts import Pick as PickType

    scoring = superflex_scoring()
    config = human_config(scoring)
    resolved = human_resolved(config)
    print("[human] loading 2026 OP forecast", flush=True)
    clear_caches()
    seed = SimpleNamespace(config=config, ecr_position="OP")
    draft = SimpleNamespace(season="2026")
    stats, ecr_rows, banners, season = forecast_for(
        draft, seed, players, fp_api_key=fp_key
    )
    print(
        f"[human] season={season} stats={len(stats)} ecr={len(ecr_rows)} "
        f"banners={[b.code for b in banners]}",
        flush=True,
    )
    pool = score_pool(stats, ecr_rows, players, resolved, Host.SLEEPER)
    adp = {row.player_id: row.adp for row in stats if row.adp is not None}
    ecr = {row.player_id: row for row in ecr_rows}

    runs: list[FixtureRun] = []
    unmatched: list[str] = []
    for draft_name, rows in DRAFTS.items():
        mapped: list[tuple[int, int, int, object]] = []
        for round_no, slot, name, pos, team in rows:
            player = match_player(name, pos, team, players)
            if player is None:
                unmatched.append(
                    f"{draft_name} {round_no}.{slot:02d} {name} {pos}-{team}"
                )
                continue
            pn = snake_pick(round_no, slot, TEAMS)
            mapped.append((pn, round_no, slot, player))
        mapped.sort()
        if unmatched:
            print(f"[human] unmatched so far: {unmatched[-5:]}", flush=True)

        picks_all = []
        for pn, round_no, slot, player in mapped:
            first, _, last = player.name.partition(" ")
            picks_all.append(
                PickType(
                    draft_id=draft_name,
                    player_id=player.player_id,
                    picked_by="operator" if slot == SEAT else "",
                    roster_id=slot,
                    round=round_no,
                    draft_slot=slot,
                    pick_no=pn,
                    is_keeper=None,
                    position=player.position,
                    team=player.team,
                    first_name=player.first_name,
                    last_name=player.last_name,
                )
            )

        seat_picks = [p for p in picks_all if p.draft_slot == SEAT]
        for mine in seat_picks:
            name = f"{draft_name}_r{mine.round:02d}"
            print(
                f"[human] {name} overall={mine.pick_no} took={mine.player_id}",
                flush=True,
            )
            before = tuple(p for p in picks_all if p.pick_no < mine.pick_no)
            built = build_at_pick(
                resolved=resolved,
                picks_before=before,
                pool=pool,
                adp=adp,
                ecr=ecr,
                pick_no=mine.pick_no,
            )
            board_ids = [row.player_id for row in built.payload.board]
            # Survival to the next seat-1 pick. Last round has none.
            later = [p for p in seat_picks if p.pick_no > mine.pick_no]
            if later:
                nxt = later[0].pick_no
                taken = {
                    p.player_id for p in picks_all if mine.pick_no < p.pick_no < nxt
                }
                available = frozenset(pid for pid in board_ids if pid not in taken)
                gate_fx = GateFixtures(
                    available_at_next=available,
                    replacement_rank_delta=built.rank_delta,
                )
            else:
                gate_fx = GateFixtures(replacement_rank_delta=built.rank_delta)
            runs.extend(
                run_policies(
                    name=name,
                    kind="human",
                    payload=built.payload,
                    fixtures=gate_fx,
                    live=live,
                    with_stability=False,
                    actually_picked=mine.player_id,
                )
            )
    if unmatched:
        (RESULTS / "unmatched_human.txt").write_text("\n".join(unmatched) + "\n")
        print(
            f"[human] {len(unmatched)} unmatched names; see results/unmatched_human.txt",
            flush=True,
        )
    return runs


def _serialize(run: FixtureRun) -> dict:
    return {
        "name": run.name,
        "kind": run.kind,
        "policy": run.policy,
        "rec": run.rec,
        "alts": list(run.alts),
        "flags": list(run.flags),
        "why": run.why,
        "coin_flip": run.coin_flip,
        "error": run.error,
        "hint": run.hint,
        "actually_picked": run.actually_picked,
        "case_why": run.case_why,
        "results": [
            {"gate": r.gate.value, "outcome": r.outcome.value, "reason": r.reason}
            for r in run.results
        ],
    }


def _by_policy(
    runs: Sequence[FixtureRun], kind: str | None = None
) -> dict[str, list[GateResult]]:
    out: dict[str, list[GateResult]] = {
        "model": [],
        "argmax_vols": [],
        "adp_follow": [],
        "ecr_follow": [],
    }
    for run in runs:
        if kind is not None and run.kind != kind:
            continue
        out.setdefault(run.policy, []).extend(run.results)
    return out


def write_report(runs: list[FixtureRun]) -> str:
    """Four-column table is golden + regret only. Human is sidecar JSON."""
    table_runs = [r for r in runs if r.kind in {"golden", "regret"}]
    table = render_report(_by_policy(table_runs))
    scores = score_results(_by_policy(table_runs))

    lines: list[str] = []
    lines.append("# S10 eval report")
    lines.append("")
    lines.append(
        "Live model. Eval path (`recommend` / `run_stability`), never `propose`."
    )
    lines.append("")
    lines.append("## Four-column table")
    lines.append("")
    lines.append("Fixtures: 12 golden cases + 4 regret seats. Pass rate ignores")
    lines.append("`NOT_PERFORMED`. `s=N` is the skip count. A matching model and")
    lines.append("`argmax_vols` rate is marked `NO DISCRIMINATING POWER`.")
    lines.append("")
    lines.append("```")
    lines.append(table.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("### Counts (pass / fail / skip)")
    lines.append("")
    lines.append("| gate | model | argmax_vols | adp_follow | ecr_follow | separates |")
    lines.append("|---|---|---|---|---|---|")
    for score in scores:
        cells = []
        for policy in ("model", "argmax_vols", "adp_follow", "ecr_follow"):
            p, f, s = score.counts[policy]
            cells.append(f"{p}/{f}/{s}")
        flag = "yes" if score.separates() else "no"
        lines.append(f"| `{score.gate.value}` | " + " | ".join(cells) + f" | {flag} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=("golden", "regret", "human"),
        default=None,
        help="run one fixture family",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY unset", file=sys.stderr)
        return 2
    fp_key = os.environ.get("FANTASYPROS_API_KEY")
    RESULTS.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    live = RetryTransport(AnthropicTransport())
    all_runs: list[FixtureRun] = []

    try:
        if args.only in (None, "golden"):
            all_runs.extend(run_golden(live))
            (RESULTS / "golden.json").write_text(
                json.dumps(
                    [_serialize(r) for r in all_runs if r.kind == "golden"], indent=2
                )
                + "\n"
            )
        if args.only in (None, "regret"):
            if not fp_key:
                print("FANTASYPROS_API_KEY unset; skipping regret", file=sys.stderr)
            else:
                print("[setup] fetching /players", flush=True)
                players = load_players()
                print(f"[setup] {len(players)} players", flush=True)
                all_runs.extend(run_regret(live, fp_key, players))
                (RESULTS / "regret.json").write_text(
                    json.dumps(
                        [_serialize(r) for r in all_runs if r.kind == "regret"],
                        indent=2,
                    )
                    + "\n"
                )
        if args.only in (None, "human"):
            if not fp_key:
                print("FANTASYPROS_API_KEY unset; skipping human", file=sys.stderr)
            else:
                if "players" not in dir():
                    print("[setup] fetching /players", flush=True)
                    players = load_players()
                all_runs.extend(run_human(live, fp_key, players))
                (RESULTS / "human.json").write_text(
                    json.dumps(
                        [_serialize(r) for r in all_runs if r.kind == "human"], indent=2
                    )
                    + "\n"
                )
    except Exception:
        traceback.print_exc()
        (RESULTS / "partial.json").write_text(
            json.dumps([_serialize(r) for r in all_runs], indent=2) + "\n"
        )
        raise

    (RESULTS / "all.json").write_text(
        json.dumps([_serialize(r) for r in all_runs], indent=2) + "\n"
    )
    print(render_report(_by_policy(all_runs, kind=None)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
