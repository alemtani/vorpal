"""Pure HTML render. No files, no clock, no client.

Night view: the pick the operator can act on is first. Informational
banners fold into a compact notice line. Host ids never headline the rec.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from vorpal.board.schedule import is_degraded, is_greyed_out, poll_interval
from vorpal.contracts import Banner, BoardRow, Flag, Payload, Proposal, WeeklyCell

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
.age.stale { color: #fc0; font-weight: 800; }
.timer { font-size: 1.25rem; }
.rec { font-size: 1.8rem; margin: 0.2rem 0; }
.stale-rec { color: #fc0; font-weight: 800; }
.notices { font-size: 0.95rem; margin: 0.4rem 0; }
.notices summary { cursor: pointer; color: #fc0; }
.notices .banner { padding: 0.15rem 0; }
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
        f'<p class="unavailable-message">{html.escape(_operator_text(message))}</p>\n'
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
    calc = by_id.get(payload.hint_argmax_vols)
    stale = rec is None
    if stale:
        heading = calc.name if calc is not None else "stale rec"
        rec_id = calc.player_id if calc is not None else ""
        rec_pos = calc.position if calc is not None else ""
        if calc is not None and calc.legal_slots:
            slot = calc.legal_slots[0].value
        else:
            slot = proposal.slot_filled.value
        why = "rec is stale"
        shown_id = rec_id
    else:
        heading = rec.name
        rec_pos = rec.position
        slot = proposal.slot_filled.value
        why = _why_on_screen(payload, proposal, by_id)
        shown_id = proposal.player_id
    alt_items = "\n".join(
        item for pid in proposal.alternatives if (item := _alt_item(by_id, pid))
    )
    if not alt_items:
        alt_items = "<li>none</li>"
    flags_block = _flags_block(proposal)
    coin = _bool(proposal.coin_flip)
    coin_label = "yes" if proposal.coin_flip else "no"
    rows = "\n".join(_board_row(row) for row in payload.board)
    weeks = "\n".join(_week_item(cell) for cell in payload.state.weekly if cell.empty)
    if not weeks:
        weeks = "<li>no empty startable slots</li>"
    stale_attr = f' data-stale="{_bool(stale)}"'
    stale_line = '<p class="stale-rec">rec is stale</p>\n' if stale else ""
    return (
        '<section class="recommendation">\n'
        f'<h1 class="rec" data-player-id="{_attr(shown_id)}"{stale_attr}>'
        f"{html.escape(heading)}</h1>\n"
        f"{stale_line}"
        f'<p class="pos">{html.escape(rec_pos)}</p>\n'
        f'<p class="slot-filled">fills {html.escape(slot)}</p>\n'
        f'<p class="why">{html.escape(why)}</p>\n'
        f'<ul class="alternatives">\n{alt_items}\n</ul>\n'
        f'<p class="coin-flip" data-coin-flip="{coin}">coin_flip: {coin_label}</p>\n'
        f"{flags_block}\n"
        "</section>\n"
        '<section class="weekly">\n'
        "<h2>Empty startable slots</h2>\n"
        f"<ol>\n{weeks}\n</ol>\n"
        "</section>\n"
        '<section class="board">\n'
        "<h2>Board</h2>\n"
        "<table>\n"
        "<thead>\n"
        "<tr>"
        "<th>Name</th><th>Pos</th>"
        '<th class="vols">VOLS</th>'
        '<th class="delta">delta</th>'
        "<th>Pts</th>"
        '<th class="ecr">ECR</th>'
        "<th>ADP</th><th>GP</th>"
        "</tr>\n"
        "</thead>\n"
        f"<tbody>\n{rows}\n</tbody>\n"
        "</table>\n"
        "</section>"
    )


def _why_on_screen(
    payload: Payload,
    proposal: Proposal,
    by_id: dict[str, BoardRow],
) -> str:
    """Operator-facing why. Dissent names the VOLS / ECR pick; #20 owns the prompt.

    Both flags can fire on one pick, so the clause is built once and joined,
    never prepended twice. Two prefixes each ending in "because" nest, and the
    first "because" then reads onto the second name instead of onto a reason.
    """

    why = proposal.why
    dissents: list[tuple[str, str]] = []
    if Flag.VOLS_DISSENT in proposal.flags:
        row = by_id.get(payload.hint_argmax_vols)
        if row is not None and row.player_id != proposal.player_id:
            dissents.append((row.name, "VOLS pick"))
    if Flag.ECR_DISAGREE in proposal.flags:
        row = _ecr_best_row(payload.board)
        if row is not None and row.player_id != proposal.player_id:
            dissents.append((row.name, "ECR pick"))

    # The model often names the dissent itself. Match the eval contains-floor
    # (name and label, §5) rather than the exact sentence: an exact match misses
    # every rewording and we print the clause twice.
    dissents = [(n, lab) for n, lab in dissents if n not in why or lab not in why]
    if not dissents:
        return why

    if len(dissents) == 1:
        name, label = dissents[0]
        return f"{name} is the {label}; we are not taking {name} because {why}"

    (vols_name, _), (ecr_name, _) = dissents
    if vols_name == ecr_name:
        lead = f"{vols_name} is the VOLS pick and the ECR pick"
        tail = vols_name
    else:
        lead = f"{vols_name} is the VOLS pick and {ecr_name} is the ECR pick"
        tail = f"{vols_name} or {ecr_name}"
    return f"{lead}; we are not taking {tail} because {why}"


def _ecr_best_row(board: Sequence[BoardRow]) -> BoardRow | None:
    """Overall ECR leader still on the board. Same min as the eval helper."""

    ranked = [row for row in board if row.ecr is not None]
    if not ranked:
        return None
    best = min(row.ecr for row in ranked)
    return next(row for row in ranked if row.ecr == best)


def _alt_item(by_id: dict[str, BoardRow], player_id: str) -> str:
    row = by_id.get(player_id)
    if row is None:
        return ""
    return f'<li data-player-id="{_attr(player_id)}">{html.escape(row.name)}</li>'


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
        f'<td class="ecr">{"" if row.ecr is None else row.ecr}</td>'
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
    return (
        f'<li data-week="{week}" class="has-empty">'
        f"W{week}: {_fmt_num(starter_points)} · empty: {empties}"
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
    age_label = f"Data age: {age_txt}s"
    if degraded or greyed:
        age_label += " — not current"
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
        f"{age_label}</div>\n"
        f'<div class="status" data-status="{_attr(status)}">'
        f"{html.escape(status_line)}</div>\n"
        f"{_notices(banners)}"
        "</header>\n"
        f"{inner}\n"
        "</body>\n"
        "</html>\n"
    )


def _notices(banners: Sequence[Banner]) -> str:
    """One compact line that banners exist. Messages live folded, not 1.5rem red."""

    if not banners:
        return ""
    n = len(banners)
    label = "1 notice" if n == 1 else f"{n} notices"
    items = "\n".join(
        f'<li class="banner" data-code="{_attr(banner.code)}">'
        f"{html.escape(_banner_text(banner))}</li>"
        for banner in banners
    )
    return (
        f'<details class="notices" data-count="{n}">\n'
        f"<summary>{label}</summary>\n"
        f"<ul>\n{items}\n</ul>\n"
        "</details>\n"
    )


def _banner_text(banner: Banner) -> str:
    return _operator_text(banner.message)


def _operator_text(message: str) -> str:
    """Do not dump raw PlatformError JSON at the operator."""

    stripped = message.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "platform error"
    return message


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
