"""Live model call. Never selected in CI (`pytest -m "not live"`)."""

from __future__ import annotations

import os

import pytest

from vorpal.contracts import (
    AdpVariant,
    Banner,
    BoardRow,
    DraftState,
    LeagueConfig,
    Need,
    Payload,
    Replacement,
    Slot,
)
from vorpal.model import AnthropicTransport, propose, recommend

pytestmark = pytest.mark.live


def test_live_call_returns_a_board_player() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset")
    payload = Payload(
        config=LeagueConfig(
            teams=12,
            rounds=15,
            slots=(Slot.RB, Slot.WR, Slot.BN),
            scoring={"rec": 1.0},
            scoring_summary="PPR",
            banners=(Banner(code="board_capped", message="board is capped"),),
            slot=1,
            adp_variant=AdpVariant.PPR,
        ),
        state=DraftState(
            pick_no=1,
            user_roster=(),
            needs={"RB": Need(filled=0, required=1)},
            weekly=(),
            recent=(),
            next_user_pick=1,
            picks_until_next=0,
            between=(),
        ),
        replacement={"RB": Replacement(player_id="x", points=100.0)},
        hint_argmax_vols="4866",
        board=(
            BoardRow(
                player_id="4866",
                name="Saquon Barkley",
                position="RB",
                points=280.0,
                vols=40.0,
                delta_starter_points=12.0,
                adp=1.5,
                legal_slots=(Slot.RB,),
                ecr=1,
                ecr_min=1,
            ),
            BoardRow(
                player_id="7564",
                name="Amon-Ra St. Brown",
                position="WR",
                points=250.0,
                vols=30.0,
                delta_starter_points=8.0,
                adp=8.0,
                legal_slots=(Slot.WR,),
                ecr=4,
                ecr_min=2,
            ),
        ),
    )
    proposal = recommend(payload, AnthropicTransport())
    assert proposal.player_id in {"4866", "7564"}

    # The draft-night path against a real response: it must validate on the
    # first call, so nothing degrades and no retry is spent.
    result = propose(payload, AnthropicTransport())
    assert result.degraded is False
    assert result.violations == ()
    assert result.attempts == 1
    assert result.proposal.player_id in {"4866", "7564"}
