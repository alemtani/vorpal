"""Fail-closed mapping. Top 300 by ADP must match at 98%."""

from __future__ import annotations

import pytest

from vorpal.contracts import Host, Player
from vorpal.errors import DataRefusal
from vorpal.ingest.mapping import MappingRow, check_mapping, map_rows


def _player(
    player_id: str,
    name: str,
    position: str,
    team: str | None,
    yahoo_id: str | None = None,
) -> Player:
    parts = name.split(" ", 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    return Player(
        player_id=player_id,
        host=Host.SLEEPER,
        first_name=first,
        last_name=last,
        name=name,
        position=position,
        team=team,
        fantasy_positions=(position,),
        active=True,
        status=None,
        injury_status=None,
        years_exp=None,
        number=None,
        bye=None,
        external_ids=() if yahoo_id is None else (("yahoo", yahoo_id),),
    )


def _row(
    player_id: str,
    name: str,
    position: str = "WR",
    team: str | None = "KC",
    adp: float | None = 1.0,
    yahoo_id: str | None = None,
    host_id: str | None = None,
) -> MappingRow:
    return MappingRow(
        player_id=player_id,
        name=name,
        position=position,
        team=team,
        adp=adp,
        yahoo_id=yahoo_id,
        host_id=host_id,
    )


def _board(*, n: int, misses: int) -> tuple[list[MappingRow], dict[str, Player]]:
    """Lowest ADP is 1. The first ``misses`` ids are absent from players."""
    sources: list[MappingRow] = []
    players: dict[str, Player] = {}
    for index in range(n):
        pid = f"id{index}"
        name = f"Player {index}"
        sources.append(_row(pid, name, adp=float(index + 1), host_id=pid))
        if index >= misses:
            players[pid] = _player(pid, name, "WR", "KC")
    return sources, players


def test_player_id_match_wins_even_when_the_name_differs() -> None:
    sources = [_row("s1", "Wrong Name", host_id="s1")]
    players = {"s1": _player("s1", "Jane Doe", "WR", "KC")}
    report = map_rows(sources, players)
    assert report.matched == 1
    assert report.hits[0].method == "player_id"
    assert report.hits[0].host_player_id == "s1"


def test_yahoo_id_match_when_host_ids_differ() -> None:
    sources = [_row("fp1", "Jane Doe", yahoo_id="111")]
    players = {"s1": _player("s1", "Jane Doe", "WR", "KC", yahoo_id="111")}
    report = map_rows(sources, players)
    assert report.hits[0].method == "yahoo_id"
    assert report.hits[0].host_player_id == "s1"


def test_fp_numeric_id_does_not_collide_with_host_id() -> None:
    sources = [_row("4984", "Someone Else", "WR", "KC")]
    players = {"4984": _player("4984", "Josh Allen", "QB", "BUF")}
    report = map_rows(sources, players)
    assert report.matched == 0


def test_name_pos_team_match_when_ids_differ() -> None:
    sources = [_row("fp1", "Jane Doe", "WR", "KC")]
    players = {"s1": _player("s1", "Jane Doe", "WR", "KC")}
    report = map_rows(sources, players)
    assert report.hits[0].method == "name_pos_team"
    assert report.hits[0].host_player_id == "s1"
    assert report.hits[0].team_mismatch is False


def test_name_pos_match_flags_team_mismatch() -> None:
    sources = [_row("fp1", "Jane Doe", "WR", "KC")]
    players = {"s1": _player("s1", "Jane Doe", "WR", "SF")}
    report = map_rows(sources, players)
    assert report.hits[0].method == "name_pos"
    assert report.hits[0].team_mismatch is True
    assert report.team_mismatches == 1


def test_dst_normalizes_to_def_for_name_match() -> None:
    sources = [_row("fp-hou", "Houston Texans", "DST", "HOU")]
    players = {"HOU": _player("HOU", "Houston Texans", "DEF", "HOU")}
    report = map_rows(sources, players)
    assert report.hits[0].host_player_id == "HOU"
    assert report.hits[0].method == "name_pos_team"


def test_name_suffixes_and_punctuation_do_not_block_a_match() -> None:
    sources = [_row("fp1", "Amon-Ra St. Brown Jr.", "WR", "DET")]
    players = {"s1": _player("s1", "Amon-Ra St. Brown", "WR", "DET")}
    report = map_rows(sources, players)
    assert report.matched == 1


def test_ambiguous_name_pos_is_a_miss() -> None:
    sources = [_row("fp1", "Jane Doe", "WR", "NE")]
    players = {
        "s1": _player("s1", "Jane Doe", "WR", "KC"),
        "s2": _player("s2", "Jane Doe", "WR", "SF"),
    }
    report = map_rows(sources, players)
    assert report.matched == 0
    assert report.misses[0].source_player_id == "fp1"


def test_override_does_not_name_match() -> None:
    sources = [_row("csv-1", "Jane Doe", "WR", "KC")]
    players = {"s1": _player("s1", "Jane Doe", "WR", "KC")}
    report = map_rows(sources, players, allow_name_match=False)
    assert report.matched == 0


def test_rows_without_adp_are_not_in_the_top_n_rate() -> None:
    sources = [_row("a", "A", adp=1.0), _row("b", "B", adp=None)]
    players = {"a": _player("a", "A", "WR", "KC")}
    report = map_rows(sources, players, top_n=300)
    assert report.considered == 1
    assert report.match_rate == 1.0


def test_mapping_at_98_percent_passes() -> None:
    sources, players = _board(n=300, misses=6)
    report = map_rows(sources, players, top_n=300)
    assert report.considered == 300
    assert report.matched == 294
    check_mapping(report)


def test_mapping_under_98_percent_raises_data_refusal_with_report() -> None:
    sources, players = _board(n=300, misses=7)
    report = map_rows(sources, players, top_n=300)
    assert report.matched == 293
    with pytest.raises(DataRefusal, match="98%") as caught:
        check_mapping(report)
    message = caught.value.message
    assert "293" in message
    assert "id0" in message


def test_no_adp_rows_falls_back_to_the_full_set() -> None:
    sources = [_row("a", "A", adp=None, host_id="a")]
    players = {"a": _player("a", "A", "WR", "KC")}
    report = map_rows(sources, players, top_n=300)
    assert report.considered == 1
    check_mapping(report)


def test_empty_sources_is_data_refusal() -> None:
    report = map_rows([], {}, top_n=300)
    with pytest.raises(DataRefusal, match="ADP"):
        check_mapping(report)
