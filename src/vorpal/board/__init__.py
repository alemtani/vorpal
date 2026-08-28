"""Local HTML board and the draft-night poll loop."""

from vorpal.board.loop import DraftPollClient, Frame, run_loop, write_html
from vorpal.board.render import render, render_unavailable
from vorpal.board.schedule import (
    is_degraded,
    is_greyed_out,
    next_backoff,
    poll_interval,
)

__all__ = [
    "DraftPollClient",
    "Frame",
    "is_degraded",
    "is_greyed_out",
    "next_backoff",
    "poll_interval",
    "render",
    "render_unavailable",
    "run_loop",
    "write_html",
]
