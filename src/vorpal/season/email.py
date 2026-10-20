"""Render a report as text + HTML and send it through Gmail SMTP."""

from __future__ import annotations

import html
import smtplib
from collections.abc import Callable, Sequence
from email.message import EmailMessage

from vorpal.season.report import Report, Table

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _text_table(t: Table) -> list[str]:
    widths = [
        max(len(str(c)) for c in col) for col in zip(t.header, *t.rows, strict=True)
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    return [t.title, fmt.format(*t.header), *(fmt.format(*r) for r in t.rows), ""]


def render_text(r: Report) -> str:
    out = [r.subject, "", *r.lines, ""]
    for t in r.tables:
        out.extend(_text_table(t) if t.rows else [t.title, "(none)", ""])
    return "\n".join(out)


def render_html(r: Report) -> str:
    e = html.escape
    parts = [
        '<div style="font-family:-apple-system,Segoe UI,sans-serif;font-size:14px">',
        f"<h2 style='margin:0 0 8px'>{e(r.subject)}</h2>",
    ]
    parts.extend(f"<p style='margin:4px 0'>{e(ln)}</p>" for ln in r.lines)
    cell = "padding:3px 8px;border-bottom:1px solid #ddd;text-align:left"
    for t in r.tables:
        parts.append(f"<h3 style='margin:16px 0 4px'>{e(t.title)}</h3>")
        parts.append("<table style='border-collapse:collapse'>")
        parts.append(
            "<tr>"
            + "".join(f"<th style='{cell}'>{e(h)}</th>" for h in t.header)
            + "</tr>"
        )
        for row in t.rows:
            parts.append(
                "<tr>"
                + "".join(f"<td style='{cell}'>{e(c)}</td>" for c in row)
                + "</tr>"
            )
        parts.append("</table>")
    parts.append("</div>")
    return "\n".join(parts)


def send(
    r: Report,
    to: Sequence[str],
    sender: str,
    password: str,
    smtp: Callable[[str, int], smtplib.SMTP] = smtplib.SMTP_SSL,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = r.subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg.set_content(render_text(r))
    msg.add_alternative(render_html(r), subtype="html")
    with smtp(SMTP_HOST, SMTP_PORT) as server:
        server.login(sender, password)
        server.send_message(msg)
