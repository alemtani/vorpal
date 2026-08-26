"""Scoring applies the league table to counting stats. Never pts_*."""

from __future__ import annotations

from vorpal.valuation import (
    FANTASY_POINT_KEYS,
    ScoringFamily,
    classify_scoring_key,
    score_player,
    score_skill,
    unmatched_scoring_keys,
)

PPR = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -1.0,
    "pass_2pt": 2.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rush_2pt": 2.0,
    "rec": 1.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "rec_2pt": 2.0,
    "fum": 0.0,
    "fum_lost": -2.0,
}

SKILL_STATS = {
    "rush_yd": 100.0,
    "rush_td": 2.0,
    "rec": 10.0,
    "rec_yd": 80.0,
    "rec_td": 1.0,
    "fum_lost": 1.0,
}


def _stats(rows: list[dict[str, object]], player_id: str) -> dict[str, float]:
    for row in rows:
        if row.get("player_id") == player_id:
            raw = row["stats"]
            assert isinstance(raw, dict)
            return {str(key): float(value) for key, value in raw.items()}
    raise AssertionError(f"missing projection row {player_id}")


def test_score_skill_covers_rush_rec_yards_td_fumble() -> None:
    points = score_skill(SKILL_STATS, PPR, position="RB")
    assert points == 100 * 0.1 + 2 * 6 + 10 * 1 + 80 * 0.1 + 1 * 6 - 2


def test_rb_and_wr_share_the_skill_formula() -> None:
    rb = score_skill(SKILL_STATS, PPR, position="RB")
    wr = score_skill(SKILL_STATS, PPR, position="WR")
    assert rb == wr
    assert score_player("RB", SKILL_STATS, PPR) == rb
    assert score_player("WR", SKILL_STATS, PPR) == wr


def test_bonus_rec_te_is_the_position_premium() -> None:
    scoring = {**PPR, "bonus_rec_te": 0.5}
    te = score_skill(SKILL_STATS, scoring, position="TE")
    wr = score_skill(SKILL_STATS, scoring, position="WR")
    assert te - wr == 0.5 * 10
    assert score_player("TE", SKILL_STATS, scoring) == te
    assert score_player("WR", SKILL_STATS, scoring) == wr


def test_bonus_rec_te_uses_rec_when_the_bonus_column_is_absent() -> None:
    scoring = {**PPR, "bonus_rec_te": 0.5}
    stats = dict(SKILL_STATS)
    assert "bonus_rec_te" not in stats
    assert score_skill(stats, scoring, position="TE") == 10 * 0.5 + score_skill(
        stats, PPR, position="TE"
    )


def test_qb_uses_pass_keys_and_skill_rushing() -> None:
    stats = {
        "pass_yd": 300.0,
        "pass_td": 2.0,
        "pass_int": 1.0,
        "rush_yd": 40.0,
        "rush_td": 1.0,
        "fum_lost": 1.0,
        "rec": 0.0,
    }
    points = score_player("QB", stats, PPR)
    assert points == 300 * 0.04 + 2 * 4 - 1 + 40 * 0.1 + 6 - 2


def test_longer_prefix_pass_int_is_qb_not_dst() -> None:
    assert classify_scoring_key("pass_int") is ScoringFamily.PASS
    assert classify_scoring_key("int") is ScoringFamily.DST
    scoring = {"pass_int": -1.0, "int": 2.0}
    qb = score_player("QB", {"pass_int": 3.0, "int": 3.0}, scoring)
    dst = score_player("DEF", {"pass_int": 3.0, "int": 3.0}, scoring)
    assert qb == -3.0
    assert dst == 6.0


def test_k_and_dst_use_their_own_keys() -> None:
    k_scoring = {
        "fgm_40_49": 4.0,
        "fgm_50p": 5.0,
        "xpm": 1.0,
        "xpmiss": -1.0,
        "rec": 1.0,
    }
    k = score_player(
        "K",
        {"fgm_40_49": 2.0, "fgm_50p": 1.0, "xpm": 3.0, "xpmiss": 1.0, "rec": 9.0},
        k_scoring,
    )
    assert k == 2 * 4 + 5 + 3 - 1
    dst_scoring = {"sack": 1.0, "int": 2.0, "pass_int": -1.0, "pass_int_td": -2.0}
    dst = score_player(
        "DEF",
        {"sack": 4.0, "int": 2.0, "pass_int": 9.0, "pass_int_td": 1.0},
        dst_scoring,
    )
    assert dst == 4 + 4


def test_never_reads_a_fantasy_point_column() -> None:
    stats = {**SKILL_STATS, "pts_ppr": 999.0, "pts_std": 888.0, "pts_half_ppr": 777.0}
    assert score_player("RB", stats, PPR) == score_skill(
        SKILL_STATS, PPR, position="RB"
    )
    scoring = {**PPR, "pts_ppr": 1.0}
    assert score_player("RB", stats, scoring) == score_player("RB", SKILL_STATS, PPR)


def test_zero_weight_key_does_not_need_a_column() -> None:
    scoring = {"rec": 1.0, "fum": 0.0, "unknown_stat": 0.0}
    assert unmatched_scoring_keys(scoring, columns={"rec"}) == ()
    assert score_player("WR", {"rec": 5.0}, scoring) == 5.0


def test_nonzero_unknown_key_is_reported_not_silent_zero() -> None:
    scoring = {"rec": 1.0, "bonus_rec_te": 0.5, "mystery": 3.0}
    unmatched = unmatched_scoring_keys(scoring, columns={"rec", "bonus_rec_te"})
    assert unmatched == ("mystery",)
    assert score_player("TE", {"rec": 4.0}, scoring) == 4.0 + 0.5 * 4


def test_fantasy_point_keys_are_never_counting_columns() -> None:
    assert FANTASY_POINT_KEYS == frozenset({"pts_ppr", "pts_std", "pts_half_ppr"})
    for key in FANTASY_POINT_KEYS:
        assert classify_scoring_key(key) is ScoringFamily.FANTASY
    assert classify_scoring_key("pts_allow_0") is ScoringFamily.DST


def test_fixture_scoring_keys_classify_and_report_missing_columns(
    snake_scoring: dict[str, float],
    projection_rows: list[dict[str, object]],
) -> None:
    columns: set[str] = set()
    for row in projection_rows:
        stats = row.get("stats")
        if isinstance(stats, dict):
            columns.update(str(key) for key in stats)
    for key in snake_scoring:
        family = classify_scoring_key(key)
        assert family is not ScoringFamily.FANTASY
        assert family is not ScoringFamily.UNKNOWN
    unmatched = unmatched_scoring_keys(snake_scoring, columns)
    for key in unmatched:
        assert snake_scoring[key] != 0.0
        assert key not in columns


def test_fixture_projection_row_does_not_use_pts_ppr(
    snake_scoring: dict[str, float],
    projection_rows: list[dict[str, object]],
) -> None:
    stats = _stats(projection_rows, "11560")
    points = score_player("QB", stats, snake_scoring)
    assert points == 3651 * 0.04 + 28 * 4 + 10 * -1 + 1 * 2 + 373 * 0.1 + 3 * 6 + 3 * -2
    only_pts = {key: value for key, value in stats.items() if key.startswith("pts_")}
    assert score_player("QB", only_pts, snake_scoring) == 0.0


def test_fixture_te_and_k_and_dst_rows(
    snake_scoring: dict[str, float],
    projection_rows: list[dict[str, object]],
) -> None:
    te = score_player("TE", _stats(projection_rows, "10236"), snake_scoring)
    assert te == 66 * 1 + 736 * 0.1 + 4 * 6
    k = score_player("K", _stats(projection_rows, "11533"), snake_scoring)
    assert k == 9 * 4 + 8 * 5 + 42 * 1 + 2 * -1
    dst_stats = _stats(projection_rows, "ARI")
    dst = score_player("DEF", dst_stats, snake_scoring)
    assert dst == 8 * 2 + 34 * 1 + 7 * 2 + 1 * 2 + 1 * 10
    assert dst != dst_stats["pts_ppr"]
    assert score_player("DST", dst_stats, snake_scoring) == dst


def test_unknown_position_and_bonus_edges() -> None:
    assert score_player("P", SKILL_STATS, PPR) == 0.0
    assert score_player("FB", SKILL_STATS, PPR) == score_skill(
        SKILL_STATS, PPR, position="FB"
    )
    scoring = {
        **PPR,
        "bonus_rec_te": 0.5,
        "bonus_rush_td_qb": 2.0,
        "bonus_rec_yd_100": 3.0,
    }
    te_stats = {**SKILL_STATS, "bonus_rec_te": 4.0}
    assert (
        score_skill(te_stats, scoring, position="TE")
        == score_skill(SKILL_STATS, PPR, position="TE") + 0.5 * 4
    )
    rb_stats = {**SKILL_STATS, "bonus_rush_td_qb": 9.0, "bonus_rec_yd_100": 2.0}
    rb = score_player("RB", rb_stats, scoring)
    assert rb == score_skill(SKILL_STATS, PPR, position="RB") + 3.0 * 2
    qb = score_player("QB", {"rush_td": 1.0, "bonus_rush_td_qb": 1.0}, scoring)
    assert qb == 6.0 + 2.0
    assert score_skill(
        SKILL_STATS, {**PPR, "bonus_rec_yd_100": 3.0}, position="RB"
    ) == (score_skill(SKILL_STATS, PPR, position="RB"))
