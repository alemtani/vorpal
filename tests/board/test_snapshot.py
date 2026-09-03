"""Completed-draft snapshot. Redacted JSON, no live model call."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vorpal.contracts import Payload, Pick, Proposal

IDENTITY_KEYS = frozenset(
    {
        "league_id",
        "scoring_league_id",
        "draft_id",
        "picked_by",
        "display_name",
        "username",
        "user_id",
        "first_name",
        "last_name",
        "name",
    }
)
TURN_KEYS = {"pick_no", "payload", "proposal", "human_pick"}


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
