"""Backtest tables on a small synthetic season."""

from vorpal.season.fit import FIRST_WEEK, backtest

SCORING = {"rec": 1.0, "rec_yd": 0.1, "rush_yd": 0.1, "rec_td": 6.0}
PLAYERS = {
    "wr": {"position": "WR"},
    "qb": {"position": "QB"},
    "low": {"position": "RB"},
}


def _line(w: int) -> dict:
    return {"rec_tgt": 6 + w % 3, "rec": 4, "rec_yd": 50 + w, "off_snp": 50}


STATS = {
    w: [
        {"player_id": "wr", "stats": _line(w)},
        {"player_id": "qb", "stats": {"off_snp": 60}},
        {"player_id": "low", "stats": {"rush_att": 1, "off_snp": 5}},
        {"player_id": "ghost", "stats": None},
    ]
    for w in range(1, 9)
}
PROJ = {
    w: [{"player_id": "wr", "stats": {"rec": 4, "rec_yd": 55}}] for w in range(4, 8)
}


def test_backtest_tables() -> None:
    r = backtest(STATS, PROJ, PLAYERS, SCORING)
    assert r.subject == f"Backtest: {8 - FIRST_WEEK + 1} player-weeks"
    hl, td, mw = r.tables
    assert [row[0] for row in hl.rows] == ["1", "2", "3", "4", "6", "10"]
    assert [row[0] for row in td.rows] == ["0", "0.25", "0.5", "1"]
    assert mw.title == "Model weight vs Sleeper (4 pairs)"
    assert all(float(row[1]) >= 0 for row in hl.rows + td.rows + mw.rows)


def test_backtest_without_projections_reports_nan() -> None:
    r = backtest(STATS, {}, PLAYERS, SCORING)
    assert r.tables[2].rows[0][1] == "nan"
