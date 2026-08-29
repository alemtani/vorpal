"""Sampler is ADP order plus noise, plus hostile states. Never the model."""

from __future__ import annotations

import random
from pathlib import Path

from builders import board_row, default_board

from vorpal.contracts import Need, Payload, RecentPick, RosterPlayer
from vorpal.evals.sampler import (
    hostile_states,
    remaining_board,
    sample_adp_order,
    sample_board_states,
)


def test_zero_noise_is_adp_order() -> None:
    rows = default_board()
    ordered = sample_adp_order(rows, noise=0.0, rng=random.Random(0))
    assert [row.player_id for row in ordered] == ["rb1", "wr1", "rb2", "te1", "k1"]


def test_noise_moves_the_order() -> None:
    rows = default_board()
    quiet = sample_adp_order(rows, noise=0.0, rng=random.Random(1))
    noisy = sample_adp_order(rows, noise=80.0, rng=random.Random(1))
    assert [row.player_id for row in quiet] != [row.player_id for row in noisy]


def test_sample_is_deterministic_for_a_seed() -> None:
    rows = default_board()
    a = sample_adp_order(rows, noise=5.0, rng=random.Random(7))
    b = sample_adp_order(rows, noise=5.0, rng=random.Random(7))
    assert [row.player_id for row in a] == [row.player_id for row in b]


def test_remaining_board_drops_picked_ids_in_order() -> None:
    rows = default_board()
    order = sample_adp_order(rows, noise=0.0, rng=random.Random(0))
    left = remaining_board(rows, order, n_picked=2)
    assert [row.player_id for row in left] == ["rb2", "te1", "k1"]


def test_sample_board_states_are_successive_remainders() -> None:
    rows = default_board()
    states = sample_board_states(rows, noise=0.0, rng=random.Random(0), n_picks=3)
    assert len(states) == 4  # before any pick, plus 3 remainders
    assert [row.player_id for row in states[0]] == [
        "rb1",
        "wr1",
        "rb2",
        "te1",
        "k1",
    ]
    assert [row.player_id for row in states[-1]] == ["te1", "k1"]


def test_hostile_states_cover_the_spec_situations() -> None:
    states = hostile_states()
    assert set(states) == {
        "empty_starter_late",
        "bye_stack",
        "position_run",
        "vols_compressed",
        "seat_unknown",
    }
    for payload in states.values():
        assert isinstance(payload, Payload)
        assert payload.board


def test_empty_starter_late_has_an_unfilled_starter_near_the_end() -> None:
    payload = hostile_states()["empty_starter_late"]
    total = payload.config.teams * payload.config.rounds
    assert payload.state.pick_no > total / 2
    assert any(
        need.filled == 0 and need.required > 0 for need in payload.state.needs.values()
    )


def test_bye_stack_user_shares_a_bye_with_board_players() -> None:
    payload = hostile_states()["bye_stack"]
    roster_byes = {player.bye for player in payload.state.user_roster}
    board_byes = {row.bye for row in payload.board}
    assert roster_byes & board_byes
    assert any(isinstance(player, RosterPlayer) for player in payload.state.user_roster)


def test_position_run_recent_picks_share_a_position() -> None:
    payload = hostile_states()["position_run"]
    assert len(payload.state.recent) >= 4
    positions = {pick.position for pick in payload.state.recent}
    assert len(positions) == 1
    assert all(isinstance(pick, RecentPick) for pick in payload.state.recent)


def test_vols_compressed_bunches_the_board() -> None:
    payload = hostile_states()["vols_compressed"]
    vols = [row.vols for row in payload.board]
    assert max(vols) - min(vols) <= 2.0


def test_seat_unknown_omits_the_seat() -> None:
    payload = hostile_states()["seat_unknown"]
    assert payload.config.slot is None
    data = payload.to_dict()
    assert "next_user_pick" not in data["state"]
    assert "picks_until_next" not in data["state"]
    assert "between" not in data["state"]


def test_sampler_source_does_not_import_a_model_or_hit_the_network() -> None:
    src = Path(__file__).resolve().parents[2] / "src" / "vorpal" / "evals"
    text = "\n".join(path.read_text() for path in src.glob("*.py"))
    lowered = text.lower()
    for banned in (
        "import anthropic",
        "import openai",
        "import httpx",
        "import requests",
        "vorpal.model",
        "as_judge",
    ):
        assert banned not in lowered


def test_adp_tie_breaks_on_player_id() -> None:
    rows = (
        board_row("b", adp=5.0, vols=1.0),
        board_row("a", adp=5.0, vols=1.0, position="WR"),
    )
    ordered = sample_adp_order(rows, noise=0.0, rng=random.Random(0))
    assert [row.player_id for row in ordered] == ["a", "b"]


def test_needs_type_on_empty_starter() -> None:
    payload = hostile_states()["empty_starter_late"]
    assert all(isinstance(need, Need) for need in payload.state.needs.values())
