"""Redaction happens on the way in. Fixtures must not identify a league."""

from record_fixtures import (
    OPERATOR_USER_ID,
    redact_draft,
    redact_fantasypros,
    redact_league,
    redact_picks,
    redact_user,
    subset_players,
    subset_projections,
)


def test_redact_league_strips_names_and_manager_fields() -> None:
    mapping = {}
    out = redact_league(
        {
            "name": "Guys who watch football",
            "league_id": "1222969602149982208",
            "draft_id": "1222969602162556928",
            "previous_league_id": "1124839415290535936",
            "last_author_display_name": "Scottfish",
            "last_author_id": "861089361775693824",
            "avatar": "abc123",
            "roster_positions": ["QB", "RB", "K", "DEF", "BN"],
            "scoring_settings": {"rec": 1.0},
            "settings": {"type": 0, "max_keepers": 1, "taxi_slots": 0},
        },
        synthetic_league_id="league_snake_redraft",
        synthetic_draft_id="draft_snake_redraft",
        operator_real_id="861089361775693824",
        user_map=mapping,
    )
    assert out["name"] == "League"
    assert out["league_id"] == "league_snake_redraft"
    assert out["draft_id"] == "draft_snake_redraft"
    assert out["previous_league_id"] is None
    assert out["last_author_display_name"] is None
    assert out["last_author_id"] is None
    assert out["avatar"] is None
    assert out["roster_positions"] == ["QB", "RB", "K", "DEF", "BN"]
    assert out["scoring_settings"] == {"rec": 1.0}


def test_redact_draft_maps_operator_and_hides_other_user_ids() -> None:
    mapping: dict[str, str] = {}
    out = redact_draft(
        {
            "draft_id": "1345041367046307840",
            "league_id": "1345041367042097152",
            "type": "snake",
            "status": "complete",
            "metadata": {"name": "The Ryan Leaf Classic", "scoring_type": "2qb"},
            "creators": ["861089361775693824", "999"],
            "draft_order": {
                "861089361775693824": 1,
                "999": 2,
            },
            "slot_to_roster_id": {"1": 1, "2": 2},
            "settings": {"teams": 12, "slots_super_flex": 1, "slots_k": 1},
        },
        synthetic_draft_id="draft_superflex",
        synthetic_league_id="league_superflex",
        operator_real_id="861089361775693824",
        user_map=mapping,
    )
    assert out["draft_id"] == "draft_superflex"
    assert out["league_id"] == "league_superflex"
    assert out["metadata"]["name"] == "Draft"
    assert out["metadata"]["scoring_type"] == "2qb"
    assert out["creators"] == [OPERATOR_USER_ID, "user_01"]
    assert out["draft_order"] == {OPERATOR_USER_ID: 1, "user_01": 2}
    assert "861089361775693824" not in str(out)


def test_redact_draft_keeps_null_league_id() -> None:
    out = redact_draft(
        {
            "draft_id": "1397794077994455040",
            "league_id": None,
            "type": "snake",
            "status": "complete",
            "metadata": {
                "name": "WalterFootball Mock Draft",
                "scoring_type": "half_ppr",
            },
            "creators": None,
            "draft_order": {"404531477133422592": 1},
            "slot_to_roster_id": {"1": 1},
            "settings": {"teams": 12, "slots_k": 1, "slots_def": 1},
        },
        synthetic_draft_id="draft_mock_standalone",
        synthetic_league_id=None,
        operator_real_id="404531477133422592",
        user_map={},
    )
    assert out["league_id"] is None
    assert out["draft_id"] == "draft_mock_standalone"


def test_redact_picks_rewrites_reaction_user_ids() -> None:
    mapping: dict[str, str] = {}
    out = redact_picks(
        [
            {
                "draft_id": "1",
                "player_id": "4866",
                "picked_by": "861089361775693824",
                "pick_no": 1,
                "reactions": {
                    "861089361775693824": ["poop"],
                    "847627141829996544": ["poop"],
                },
            }
        ],
        synthetic_draft_id="draft_snake_redraft",
        operator_real_id="861089361775693824",
        user_map=mapping,
    )
    assert out[0]["reactions"] == {
        "user_operator": ["poop"],
        "user_01": ["poop"],
    }
    assert "861089361775693824" not in str(out)


def test_redact_picks_rewrites_picked_by_and_keeps_player_ids() -> None:
    mapping: dict[str, str] = {}
    out = redact_picks(
        [
            {
                "draft_id": "1222969602162556928",
                "player_id": "4866",
                "picked_by": "861089361775693824",
                "roster_id": 2,
                "pick_no": 1,
                "is_keeper": None,
                "metadata": {
                    "first_name": "Saquon",
                    "last_name": "Barkley",
                    "position": "RB",
                },
            },
            {
                "draft_id": "1222969602162556928",
                "player_id": "9221",
                "picked_by": "",
                "roster_id": None,
                "pick_no": 2,
                "is_keeper": None,
                "metadata": {
                    "first_name": "Jahmyr",
                    "last_name": "Gibbs",
                    "position": "RB",
                },
            },
        ],
        synthetic_draft_id="draft_snake_redraft",
        operator_real_id="861089361775693824",
        user_map=mapping,
    )
    assert out[0]["draft_id"] == "draft_snake_redraft"
    assert out[0]["picked_by"] == OPERATOR_USER_ID
    assert out[0]["player_id"] == "4866"
    assert out[1]["picked_by"] == ""
    assert out[1]["roster_id"] is None
    assert "861089361775693824" not in str(out)


def test_redact_user_keeps_only_the_synthetic_operator() -> None:
    out = redact_user(
        {
            "user_id": "861089361775693824",
            "username": "scottfish",
            "display_name": "Scottfish",
            "avatar": "f0edbf4278f53f9425db175073df6584",
            "email": "hidden@example.com",
            "is_bot": False,
        }
    )
    assert out["user_id"] == OPERATOR_USER_ID
    assert out["username"] == "operator"
    assert out["display_name"] == "Operator"
    assert out["avatar"] is None
    assert "email" not in out
    assert out["is_bot"] is False


def test_subset_players_keeps_requested_ids_and_position_samples() -> None:
    players = {
        "4866": {
            "player_id": "4866",
            "position": "RB",
            "yahoo_id": 1,
            "full_name": "Saquon Barkley",
        },
        "ARI": {
            "player_id": "ARI",
            "position": "DEF",
            "yahoo_id": None,
            "first_name": "Arizona",
        },
        "x": {"player_id": "x", "position": "QB", "yahoo_id": None},
    }
    out = subset_players(players, keep_ids={"4866"}, per_position=1)
    assert "4866" in out
    assert "ARI" in out
    assert "x" in out


def test_subset_projections_keeps_counting_and_market_only_rows() -> None:
    rows = [
        {
            "player_id": "1",
            "company": "rotowire",
            "week": None,
            "stats": {"pass_yd": 4000.0, "pts_ppr": 300.0, "adp_ppr": 12.0, "gp": 17.0},
            "player": {"position": "QB"},
        },
        {
            "player_id": "2",
            "company": "rotowire",
            "week": None,
            "stats": {"adp_ppr": 200.0, "gp": 17.0},
            "player": {"position": "RB"},
        },
        {
            "player_id": "3",
            "company": "rotowire",
            "week": None,
            "stats": {"rush_yd": 1200.0, "adp_ppr": 8.0},
            "player": {"position": "RB"},
        },
    ]
    out = subset_projections(rows, keep_ids={"1"}, per_position=1)
    ids = {row["player_id"] for row in out}
    assert "1" in ids
    assert "2" in ids
    assert "3" in ids
    assert all(row["week"] is None for row in out)


def test_redact_fantasypros_drops_image_urls() -> None:
    out = redact_fantasypros(
        {
            "position_id": "QB",
            "public_api_limited": True,
            "players": [
                {
                    "player_name": "Josh Allen",
                    "player_yahoo_id": "30977",
                    "player_bye_week": "7",
                    "rank_ecr": 1,
                    "rank_std": "0.17",
                    "player_image_url": "https://images.example/a.jpg",
                    "player_square_image_url": "https://images.example/b.jpg",
                }
            ],
        }
    )
    row = out["players"][0]
    assert "player_image_url" not in row
    assert "player_square_image_url" not in row
    assert row["player_yahoo_id"] == "30977"
    assert row["player_bye_week"] == "7"
