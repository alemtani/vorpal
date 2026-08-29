"""Recorded fixtures cover the seed scenarios. They are redacted."""

from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SLEEPER = FIXTURES / "sleeper"

# Sleeper user/draft snowflakes are 15+ digits. Player ids are short.
SNOWFLAKE = re.compile(r'"[0-9]{15,}"')


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_snake_redraft_is_league_attached() -> None:
    draft = _load(SLEEPER / "draft_snake_redraft.json")
    league = _load(SLEEPER / "league_snake_redraft.json")
    assert isinstance(draft, dict)
    assert isinstance(league, dict)
    assert draft["type"] == "snake"
    assert draft["league_id"] == "league_snake_redraft"
    assert league["league_id"] == "league_snake_redraft"
    assert league["settings"]["type"] == 0
    assert "K" in league["roster_positions"]
    assert "DEF" in league["roster_positions"]
    assert draft["settings"]["slots_k"] == 1
    assert draft["settings"]["slots_def"] == 1
    assert "SUPER_FLEX" not in league["roster_positions"]


def test_standalone_mock_has_null_league_id() -> None:
    draft = _load(SLEEPER / "draft_mock_standalone.json")
    assert isinstance(draft, dict)
    assert draft["league_id"] is None
    assert draft["type"] == "snake"
    assert (SLEEPER / "league_mock_standalone.json").exists() is False


def test_superflex_league_has_super_flex_slot() -> None:
    draft = _load(SLEEPER / "draft_superflex.json")
    league = _load(SLEEPER / "league_superflex.json")
    assert isinstance(draft, dict)
    assert isinstance(league, dict)
    assert draft["settings"]["slots_super_flex"] == 1
    assert "SUPER_FLEX" in league["roster_positions"]
    assert league["settings"]["type"] == 0


def test_k_or_dst_slot_exists_on_snake_redraft() -> None:
    draft = _load(SLEEPER / "draft_snake_redraft.json")
    assert isinstance(draft, dict)
    assert draft["settings"]["slots_k"] == 1 or draft["settings"]["slots_def"] == 1


def test_mid_draft_picks_are_partial() -> None:
    draft = _load(SLEEPER / "draft_mid_draft.json")
    picks = _load(SLEEPER / "picks_mid_draft.json")
    assert isinstance(draft, dict)
    assert isinstance(picks, list)
    total = draft["settings"]["teams"] * draft["settings"]["rounds"]
    assert 0 < len(picks) < total
    assert draft["status"] in {"paused", "drafting", "pre_draft"}


def test_operator_user_is_synthetic() -> None:
    user = _load(SLEEPER / "user_operator.json")
    assert isinstance(user, dict)
    assert user["user_id"] == "user_operator"
    assert user["username"] == "operator"
    assert user["display_name"] == "Operator"


def test_projections_are_season_totals_from_one_company() -> None:
    rows = _load(FIXTURES / "projections" / "season_regular.json")
    assert isinstance(rows, list)
    assert rows
    companies = {row["company"] for row in rows}
    assert companies == {"rotowire"}
    assert all(row["week"] is None for row in rows)
    assert any(
        any(key.startswith("pts_") for key in (row.get("stats") or {})) for row in rows
    ), "raw pts_* keys stay on the fixture so ingest can refuse them"


def test_players_include_yahoo_id_and_no_bye_field() -> None:
    players = _load(SLEEPER / "players.json")
    assert isinstance(players, dict)
    assert any(row.get("yahoo_id") not in (None, "") for row in players.values())
    assert all(not any("bye" in key.lower() for key in row) for row in players.values())


def test_fantasypros_live_rows_have_yahoo_std_and_bye() -> None:
    fp = FIXTURES / "fantasypros"
    assert not (fp / "UNVERIFIED").exists()
    overall = _load(fp / "consensus_rankings_ppr.json")
    op = _load(fp / "consensus_rankings_op.json")
    assert isinstance(overall, dict)
    assert isinstance(op, dict)
    assert overall["position_id"] == "ALL"
    assert op["position_id"] == "OP"
    assert overall.get("public_api_limited") is True
    assert overall.get("limit") == 10
    players = overall["players"]
    assert isinstance(players, list)
    assert players
    row = players[0]
    assert "rank_ecr" in row
    assert "rank_std" in row
    assert "rank_min" in row
    assert "rank_max" in row
    assert row.get("player_yahoo_id") not in (None, "")
    assert row.get("player_bye_week") not in (None, "")
    assert "player_image_url" not in row
    assert "player_square_image_url" not in row


def test_fixtures_do_not_identify_a_league_or_manager() -> None:
    for path in FIXTURES.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        if path.parent.name != "sleeper":
            continue
        data = json.loads(text)
        if path.name.startswith("league_"):
            assert isinstance(data, dict)
            assert data.get("name") == "League", path
            assert data.get("last_author_display_name") in (None, "")
            assert data.get("last_author_id") in (None, "")
        if path.name.startswith("draft_"):
            assert isinstance(data, dict)
            meta = data.get("metadata") or {}
            if "name" in meta:
                assert meta["name"] == "Draft", path
        if path.name.startswith(("draft_", "picks_", "user_")):
            for match in SNOWFLAKE.findall(text):
                raise AssertionError(f"snowflake user id left in {path}: {match}")
