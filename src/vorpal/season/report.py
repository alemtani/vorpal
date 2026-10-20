"""A report is a subject, a few plain lines, and tables. Email renders it."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Table:
    title: str
    header: tuple[str, ...]
    rows: list[tuple[str, ...]]


@dataclass
class Report:
    subject: str
    lines: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    key: str = ""
    """Stable text of the advice. Same key as last send means nothing changed."""


def pts(x: float) -> str:
    return f"{x:.1f}"


def signed(x: float) -> str:
    return f"{x:+.1f}"


DAMPED_NOTE = (
    "Damped projection = 25% touches model + 75% Sleeper/ESPN average."
    " The model drops out for fill-in roles."
)
