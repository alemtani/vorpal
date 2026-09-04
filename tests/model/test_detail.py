"""Lean view and detail resolver: pure dict → dict, no network.

The board ships lean to the model; `detail` fills the heavier columns back in
for named ids. Both read the full serialized payload the transport already
holds. See SPEC.md §4.
"""

from __future__ import annotations

from vorpal.model.detail import (
    DETAIL_ROW_KEYS,
    LEAN_ROW_KEYS,
    lean_view,
    resolve_detail,
)


def _full_payload() -> dict:
    return {
        "config": {"teams": 12},
        "hint_argmax_vols": "a",
        "board": [
            {
                "player_id": "a",
                "name": "Alpha",
                "position": "RB",
                "vols": 40.0,
                "adp": 3.0,
                "ecr": 4,
                "legal_slots": ["RB", "FLEX"],
                "points": 280.0,
                "delta_starter_points": 12.0,
                "gp": 17.0,
                "bye": 9,
                "ecr_min": 2,
                "ecr_max": 8,
                "ecr_std": 1.5,
            },
            {
                # A row with the optional columns absent (all-None on the object).
                "player_id": "b",
                "name": "Bravo",
                "position": "WR",
                "vols": 12.0,
                "adp": 90.0,
                "legal_slots": ["WR", "FLEX"],
                "points": 132.0,
                "delta_starter_points": 0.0,
            },
        ],
    }


def test_lean_view_keeps_only_the_lean_columns() -> None:
    lean = lean_view(_full_payload())
    for row in lean["board"]:
        assert set(row) <= LEAN_ROW_KEYS
    # ecr is present on a, absent on b — optionals stay optional.
    assert lean["board"][0]["player_id"] == "a"
    assert "ecr" in lean["board"][0]
    assert "ecr" not in lean["board"][1]


def test_lean_view_drops_every_detail_column() -> None:
    lean = lean_view(_full_payload())
    for row in lean["board"]:
        assert DETAIL_ROW_KEYS.isdisjoint(row)


def test_lean_view_leaves_non_board_fields_untouched() -> None:
    lean = lean_view(_full_payload())
    assert lean["config"] == {"teams": 12}
    assert lean["hint_argmax_vols"] == "a"


def test_lean_view_does_not_mutate_the_input() -> None:
    payload = _full_payload()
    lean_view(payload)
    assert "delta_starter_points" in payload["board"][0]


def test_resolve_detail_returns_detail_columns_by_id() -> None:
    detail = resolve_detail(_full_payload(), ["a"])
    assert set(detail) == {"a"}
    assert detail["a"]["delta_starter_points"] == 12.0
    assert detail["a"]["ecr_std"] == 1.5
    assert detail["a"]["bye"] == 9
    # Never leaks a lean column back.
    assert LEAN_ROW_KEYS.isdisjoint(detail["a"])


def test_resolve_detail_omits_absent_optionals() -> None:
    detail = resolve_detail(_full_payload(), ["b"])
    assert detail["b"]["delta_starter_points"] == 0.0
    assert "gp" not in detail["b"]
    assert "ecr_std" not in detail["b"]


def test_resolve_detail_drops_off_board_ids_never_errors() -> None:
    detail = resolve_detail(_full_payload(), ["a", "ghost"])
    assert set(detail) == {"a"}


def test_resolve_detail_empty_request_is_empty() -> None:
    assert resolve_detail(_full_payload(), []) == {}
