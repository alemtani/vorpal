"""LeagueHost is the generic adapter. SleeperHost is the v1 implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vorpal.contracts import Draft, LeagueFormat, Player, Slot
from vorpal.errors import PlatformError
from vorpal.platform import LeagueHost, SleeperHost

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sleeper"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _parse_draft(host: LeagueHost, payload: dict[str, Any]) -> Draft:
    """Callers depend on LeagueHost, not on SleeperHost."""
    return host.parse_draft(payload)


def test_league_host_cannot_be_constructed() -> None:
    with pytest.raises(TypeError):
        LeagueHost()  # type: ignore[abstract]


def test_sleeper_host_is_a_league_host() -> None:
    host = SleeperHost()
    assert isinstance(host, LeagueHost)
    assert host.name == "sleeper"


def test_parse_snake_redraft_draft_from_fixture() -> None:
    host = SleeperHost()
    draft = _parse_draft(host, _load("draft_snake_redraft.json"))
    assert draft.host == "sleeper"
    assert draft.draft_id == "draft_snake_redraft"
    assert draft.league_id == "league_snake_redraft"
    assert draft.type == "snake"
    assert draft.teams == 12
    assert draft.rounds == 15
    assert draft.pick_timer == 60
    assert draft.reversal_round == 0
    assert draft.slot_counts.k == 1
    assert draft.slot_counts.defense == 1
    assert draft.slot_counts.super_flex == 0
    assert draft.slot_counts.bn == 5
    assert draft.slot_to_roster_id[1] == 2
    assert draft.scoring_label == "ppr"
    assert "user_operator" in (draft.draft_order or {})


def test_parse_standalone_mock_keeps_null_league_id() -> None:
    draft = SleeperHost().parse_draft(_load("draft_mock_standalone.json"))
    assert draft.league_id is None
    assert draft.slot_counts.k == 1
    assert draft.slot_counts.defense == 1


def test_parse_superflex_slot_counts() -> None:
    draft = SleeperHost().parse_draft(_load("draft_superflex.json"))
    assert draft.slot_counts.super_flex == 1
    assert draft.slot_counts.defense == 0
    assert draft.scoring_label == "2qb"


def test_parse_mid_draft_absent_bench_and_zero_k() -> None:
    draft = SleeperHost().parse_draft(_load("draft_mid_draft.json"))
    assert draft.status == "paused"
    assert draft.slot_counts.bn is None
    assert draft.slot_counts.k == 0
    assert draft.slot_counts.defense == 0


def test_parse_league_maps_sleeper_type_zero_to_redraft() -> None:
    league = SleeperHost().parse_league(_load("league_snake_redraft.json"))
    assert league.host == "sleeper"
    assert league.format is LeagueFormat.REDRAFT
    assert league.max_keepers == 1
    assert league.taxi_slots == 0
    assert Slot.K in league.roster_positions
    assert Slot.DEF in league.roster_positions
    assert Slot.SUPER_FLEX not in league.roster_positions
    assert league.scoring["rec"] == 1.0


def test_parse_superflex_league() -> None:
    league = SleeperHost().parse_league(_load("league_superflex.json"))
    assert Slot.SUPER_FLEX in league.roster_positions
    assert league.format is LeagueFormat.REDRAFT


def test_parse_picks_allows_empty_picked_by_and_null_roster() -> None:
    picks = SleeperHost().parse_picks(_load("picks_mid_draft.json"))
    assert len(picks) == 100
    assert picks[0].pick_no == 1
    assert picks[0].player_id
    assert picks[0].picked_by == ""
    assert picks[0].roster_id is None
    assert picks[0].is_keeper is None


def test_parse_user_and_players_from_fixtures() -> None:
    host = SleeperHost()
    user = host.parse_user(_load("user_operator.json"))
    assert user.user_id == "user_operator"
    players = host.parse_players(_load("players.json"))
    kupp = players["4039"]
    assert isinstance(kupp, Player)
    assert kupp.yahoo_id == "30182"
    assert kupp.espn_id == "2977187"
    assert kupp.position == "WR"
    assert kupp.bye is None
    assert "ARI" in players
    assert players["ARI"].position == "DEF"
    assert players["ARI"].yahoo_id is None


def test_parse_rejects_wrong_shape() -> None:
    host = SleeperHost()
    with pytest.raises(PlatformError, match="draft"):
        host.parse_draft([])
    with pytest.raises(PlatformError, match="league"):
        host.parse_league("nope")
    with pytest.raises(PlatformError, match="picks"):
        host.parse_picks({})
    with pytest.raises(PlatformError, match="players"):
        host.parse_players([])
    with pytest.raises(PlatformError, match="user"):
        host.parse_user([])
    with pytest.raises(PlatformError, match="settings"):
        host.parse_draft({"draft_id": "x", "settings": "nope"})
    with pytest.raises(PlatformError, match="draft_order"):
        host.parse_draft({"settings": {"teams": 12, "rounds": 1}, "draft_order": []})
    with pytest.raises(PlatformError, match="slot_to_roster_id"):
        host.parse_draft(
            {"settings": {"teams": 12, "rounds": 1}, "slot_to_roster_id": []}
        )
    with pytest.raises(PlatformError, match="teams"):
        host.parse_draft({"settings": {"rounds": 1}})
    with pytest.raises(PlatformError, match="not an int"):
        host.parse_draft({"settings": {"teams": "x", "rounds": 1}})
    with pytest.raises(PlatformError, match="not an int"):
        host.parse_draft({"settings": {"teams": 12, "rounds": 1}, "start_time": "soon"})
    with pytest.raises(PlatformError, match="roster_positions"):
        host.parse_league({"settings": {"type": 0}, "roster_positions": "QB"})
    with pytest.raises(PlatformError, match="unknown slot"):
        host.parse_league({"roster_positions": ["NOPE"]})
    with pytest.raises(PlatformError, match="scoring_settings"):
        host.parse_league({"roster_positions": ["QB"], "scoring_settings": []})
    with pytest.raises(PlatformError, match="pick is not an object"):
        host.parse_picks(["nope"])
    with pytest.raises(PlatformError, match="player is not an object"):
        host.parse_players({"1": "nope"})


def test_parse_draft_order_none_and_keeper_flag() -> None:
    host = SleeperHost()
    draft = host.parse_draft(
        {
            "draft_id": "d",
            "settings": {"teams": 2, "rounds": 1, "reversal_round": None},
            "draft_order": None,
            "metadata": "skip",
        }
    )
    assert draft.draft_order is None
    assert draft.reversal_round == 0
    picks = host.parse_picks(
        [
            {
                "player_id": "1",
                "picked_by": None,
                "is_keeper": True,
                "round": 1,
                "draft_slot": 1,
                "pick_no": 1,
                "metadata": "skip",
            }
        ]
    )
    assert picks[0].is_keeper is True
    assert picks[0].picked_by == ""


def test_parse_league_format_and_odd_player_rows() -> None:
    host = SleeperHost()
    keeper = host.parse_league({"settings": {"type": 1}, "roster_positions": []})
    dynasty = host.parse_league({"settings": {"type": 2}, "roster_positions": []})
    unknown = host.parse_league({"settings": {}})
    weird = host.parse_league({"settings": {"type": 9}, "roster_positions": []})
    assert keeper.format is LeagueFormat.KEEPER
    assert dynasty.format is LeagueFormat.DYNASTY
    assert unknown.format is LeagueFormat.UNKNOWN
    assert weird.format is LeagueFormat.UNKNOWN
    players = host.parse_players(
        {
            "x": {
                "player_id": "x",
                "first_name": "A",
                "last_name": "B",
                "yahoo_id": "",
                "espn_id": "",
                "fantasy_positions": "QB",
            }
        }
    )
    assert players["x"].name == "A B"
    assert players["x"].yahoo_id is None
    assert players["x"].espn_id is None
    assert players["x"].fantasy_positions == ()
