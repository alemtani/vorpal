"""Canonical host scoring tables for standalone mocks.

A standalone mock (`league_id` null) carries slots but no scoring table.
Its `metadata.scoring_type` is a label, not a table, so `resolve` refuses
to borrow scoring from it. These presets are the table that label names.

Not a guess. Sleeper's std, half, and ppr default scoring differ by one
value: `rec` (0.0, 0.5, 1.0). Every other key is identical. The base table
here is a real captured Sleeper default (the same 42 keys as
`tests/fixtures/sleeper/league_superflex.json`). A preset sets `rec`.

Superflex is not a scoring preset. Sleeper's superflex default scoring is
identical to ppr; superflex is a slots and market difference, and those
come from the mock. `resolve._is_two_qb` reads the mock's slots.
"""

from __future__ import annotations

from vorpal.contracts import Host, League, LeagueFormat

# Sleeper default scoring, less `rec`. One captured table, verified against a
# real league export. A preset supplies `rec`; nothing else changes between
# std, half, and ppr.
_SLEEPER_BASE: dict[str, float] = {
    "blk_kick": 2.0,
    "def_st_ff": 1.0,
    "def_st_fum_rec": 1.0,
    "def_st_td": 6.0,
    "def_td": 6.0,
    "ff": 1.0,
    "fgm_0_19": 3.0,
    "fgm_20_29": 3.0,
    "fgm_30_39": 3.0,
    "fgm_40_49": 4.0,
    "fgm_50p": 5.0,
    "fgmiss": -1.0,
    "fum": 0.0,
    "fum_lost": -2.0,
    "fum_rec": 2.0,
    "fum_rec_td": 6.0,
    "int": 2.0,
    "pass_2pt": 2.0,
    "pass_int": -1.0,
    "pass_td": 4.0,
    "pass_yd": 0.04,
    "pts_allow_0": 10.0,
    "pts_allow_14_20": 1.0,
    "pts_allow_1_6": 7.0,
    "pts_allow_21_27": 0.0,
    "pts_allow_28_34": -1.0,
    "pts_allow_35p": -4.0,
    "pts_allow_7_13": 4.0,
    "rec_2pt": 2.0,
    "rec_td": 6.0,
    "rec_yd": 0.1,
    "rush_2pt": 2.0,
    "rush_td": 6.0,
    "rush_yd": 0.1,
    "sack": 1.0,
    "safe": 2.0,
    "st_ff": 1.0,
    "st_fum_rec": 1.0,
    "st_td": 6.0,
    "xpm": 1.0,
    "xpmiss": -1.0,
}

# The one key that names the preset.
_REC_BY_PRESET: dict[str, float] = {
    "std": 0.0,
    "half": 0.5,
    "ppr": 1.0,
}

PRESETS: tuple[str, ...] = tuple(_REC_BY_PRESET)


def preset_scoring(name: str) -> dict[str, float]:
    """The full Sleeper default scoring table for a preset name."""
    rec = _REC_BY_PRESET[name]
    return {**_SLEEPER_BASE, "rec": rec}


def preset_league(name: str, season: str, host: Host = Host.SLEEPER) -> League:
    """A synthetic scoring source for a standalone mock.

    Only `scoring` is read from a borrowed source; slots come from the mock.
    `format` and `taxi_slots` are set so the redraft refusals pass. The
    `league_id` names the preset so the `scoring_borrowed` banner is honest.
    """
    return League(
        host=host,
        league_id=f"sleeper-default-{name}",
        draft_id="",
        season=season,
        status="",
        sport="nfl",
        season_type="regular",
        total_rosters=0,
        roster_positions=(),
        scoring=preset_scoring(name),
        format=LeagueFormat.REDRAFT,
        max_keepers=0,
        taxi_slots=0,
        num_teams=0,
    )
