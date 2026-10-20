"""Week 7: Tuten on bye and Evans out are starting. Gibbs and J. Williams sit."""

from dataclasses import replace

import pytest

from vorpal.season.lineup import lineup_report, win_chance


def test_week_7_starts_gibbs_and_jameson_williams(season7) -> None:
    r = lineup_report(season7)
    assert r.subject.startswith("Week 7 lineup: 2 changes")
    assert any(ln.startswith("START Jahmyr Gibbs") for ln in r.lines)
    assert any(ln.startswith("START Jameson Williams") for ln in r.lines)
    assert "SIT Bhayshul Tuten (JAX bye)" in r.lines
    assert "SIT Mike Evans (Out)" in r.lines


def test_week_7_suggests_ir_for_out_players(season7) -> None:
    r = lineup_report(season7)
    ir = [ln for ln in r.lines if ln.startswith("Move to IR")]
    assert ir == [
        "Move to IR (1 open): Breece Hall (Out), Mike Evans (Out). Frees a bench spot."
    ]


def test_tables_show_best_lineup_and_bench(season7) -> None:
    best, bench, ir = lineup_report(season7).tables
    assert ir.rows == [("T.J. Hockenson", "Out", ir.rows[0][2], "week 8")]
    assert len(best.rows) == 9
    assert best.rows[0][0] == "QB"
    why = {row[0]: row[2] for row in bench.rows}
    assert why["Bhayshul Tuten"] == "JAX bye"
    assert why["Kyle Pitts"] == ""


def test_no_changes_once_the_lineup_is_set(season7) -> None:
    first = lineup_report(season7)
    best_ids = [row[1] for row in first.tables[0].rows]
    by_name = {season7.name(p): p for p in season7.active(season7.me)}
    me = dict(season7.me, starters=[by_name[n] for n in best_ids])
    r = lineup_report(replace(season7, me=me))
    assert r.subject == "Week 7 lineup: no changes (" + r.subject.split("(")[1]
    assert r.key == first.key


def test_activate_from_ir_when_status_clears(season7) -> None:
    now = dict(season7.now)
    now["hock"] = replace(now["hock"], status=None, points=10.5)
    r = lineup_report(replace(season7, now=now))
    assert "Activate T.J. Hockenson from IR (status now healthy)." in r.lines


def test_win_chance_against_opponent(season7) -> None:
    opp = season7.roster(8)["players"]
    r = lineup_report(season7, opponent=opp, opponent_name="Nuyen")
    line = next(ln for ln in r.lines if ln.startswith("Win chance vs Nuyen"))
    assert "%" in line


def test_win_chance_math() -> None:
    assert win_chance([], []) == 0.5
    assert win_chance([100.0], [100.0]) == pytest.approx(0.5)
    assert win_chance([110.0], [100.0]) > 0.5
    assert win_chance([90.0], [100.0]) < 0.5


def test_late_game_warning_without_a_monday_backup(season7) -> None:
    now = dict(season7.now)
    now["evans"] = replace(now["evans"], status=None, points=16.0)
    r = lineup_report(replace(season7, now=now))
    late = [ln for ln in r.lines if ln.startswith("Late game")]
    assert len(late) == 1
    assert "Mike Evans" in late[0] and "2026-10-26" in late[0]
    assert "Benching him for" in late[0]


def test_no_late_warning_when_a_backup_plays_that_day(season7) -> None:
    now = dict(season7.now)
    now["evans"] = replace(now["evans"], status=None, points=16.0)
    dates = dict(season7.dates)
    dates["CLE", 7] = "2026-10-26"
    dates["NO", 7] = "2026-10-26"
    r = lineup_report(replace(season7, now=now, dates=dates))
    assert not [ln for ln in r.lines if ln.startswith("Late game")]


def test_late_warning_without_any_bench_option(season7) -> None:
    me = dict(season7.me, players=["maye"], starters=["maye"], reserve=[])
    dates = dict(season7.dates)
    dates["NE", 7] = "2026-10-26"
    r = lineup_report(replace(season7, me=me, dates=dates))
    late = [ln for ln in r.lines if ln.startswith("Late game")]
    assert late and "Benching" not in late[0]


def test_sit_reason_for_a_low_projection_and_teamless_player(season7) -> None:
    now = dict(season7.now)
    now["pat"] = replace(now["pat"], points=0.5)
    now["vele"] = replace(now["vele"], team=None, plays=False, points=0.0)
    r = lineup_report(replace(season7, now=now))
    assert "SIT Devaughn Vele (no team)" in r.lines


def test_notes_are_appended(season7) -> None:
    r = lineup_report(replace(season7, notes=["ESPN projections missing"]))
    assert r.lines[-1] == "ESPN projections missing"


def test_ir_status_is_always_ir_eligible(season7) -> None:
    now = dict(season7.now)
    now["tuten"] = replace(now["tuten"], status="IR")
    r = lineup_report(replace(season7, now=now))
    ir = next(ln for ln in r.lines if ln.startswith("Move to IR"))
    assert "Bhayshul Tuten (IR)" in ir


def test_model_column_marks_unused_and_partial_models(season7) -> None:
    from vorpal.season.lineup import _model_cell

    assert _model_cell(season7.now["maye"]) == "-"
    assert _model_cell(season7.now["pierce"]).endswith("(unused: fill-in role)")
    two = replace(season7.now["pierce"], role_games=2)
    assert _model_cell(two).endswith("(part: 2 role games)")
    assert "(" not in _model_cell(season7.now["london"])


def test_ir_table_with_injury_and_healthy_reserve(season7) -> None:
    now = dict(season7.now)
    now["hock"] = replace(now["hock"], injury="Concussion")
    now["tuten"] = replace(now["tuten"], status=None)
    me = dict(season7.me, reserve=["hock", "tuten", "ghost"])
    ir = lineup_report(replace(season7, now=now, me=me)).tables[2]
    assert ir.rows[0][1] == "Out (Concussion)"
    assert ir.rows[1][1:] == ("healthy", ir.rows[1][2], "now")
    assert len(ir.rows) == 2
