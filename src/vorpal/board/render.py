"""Pure HTML render. No files, no clock, no client."""

from __future__ import annotations

import html
from collections.abc import Sequence

from vorpal.board.schedule import is_degraded, is_greyed_out, poll_interval
from vorpal.contracts import Banner, BoardRow, Payload, Proposal, WeeklyCell

_CSS = """
:root { color-scheme: dark; }
body {
  font-family: ui-sans-serif, system-ui, sans-serif;
  background: #111;
  color: #f5f5f5;
  margin: 0;
  padding: 1rem;
}
body[data-degraded="true"] { box-shadow: inset 0 0 0 8px #fc0; }
body[data-greyed="true"] .recommendation,
body[data-greyed="true"] .weekly,
body[data-greyed="true"] .board { filter: grayscale(1); opacity: 0.65; }
.banner {
  background: #c00;
  color: #fff;
  font-size: 1.5rem;
  font-weight: 800;
  padding: 0.8rem 1rem;
  margin: 0.6rem 0;
  border: 4px solid #fff;
}
.age.stale { color: #fc0; font-weight: 800; }
.timer { font-size: 1.25rem; }
.rec { font-size: 1.8rem; margin: 0.2rem 0; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid #444; padding: 0.3rem 0.5rem; text-align: left; }
td.gp { font-weight: 800; color: #fc0; }
.empty-slot {
  background: #c00;
  color: #fff;
  font-weight: 800;
  padding: 0 0.35rem;
}
""".strip()


def render(
    payload: Payload,
    proposal: Proposal,
    age_seconds: float,
    banners: Sequence[Banner],
) -> str:
    """Return a self-contained HTML page. Does not write a file."""

    pick_timer = payload.config.pick_timer
    status = payload.config.status
    bits = [status, f"pick {payload.state.pick_no}"]
    if payload.state.next_user_pick is not None:
        bits.append(f"next {payload.state.next_user_pick}")
    if payload.state.picks_until_next is not None:
        bits.append(f"in {payload.state.picks_until_next}")
    return _shell(
        title=f"vorpal — pick {payload.state.pick_no}",
        status=status,
        status_line=" · ".join(bits),
        pick_timer=pick_timer,
        age_seconds=age_seconds,
        banners=_all_banners(age_seconds, pick_timer, banners, payload.config.banners),
        inner=_board_inner(payload, proposal),
    )


def render_unavailable(
    message: str,
    age_seconds: float,
    banners: Sequence[Banner] = (),
    *,
    status: str = "unknown",
    pick_timer: int | None = None,
) -> str:
    """Loud page when there is no board to show. Never claims to be current."""

    shown = list(banners)
    if not any(banner.message == message for banner in shown):
        shown.insert(0, Banner(code="unavailable", message=message))
    inner = (
        f'<p class="unavailable-message">{html.escape(message)}</p>\n'
        "<p>No board yet. This is not current.</p>"
    )
    return _shell(
        title="vorpal",
        status=status,
        status_line=status,
        pick_timer=pick_timer,
        age_seconds=age_seconds,
        banners=_all_banners(age_seconds, pick_timer, shown, ()),
        inner=inner,
    )


def _all_banners(
    age_seconds: float,
    pick_timer: int | None,
    extra: Sequence[Banner],
    config: Sequence[Banner],
) -> tuple[Banner, ...]:
    synthetic: list[Banner] = []
    age_txt = _fmt_age(age_seconds)
    if is_greyed_out(age_seconds, pick_timer):
        synthetic.append(
            Banner(
                code="greyed_out",
                message=(
                    f"GREYED OUT: data age {age_txt}s reached pick timer "
                    f"{pick_timer}s. This board is not current."
                ),
            )
        )
    if is_degraded(age_seconds):
        synthetic.append(
            Banner(
                code="stale_data",
                message=(
                    f"STALE: data age {age_txt}s is past 15s. "
                    "This board is not current."
                ),
            )
        )
    return (*synthetic, *extra, *config)


def _board_inner(payload: Payload, proposal: Proposal) -> str:
    by_id = {row.player_id: row for row in payload.board}
    rec = by_id.get(proposal.player_id)
    rec_name = rec.name if rec is not None else proposal.player_id
    rec_pos = rec.position if rec is not None else ""
    alt_items = "\n".join(_alt_item(by_id, pid) for pid in proposal.alternatives)
    if not alt_items:
        alt_items = "<li>none</li>"
    flags_block = _flags_block(proposal)
    coin = _bool(proposal.coin_flip)
    coin_label = "yes" if proposal.coin_flip else "no"
    rows = "\n".join(_board_row(row) for row in payload.board)
    weeks = "\n".join(_week_item(cell) for cell in payload.state.weekly)
    return (
        '<section class="recommendation">\n'
        f'<h1 class="rec" data-player-id="{_attr(proposal.player_id)}">'
        f"{html.escape(rec_name)}</h1>\n"
        f'<p class="slot-filled">fills {html.escape(proposal.slot_filled.value)}</p>\n'
        f'<p class="pos">{html.escape(rec_pos)}</p>\n'
        f'<p class="why">{html.escape(proposal.why)}</p>\n'
        f'<ul class="alternatives">\n{alt_items}\n</ul>\n'
        f'<p class="coin-flip" data-coin-flip="{coin}">coin_flip: {coin_label}</p>\n'
        f"{flags_block}\n"
        "</section>\n"
        '<section class="weekly">\n'
        "<h2>Starter points by week</h2>\n"
        f"<ol>\n{weeks}\n</ol>\n"
        "</section>\n"
        '<section class="board">\n'
        "<h2>Board</h2>\n"
        "<table>\n"
        "<thead>\n"
        "<tr>"
        "<th>name</th><th>pos</th>"
        '<th class="vols">vols</th>'
        '<th class="delta">delta_starter_points</th>'
        "<th>points</th><th>adp</th><th>gp</th>"
        "</tr>\n"
        "</thead>\n"
        f"<tbody>\n{rows}\n</tbody>\n"
        "</table>\n"
        "</section>"
    )


def _alt_item(by_id: dict[str, BoardRow], player_id: str) -> str:
    row = by_id.get(player_id)
    label = row.name if row is not None else player_id
    return f'<li data-player-id="{_attr(player_id)}">{html.escape(label)}</li>'


def _flags_block(proposal: Proposal) -> str:
    if not proposal.flags:
        return '<ul class="flags" data-empty="true"></ul>\n<p>no flags</p>'
    items = "\n".join(
        f'<li class="flag">{html.escape(flag.value)}</li>' for flag in proposal.flags
    )
    return f'<ul class="flags">\n{items}\n</ul>'


def _board_row(row: BoardRow) -> str:
    gp_attr = ""
    gp_cell = ""
    if row.gp is not None and row.gp < 17:
        gp_txt = f"{row.gp:.1f}"
        gp_attr = f' data-gp="{gp_txt}"'
        gp_cell = gp_txt
    return (
        f'<tr data-player-id="{_attr(row.player_id)}"{gp_attr}>'
        f"<td>{html.escape(row.name)}</td>"
        f"<td>{html.escape(row.position)}</td>"
        f'<td class="vols">{_fmt_num(row.vols)}</td>'
        f'<td class="delta">{_fmt_num(row.delta_starter_points)}</td>'
        f"<td>{_fmt_num(row.points)}</td>"
        f"<td>{_fmt_num(row.adp)}</td>"
        f'<td class="gp">{gp_cell}</td>'
        "</tr>"
    )


def _week_item(cell: WeeklyCell) -> str:
    week = cell.week
    starter_points = cell.starter_points
    empty = cell.empty
    empties = "".join(
        f'<span class="empty-slot">{html.escape(slot.value)}</span>' for slot in empty
    )
    cls = ' class="has-empty"' if empty else ""
    empty_note = f" · empty: {empties}" if empty else ""
    return (
        f'<li data-week="{week}"{cls}>'
        f"W{week}: {_fmt_num(starter_points)}{empty_note}"
        "</li>"
    )


def _shell(
    *,
    title: str,
    status: str,
    status_line: str,
    pick_timer: int | None,
    age_seconds: float,
    banners: Sequence[Banner],
    inner: str,
) -> str:
    degraded = is_degraded(age_seconds)
    greyed = is_greyed_out(age_seconds, pick_timer)
    age_txt = _fmt_age(age_seconds)
    age_class = "age stale" if degraded else "age"
    timer_attr = "" if pick_timer is None else str(pick_timer)
    if pick_timer is None or pick_timer == 0:
        timer_label = "Pick timer: off"
    else:
        timer_label = f"Pick timer: {pick_timer}s"
    banner_html = "\n".join(
        f'<div class="banner" data-code="{_attr(banner.code)}">'
        f"{html.escape(banner.message)}</div>"
        for banner in banners
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="{poll_interval(status)}">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>\n{_CSS}\n</style>\n"
        "</head>\n"
        f'<body data-degraded="{_bool(degraded)}" data-greyed="{_bool(greyed)}">\n'
        "<header>\n"
        f'<div class="timer" data-pick-timer="{_attr(timer_attr)}">'
        f"{timer_label}</div>\n"
        f'<div class="{age_class}" data-age-seconds="{age_txt}">'
        f"Data age: {age_txt}s</div>\n"
        f'<div class="status" data-status="{_attr(status)}">'
        f"{html.escape(status_line)}</div>\n"
        "</header>\n"
        '<section class="banners" role="alert">\n'
        f"{banner_html}\n"
        "</section>\n"
        f"{inner}\n"
        "</body>\n"
        "</html>\n"
    )


def _fmt_age(age_seconds: float) -> str:
    if float(age_seconds) == int(age_seconds):
        return str(int(age_seconds))
    return f"{age_seconds:.1f}"


def _fmt_num(value: float) -> str:
    return f"{value:.1f}"


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _attr(value: str) -> str:
    return html.escape(value, quote=True)
