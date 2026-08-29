"""Regenerate `tests/regret/fixtures/*.json` from the recorded drafts.

    uv run python tests/regret/build.py

The committed JSON is derived, never hand-edited. `test_regret.py`
rebuilds every fixture and compares byte for byte, so an edit here that
does not come from the recorded picks fails the suite.

Four seats across three completed drafts. Breadth of situation over
volume: an early-round tier drain, a late round where the board is flat,
a superflex second round, and a mock with CPU autopick — which is a
weaker record on purpose, and says so in its own `provenance` field.
"""

from __future__ import annotations

from replay import FIXTURES, RegretFixture, replay

SPECS: tuple[dict, ...] = (
    {
        "name": "snake_redraft_seat02_r03",
        "draft": "snake_redraft",
        "draft_slot": 2,
        "round_no": 3,
        "provenance": (
            "League-attached 12-team snake redraft, PPR, played to completion "
            "by twelve human seats. Read through the documented Sleeper draft "
            "and picks endpoints and redacted on the way in."
        ),
        "era": (
            "2025 preseason ADP. The order these players came off the board is "
            "a 2025 market, not the market this tool will draft into. Survival "
            "here is a fact about that room in that season and nothing more."
        ),
    },
    {
        "name": "snake_redraft_seat02_r09",
        "draft": "snake_redraft",
        "draft_slot": 2,
        "round_no": 9,
        "provenance": (
            "Same completed draft, same seat, six rounds later. The late board "
            "is where VOLS compresses and wait-or-take stops being obvious."
        ),
        "era": (
            "2025 preseason ADP. Late-round order in any recorded draft is the "
            "noisiest part of the record: it is where a room's habits, not the "
            "market, decide who goes when."
        ),
    },
    {
        "name": "superflex_seat07_r02",
        "draft": "superflex",
        "draft_slot": 7,
        "round_no": 2,
        "provenance": (
            "Completed 12-team superflex snake, 18 rounds, K and no DEF. The "
            "second round of a superflex draft is where the quarterback run "
            "happens, so it is the pick worth freezing."
        ),
        "era": (
            "2026 preseason ADP in a superflex room. Quarterback survival in "
            "superflex is the most format-specific number in this directory; "
            "do not read it across to a one-QB league."
        ),
    },
    {
        "name": "mock_standalone_seat06_r05",
        "draft": "mock_standalone",
        "draft_slot": 6,
        "round_no": 5,
        "provenance": (
            "Standalone mock, league_id null, cpu_autopick on: 32 of 192 picks "
            "were made by the platform's autopick, not by a person. A weaker "
            "record than the two league drafts, kept because a mock room drafts "
            "closer to raw ADP and that is a different failure mode to measure "
            "against."
        ),
        "era": (
            "2026 preseason ADP, half-PPR. Autopicked seats follow the "
            "platform's own ranking, so survival in this draft is partly a "
            "measurement of that ranking rather than of a room."
        ),
    },
)


def build() -> tuple[RegretFixture, ...]:
    return tuple(replay(**spec) for spec in SPECS)


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for fixture in build():
        (FIXTURES / f"{fixture.name}.json").write_text(fixture.to_json())
        print(f"wrote {fixture.name}")


if __name__ == "__main__":
    main()
