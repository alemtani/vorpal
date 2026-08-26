"""Render is a pure function. Snapshot the HTML string."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from vorpal.contracts import Banner, BoardRow, Payload, Proposal

SNAPSHOTS = Path(__file__).parent / "snapshots"


def _assert_snapshot(name: str, actual: str) -> None:
    path = SNAPSHOTS / name
    expected = path.read_text(encoding="utf-8")
    assert actual == expected


def test_render_is_importable_as_a_pure_function(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 4, ())
    assert isinstance(html, str)
    assert html.startswith("<!DOCTYPE html>")


def test_normal_state_html_matches_snapshot(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 4, ())
    _assert_snapshot("normal.html", html)


def test_refusal_state_html_matches_snapshot(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    banners = (
        Banner(code="unsupported_league", message="dynasty is out of v1"),
        Banner(code="data_refusal", message="projections host is down and no override"),
        Banner(code="platform_error", message="sleeper returned 500"),
        Banner(code="user_refusal", message="operator is not in draft_order"),
    )
    html = render(make_payload(), make_proposal(), 0, banners)
    _assert_snapshot("refusal.html", html)


def test_page_shows_recommendation_slot_alternatives_why_and_flags(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    assert 'data-player-id="p1"' in html
    assert "A Back" in html
    assert "fills RB" in html or ">RB<" in html
    assert "B Receiver" in html
    assert "fills the empty RB and beats replacement" in html
    assert "VOLS_DISSENT" in html
    assert "BYE_STACK" in html


def test_board_shows_vols_and_delta_side_by_side_and_gp_when_below_17(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    vols_at = html.find('class="vols"')
    delta_at = html.find('class="delta"')
    assert vols_at != -1 and delta_at != -1
    assert vols_at < delta_at
    assert "40.0" in html
    assert "12.0" in html
    assert 'data-gp="16.0"' in html
    assert "16.0" in html
    assert 'data-gp="17' not in html
    p3_start = html.find('data-player-id="p3"')
    assert p3_start != -1
    p3_row = html[p3_start : p3_start + 400]
    assert "data-gp=" not in p3_row


def test_weekly_vector_has_18_weeks_and_calls_out_empty_startable_slots(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    for week in range(1, 19):
        assert f'data-week="{week}"' in html
    week9 = html[html.find('data-week="9"') : html.find('data-week="10"')]
    assert "RB" in week9
    assert "FLEX" in week9
    assert "empty-slot" in week9


def test_every_banner_is_loud_including_refusals(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    banners = (
        Banner(code="unsupported_league", message="dynasty is out of v1"),
        Banner(code="data_refusal", message="fix the override file"),
    )
    html = render(make_payload(), make_proposal(), 0, banners)
    assert "dynasty is out of v1" in html
    assert "fix the override file" in html
    assert "board is capped" in html
    assert html.count('class="banner"') >= 3
    assert "role=" in html and "alert" in html
    style_start = html.find("<style>")
    style = html[style_start : html.find("</style>")]
    assert ".banner" in style
    assert "font-weight: 800" in style or "font-weight:800" in style
    assert "#c00" in style or "#cc0000" in style or "background: #c" in style


def test_data_age_is_always_present(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    assert 'data-age-seconds="0"' in html
    assert "Data age:" in html


def test_meta_refresh_is_3s_while_drafting_else_15s(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    drafting = render(make_payload(status="drafting"), make_proposal(), 0, ())
    paused = render(make_payload(status="paused"), make_proposal(), 0, ())
    complete = render(make_payload(status="complete"), make_proposal(), 0, ())
    assert 'http-equiv="refresh" content="3"' in drafting
    assert 'http-equiv="refresh" content="15"' in paused
    assert 'http-equiv="refresh" content="15"' in complete


def test_past_15s_degrades_and_says_the_board_is_not_current(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    fresh = render(make_payload(), make_proposal(), 14.9, ())
    stale = render(make_payload(), make_proposal(), 15, ())
    assert 'data-degraded="false"' in fresh
    assert 'data-degraded="true"' in stale
    assert "not current" in stale.lower()
    assert 'data-code="stale_data"' in stale
    assert 'data-code="stale_data"' not in fresh


def test_grey_out_at_pick_timer_and_skip_when_timer_is_zero_or_null(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    grey = render(make_payload(pick_timer=60), make_proposal(), 60, ())
    before = render(make_payload(pick_timer=60), make_proposal(), 59, ())
    zero = render(make_payload(pick_timer=0), make_proposal(), 90, ())
    null = render(make_payload(pick_timer=None), make_proposal(), 90, ())
    assert 'data-greyed="true"' in grey
    assert 'data-code="greyed_out"' in grey
    assert "not current" in grey.lower()
    assert 'data-greyed="false"' in before
    assert 'data-greyed="false"' in zero
    assert 'data-greyed="false"' in null
    assert 'data-code="greyed_out"' not in zero
    assert 'data-code="greyed_out"' not in null
    assert 'data-degraded="true"' in zero
    assert 'data-degraded="true"' in null


def test_render_does_not_write_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    monkeypatch.chdir(tmp_path)
    render(make_payload(), make_proposal(), 1, ())
    assert list(tmp_path.iterdir()) == []


def test_render_escapes_names_why_and_banner_text(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_row: Callable[..., BoardRow],
) -> None:
    from vorpal.board import render

    row = make_row(player_id="p1", name='Joe <script> & "Co"', gp=16.0)
    payload = make_payload(board=(row,))
    proposal = make_proposal(why="a <b> why & more", flags=())
    banners = (Banner(code="x", message="<img src=x onerror=alert(1)>"),)
    html = render(payload, proposal, 0, banners)
    assert "<script>" not in html
    assert "<b>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html
    assert "&lt;b&gt;" in html
    assert "&lt;img" in html


def test_empty_flags_still_has_a_flags_section(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(flags=()), 0, ())
    assert "flag" in html.lower()
    assert "VOLS_DISSENT" not in html


def test_coin_flip_is_visible_when_set(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    on = render(make_payload(), make_proposal(coin_flip=True), 0, ())
    off = render(make_payload(), make_proposal(coin_flip=False), 0, ())
    assert "coin_flip" in on
    assert 'data-coin-flip="true"' in on
    assert 'data-coin-flip="false"' in off


def test_unknown_recommendation_id_still_renders_the_id(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(
        make_payload(next_user_pick=None, picks_until_next=None),
        make_proposal(player_id="missing", alternatives=("nope",)),
        0,
        (),
    )
    assert "missing" in html
    assert "nope" in html
    assert "next " not in html.split("Data age:")[1][:200]


def test_empty_alternatives_still_has_a_list(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(alternatives=()), 0, ())
    assert "none" in html


def test_render_unavailable_is_loud_and_never_claims_to_be_current() -> None:
    from vorpal.board.render import render_unavailable

    banners = (Banner(code="platform_error", message="sleeper returned 500"),)
    html = render_unavailable(
        "sleeper returned 500", 16, banners, status="paused", pick_timer=60
    )
    assert html.startswith("<!DOCTYPE html>")
    assert "sleeper returned 500" in html
    assert "not current" in html.lower()
    assert 'data-degraded="true"' in html
    assert 'class="banner"' in html
    assert 'http-equiv="refresh" content="15"' in html


def test_render_unavailable_with_no_banners_still_shows_the_message() -> None:
    from vorpal.board.render import render_unavailable

    html = render_unavailable("gone", 0, ())
    assert "gone" in html
    assert "not current" in html.lower()
    assert 'data-code="unavailable"' in html
