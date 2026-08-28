"""Override CSV is keyed by player_id. No name matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from vorpal.contracts import OverrideRow
from vorpal.errors import DataRefusal
from vorpal.ingest import load_override, parse_override

CSV = """player_id,adp,rec,rec_yd,pts_ppr,adp_stdev,name,team,pos
1,12.4,80,1000,250,3.1,Jane Doe,KC,WR
2,40.0,40,500,90,,John Roe,SF,WR
"""


def test_parse_override_returns_override_rows() -> None:
    rows = parse_override(CSV)
    assert len(rows) == 2
    assert rows[0] == OverrideRow(
        player_id="1",
        stats={"rec": 80.0, "rec_yd": 1000.0},
        adp=12.4,
        adp_stdev=3.1,
        name="Jane Doe",
        team="KC",
        pos="WR",
    )
    assert rows[1].adp_stdev is None
    assert "pts_ppr" not in rows[0].stats
    assert "adp" not in rows[0].stats


def test_pts_star_columns_do_not_reach_override_stats() -> None:
    rows = parse_override(
        "player_id,adp,rush_yd,pts_ppr,pts_std,pts_half_ppr\n1,8,100,1,2,3\n"
    )
    assert rows[0].stats == {"rush_yd": 100.0}


def test_pts_allow_columns_are_kept() -> None:
    rows = parse_override("player_id,adp,sack,pts_allow_0\nKC,90,40,2\n")
    assert rows[0].stats["pts_allow_0"] == 2.0


def test_missing_player_id_column_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="player_id"):
        parse_override("adp,rec\n1,2\n")


def test_missing_adp_column_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="adp"):
        parse_override("player_id,rec\n1,2\n")


def test_blank_adp_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="adp"):
        parse_override("player_id,adp,rec\n1,,2\n")


def test_blank_player_id_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="player_id"):
        parse_override("player_id,adp,rec\n,1,2\n")


def test_duplicate_player_id_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="duplicate"):
        parse_override("player_id,adp,rec\n1,1,2\n1,2,3\n")


def test_empty_csv_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="empty"):
        parse_override("player_id,adp,rec\n")


def test_blank_file_is_data_refusal() -> None:
    with pytest.raises(DataRefusal, match="empty"):
        parse_override("")


def test_non_numeric_override_stat_is_skipped() -> None:
    rows = parse_override("player_id,adp,rec\n1,2,\n")
    assert rows[0].stats == {}


def test_required_scoring_key_must_be_present() -> None:
    with pytest.raises(DataRefusal, match="rec_td"):
        parse_override(CSV, scoring_keys=("rec", "rec_td"))


def test_zero_weight_scoring_key_is_not_required() -> None:
    rows = parse_override(CSV, scoring={"rec": 1.0, "rec_td": 0.0, "pass_td": 0.0})
    assert rows[0].stats["rec"] == 80.0


def test_load_override_reads_utf8_sig(tmp_path: Path) -> None:
    path = tmp_path / "override.csv"
    path.write_bytes(b"\xef\xbb\xbf" + CSV.encode("utf-8"))
    rows = load_override(path)
    assert rows[0].player_id == "1"


def test_missing_override_file_is_data_refusal(tmp_path: Path) -> None:
    with pytest.raises(DataRefusal, match="override"):
        load_override(tmp_path / "missing.csv")


def test_headers_are_stripped() -> None:
    rows = parse_override(" player_id , adp , rec \n 9 , 4.5 , 11 \n")
    assert rows[0].player_id == "9"
    assert rows[0].adp == 4.5
    assert rows[0].stats["rec"] == 11.0
