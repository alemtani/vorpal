"""Completed-draft snapshot. Redacted JSON, no live model call."""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from vorpal.contracts import IDENTITY_KEYS, Payload, Pick, Proposal

TURN_KEYS = {"pick_no", "payload", "proposal", "human_pick"}
SRC_VORPAL = Path(__file__).resolve().parents[2] / "src" / "vorpal"


def _keys(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        found.update(obj)
        for value in obj.values():
            found.update(_keys(value))
    elif isinstance(obj, list):
        for value in obj:
            found.update(_keys(value))
    return found


def test_redaction_drops_player_names_and_keeps_ids(
    make_payload: Callable[..., Payload],
) -> None:
    from vorpal.board.snapshot import redact

    payload = make_payload()
    raw = payload.to_dict()
    assert any(row.get("name") == "A Back" for row in raw["board"])
    out = redact(raw)
    assert "name" not in _keys(out)
    board_ids = {row["player_id"] for row in out["board"]}
    assert board_ids == {"p1", "p2", "p3"}
    assert out["state"]["user_roster"][0]["player_id"] == "p0"
    dumped = json.dumps(out)
    assert "A Back" not in dumped
    assert "Held Back" not in dumped
    assert "B Receiver" not in dumped


def test_redaction_drops_league_id_and_manager_identity(
    make_payload: Callable[..., Payload],
) -> None:
    from vorpal.board.snapshot import redact

    blob = make_payload().to_dict()
    blob["config"]["league_id"] = "league_secret"
    blob["config"]["scoring_league_id"] = "league_secret"
    blob["config"]["draft_id"] = "draft_secret"
    blob["picked_by"] = "alex"
    blob["display_name"] = "Alex T"
    blob["username"] = "alemtani"
    blob["user_id"] = "user_real"
    out = redact(blob)
    assert IDENTITY_KEYS.isdisjoint(_keys(out))
    dumped = json.dumps(out)
    assert "league_secret" not in dumped
    assert "draft_secret" not in dumped
    assert "alemtani" not in dumped
    assert "Alex T" not in dumped


def test_snapshot_file_shape_is_payload_proposal_human_pick_pick_numbers(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.snapshot import SnapshotCollector, snapshot_path_for

    payload = make_payload(pick_no=1, picks_until_next=0, next_user_pick=1)
    proposal = make_proposal(player_id="p1")
    collector = SnapshotCollector()
    collector.observe(Frame(payload=payload, proposal=proposal, banners=()))
    path = snapshot_path_for(tmp_path / "board.html")
    collector.write(path, (make_pick(pick_no=1, player_id="p9"),))
    assert path.name == "board.snapshot.local.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert set(body) == {"picks"}
    assert len(body["picks"]) == 1
    turn = body["picks"][0]
    assert set(turn) == TURN_KEYS
    assert turn["pick_no"] == 1
    assert turn["human_pick"] == "p9"
    assert turn["proposal"]["player_id"] == "p1"
    assert turn["proposal"]["alternatives"] == ["p2"]
    assert "name" not in _keys(turn)
    assert IDENTITY_KEYS.isdisjoint(_keys(turn))
    assert not (tmp_path / "board.snapshot.local.json.tmp").exists()


def test_snapshot_omits_other_seats_and_keeps_agreement_picks(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.snapshot import SnapshotCollector

    payload = make_payload(pick_no=2, picks_until_next=0, next_user_pick=2, slot=2)
    collector = SnapshotCollector()
    collector.observe(
        Frame(payload=payload, proposal=make_proposal(player_id="p1"), banners=())
    )
    other = make_pick(pick_no=1, player_id="p8", draft_slot=1)
    agreed = make_pick(pick_no=2, player_id="p1")
    path = tmp_path / "board.snapshot.local.json"
    collector.write(path, (other, agreed))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert [turn["human_pick"] for turn in body["picks"]] == ["p1"]
    assert body["picks"][0]["proposal"]["player_id"] == "p1"


def test_unknown_seat_writes_no_human_picks(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.snapshot import SnapshotCollector

    payload = make_payload(slot=None, picks_until_next=None)
    collector = SnapshotCollector()
    collector.observe(Frame(payload=payload, proposal=make_proposal(), banners=()))
    path = tmp_path / "out.snapshot.local.json"
    collector.write(path, (make_pick(),))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body == {"picks": []}


def test_off_clock_frame_still_records_the_click_without_a_rec(
    tmp_path: Path,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_pick: Callable[..., Pick],
) -> None:
    from vorpal.board import Frame
    from vorpal.board.snapshot import SnapshotCollector

    payload = make_payload(pick_no=1, picks_until_next=5, next_user_pick=6)
    collector = SnapshotCollector()
    collector.observe(
        Frame(payload=payload, proposal=make_proposal(player_id="p1"), banners=())
    )
    path = tmp_path / "board.snapshot.local.json"
    collector.write(path, (make_pick(pick_no=1, player_id="p9"),))
    turn = json.loads(path.read_text(encoding="utf-8"))["picks"][0]
    assert turn["human_pick"] == "p9"
    assert turn["pick_no"] == 1
    assert turn["payload"] is None
    assert turn["proposal"] is None


def _literal_strings(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            found.add(child.value)
    return found


def test_board_and_valuation_do_not_own_a_host_identity_table() -> None:
    """Sleeper wire identity names are not a second table in board/valuation.

    Adapters map host JSON onto contract fields. IDENTITY_KEYS lives on those
    generic types. A frozenset/set/dict literal that names both picked_by and
    display_name is a host denylist — allowed only in platform/ and ingest.
    """

    hits: list[str] = []
    for package in ("board", "valuation"):
        root = SRC_VORPAL / package
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.Set, ast.List, ast.Tuple, ast.Dict, ast.Call)
                ):
                    continue
                strings = _literal_strings(node)
                if "picked_by" in strings and "display_name" in strings:
                    rel = path.relative_to(SRC_VORPAL)
                    hits.append(f"{rel}:{node.lineno}")
    assert hits == []


def test_snapshot_identity_keys_are_the_contract_set() -> None:
    from vorpal.board import snapshot

    assert snapshot.IDENTITY_KEYS is IDENTITY_KEYS
    assert "player_id" not in IDENTITY_KEYS


def test_redact_follows_the_contract_identity_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vorpal.board.snapshot import redact

    leaked = {
        "display_name": "Alex T",
        "picked_by": "user_real",
        "player_id": "p1",
        "espn_owner_guid": "espn-secret",
    }
    out = redact(leaked)
    assert "display_name" not in out
    assert "picked_by" not in out
    assert out["player_id"] == "p1"
    # Not a contract field. Adapters map host wire onto the generic names;
    # board does not own an ESPN denylist.
    assert out["espn_owner_guid"] == "espn-secret"

    monkeypatch.setattr(
        "vorpal.board.snapshot.IDENTITY_KEYS",
        IDENTITY_KEYS | frozenset({"espn_owner_guid"}),
    )
    dropped = redact(leaked)
    assert "espn_owner_guid" not in dropped
    assert dropped["player_id"] == "p1"
