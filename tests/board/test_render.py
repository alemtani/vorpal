"""Render is a pure function. Snapshot the HTML string."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from re import search

import pytest

from vorpal.contracts import Banner, BoardRow, Flag, Payload, Proposal, Slot, WeeklyCell

SNAPSHOTS = Path(__file__).parent / "snapshots"


def _assert_snapshot(name: str, actual: str) -> None:
    path = SNAPSHOTS / name
    expected = path.read_text(encoding="utf-8")
    assert actual == expected


def _style(html: str) -> str:
    start = html.find("<style>")
    return html[start : html.find("</style>")]


def _rec_heading(html: str) -> str:
    match = search(r'<h1 class="rec"[^>]*>([^<]*)</h1>', html)
    assert match is not None
    return match.group(1)


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


def test_rec_is_first_before_weekly_and_board(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    rec_at = html.find('class="recommendation"')
    assert rec_at != -1
    assert rec_at < html.find('class="weekly"')
    assert rec_at < html.find('class="board"')
    rec = html[rec_at : html.find("</section>", rec_at)]
    pos_at = rec.find('class="pos"')
    slot_at = rec.find('class="slot-filled"')
    why_at = rec.find('class="why"')
    alts_at = rec.find('class="alternatives"')
    assert pos_at != -1 and slot_at != -1 and why_at != -1 and alts_at != -1
    assert pos_at < slot_at < why_at < alts_at


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


def test_headers_are_not_payload_field_names(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    assert "delta_starter_points" not in html


def test_empty_weeks_are_called_out_without_dumping_eighteen_rows(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    assert 'data-week="9"' in html
    week9 = html[html.find('data-week="9"') : html.find('data-week="9"') + 200]
    assert "RB" in week9
    assert "FLEX" in week9
    assert "empty-slot" in week9
    for week in (1, 2, 10, 18):
        assert f'data-week="{week}"' not in html


def test_informational_banners_fold_into_a_compact_notice_line(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    raw_json = '{"status":500,"body":{"error":"upstream"}}'
    banners = (
        Banner(
            code="unknown_scoring_keys",
            message="Nonzero scoring keys with no matching stat column: bonus_rec_te.",
        ),
        Banner(
            code="scoring_borrowed",
            message=(
                "Scoring comes from league 123. The mock has no scoring table "
                "(metadata.scoring_type is a label, not a table)."
            ),
        ),
        Banner(
            code="keepers_possible",
            message="Keepers possible. Players with a truthy is_keeper are dropped.",
        ),
        Banner(code="board_capped", message="board is capped; do not read scarcity"),
        Banner(code="platform_error", message=raw_json),
    )
    html = render(make_payload(config_banners=()), make_proposal(), 0, banners)
    style = _style(html)
    rec_at = html.find('class="recommendation"')
    assert rec_at != -1
    assert "font-size: 1.5rem" not in style
    assert "notice" in html.lower()
    assert raw_json not in html
    assert "dynasty" not in html
    rec_block = html[rec_at : html.find("</section>", rec_at)]
    assert "bonus_rec_te" not in rec_block
    assert "league 123" not in rec_block
    assert raw_json not in rec_block
    assert "A Back" in rec_block


def test_refusal_messages_are_still_in_the_page_once_folded(
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
    assert "notice" in html.lower()


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


def test_stale_rec_says_so_and_shows_the_calculator_name(
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
    heading = _rec_heading(html)
    assert heading == "A Back"
    assert "stale" in html.lower()
    assert heading != "missing"
    assert "nope" not in html
    assert "next " not in html.split("Data age:")[1][:200]


def test_rec_heading_is_never_a_host_id(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(
        make_payload(board=()),
        make_proposal(player_id="4045", alternatives=()),
        0,
        (),
    )
    heading = _rec_heading(html)
    assert heading != "4045"
    assert "4045" not in heading
    assert "stale" in html.lower()


def test_vols_dissent_why_names_the_vols_pick(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(
        make_payload(),
        make_proposal(
            player_id="p2",
            alternatives=("p3",),
            slot_filled=Slot.WR,
            flags=(Flag.VOLS_DISSENT,),
            why="bye week stacks on the empty RB",
        ),
        0,
        (),
    )
    why = html[html.find('class="why"') : html.find('class="why"') + 240]
    assert "A Back is the VOLS pick; we are not taking A Back because" in why
    assert "bye week stacks on the empty RB" in why
    assert _rec_heading(html) == "B Receiver"


def test_ecr_disagree_why_names_the_ecr_pick(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_row: Callable[..., BoardRow],
) -> None:
    from vorpal.board import render

    board = (
        make_row(player_id="p1", name="A Back", ecr=1, vols=40.0, gp=16.0, adp=1.5),
        make_row(
            player_id="p2",
            name="B Receiver",
            position="WR",
            ecr=20,
            vols=30.0,
            delta_starter_points=8.0,
            points=240.0,
            adp=12.0,
            legal_slots=(Slot.WR, Slot.FLEX),
        ),
    )
    html = render(
        make_payload(board=board),
        make_proposal(
            player_id="p2",
            alternatives=("p1",),
            slot_filled=Slot.WR,
            flags=(Flag.ECR_DISAGREE,),
            why="the empty WR is a bigger hole",
        ),
        0,
        (),
    )
    why = html[html.find('class="why"') : html.find('class="why"') + 240]
    assert "A Back is the ECR pick; we are not taking A Back because" in why
    assert "the empty WR is a bigger hole" in why


def test_already_formed_dissent_why_is_not_wrapped_again(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    why = "A Back is the VOLS pick; we are not taking A Back because the bye stacks"
    html = render(
        make_payload(),
        make_proposal(
            player_id="p2",
            slot_filled=Slot.WR,
            flags=(Flag.VOLS_DISSENT,),
            why=why,
        ),
        0,
        (),
    )
    assert html.count("A Back is the VOLS pick") == 1


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


def test_render_unavailable_does_not_dump_raw_platform_json() -> None:
    from vorpal.board.render import render_unavailable

    raw = '{"error":"upstream","status":502}'
    html = render_unavailable(raw, 0, ())
    assert raw not in html
    assert "not current" in html.lower()


def test_no_banners_omits_the_notice_line(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(config_banners=()), make_proposal(), 0, ())
    assert 'class="notices"' not in html
    assert "<summary>" not in html


def test_weeks_without_empty_slots_are_not_listed(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    weekly = (WeeklyCell(week=1, starter_points=90.0, empty=()),)
    html = render(make_payload(weekly=weekly), make_proposal(), 0, ())
    assert "no empty startable slots" in html
    assert "data-week=" not in html


def test_stale_rec_falls_back_to_proposal_slot_when_calculator_has_no_slots(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_row: Callable[..., BoardRow],
) -> None:
    from vorpal.board import render

    calc = make_row(player_id="p1", name="A Back", legal_slots=())
    html = render(
        make_payload(board=(calc,)),
        make_proposal(player_id="missing", slot_filled=Slot.FLEX),
        0,
        (),
    )
    assert "fills FLEX" in html
    assert _rec_heading(html) == "A Back"


def test_ecr_disagree_without_ranks_keeps_the_model_why(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_row: Callable[..., BoardRow],
) -> None:
    from vorpal.board import render

    board = (
        make_row(player_id="p1", name="A Back", ecr=None, vols=40.0),
        make_row(
            player_id="p2",
            name="B Receiver",
            position="WR",
            ecr=None,
            vols=30.0,
            legal_slots=(Slot.WR, Slot.FLEX),
        ),
    )
    html = render(
        make_payload(board=board),
        make_proposal(
            player_id="p2",
            slot_filled=Slot.WR,
            flags=(Flag.ECR_DISAGREE,),
            why="the empty WR is a bigger hole",
        ),
        0,
        (),
    )
    assert "is the ECR pick" not in html
    assert "the empty WR is a bigger hole" in html


def test_vols_dissent_without_hint_on_board_keeps_the_model_why(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    payload = replace(make_payload(), hint_argmax_vols="ghost")
    html = render(
        payload,
        make_proposal(
            player_id="p2",
            slot_filled=Slot.WR,
            flags=(Flag.VOLS_DISSENT,),
            why="bye week stacks",
        ),
        0,
        (),
    )
    assert "is the VOLS pick" not in html
    assert "bye week stacks" in html


def test_already_formed_ecr_why_is_not_wrapped_again(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_row: Callable[..., BoardRow],
) -> None:
    from vorpal.board import render

    board = (
        make_row(player_id="p1", name="A Back", ecr=1, vols=40.0),
        make_row(
            player_id="p2",
            name="B Receiver",
            position="WR",
            ecr=20,
            vols=30.0,
            legal_slots=(Slot.WR, Slot.FLEX),
        ),
    )
    why = "A Back is the ECR pick; we are not taking A Back because the empty WR"
    html = render(
        make_payload(board=board),
        make_proposal(
            player_id="p2",
            slot_filled=Slot.WR,
            flags=(Flag.ECR_DISAGREE,),
            why=why,
        ),
        0,
        (),
    )
    assert html.count("A Back is the ECR pick") == 1


def test_json_array_platform_error_is_not_dumped() -> None:
    from vorpal.board.render import render_unavailable

    raw = '[{"error":"upstream"}]'
    html = render_unavailable(raw, 0, ())
    assert raw not in html
    assert "platform error" in html


def test_both_dissents_do_not_nest_because(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_row: Callable[..., BoardRow],
) -> None:
    """Two prefixes each ending in "because" used to nest, so the first read
    onto the second name instead of onto a reason. One clause, one because."""
    from vorpal.board import render

    board = (
        make_row(player_id="p1", name="A Back", ecr=40, vols=90.0),
        make_row(player_id="p3", name="C Passer", position="QB", ecr=1, vols=10.0),
        make_row(
            player_id="p2",
            name="B Receiver",
            position="WR",
            ecr=20,
            vols=30.0,
            legal_slots=(Slot.WR, Slot.FLEX),
        ),
    )
    html = render(
        make_payload(board=board),
        make_proposal(
            player_id="p2",
            slot_filled=Slot.WR,
            flags=(Flag.VOLS_DISSENT, Flag.ECR_DISAGREE),
            why="the empty WR is the bigger hole",
        ),
        0,
        (),
    )
    why = html[html.find('class="why"') : html.find('class="why"') + 320]
    assert why.count("because") == 1
    assert "A Back is the VOLS pick and C Passer is the ECR pick" in why
    assert "we are not taking A Back or C Passer because" in why
    assert "the empty WR is the bigger hole" in why


def test_one_player_leading_both_is_named_once(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
    make_row: Callable[..., BoardRow],
) -> None:
    """VOLS and ECR leader can be the same player. Two clauses named him twice."""
    from vorpal.board import render

    board = (
        make_row(player_id="p1", name="A Back", ecr=1, vols=90.0),
        make_row(
            player_id="p2",
            name="B Receiver",
            position="WR",
            ecr=20,
            vols=30.0,
            legal_slots=(Slot.WR, Slot.FLEX),
        ),
    )
    html = render(
        make_payload(board=board),
        make_proposal(
            player_id="p2",
            slot_filled=Slot.WR,
            flags=(Flag.VOLS_DISSENT, Flag.ECR_DISAGREE),
            why="the empty WR is the bigger hole",
        ),
        0,
        (),
    )
    why = html[html.find('class="why"') : html.find('class="why"') + 320]
    assert "A Back is the VOLS pick and the ECR pick" in why
    assert why.count("because") == 1
    assert why.count("A Back") == 2


def test_model_rewording_of_the_dissent_is_not_duplicated(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    """The old guard was exact-match, so any rewording printed the clause twice."""
    from vorpal.board import render

    why = "A Back is the VOLS pick here, but the bye stacks on the empty RB"
    html = render(
        make_payload(),
        make_proposal(
            player_id="p2",
            slot_filled=Slot.WR,
            flags=(Flag.VOLS_DISSENT,),
            why=why,
        ),
        0,
        (),
    )
    assert "we are not taking" not in html
    assert why in html


def test_board_shows_ecr(
    make_payload: Callable[..., Payload],
    make_proposal: Callable[..., Proposal],
) -> None:
    from vorpal.board import render

    html = render(make_payload(), make_proposal(), 0, ())
    assert '<th class="ecr">ECR</th>' in html
    assert '<td class="ecr">5</td>' in html
    # A row with no ECR renders an empty cell, not "None".
    assert '<td class="ecr"></td>' in html
    assert "None" not in html
