"""Split the model-facing board from the columns `detail` fills back in.

The board the model reads is lean: a first scan needs an id, a name, a value,
a market rank, and the slots a player can fill. The heavier per-player columns
ride behind `detail(player_ids)`, which the model calls for the few players it
is deciding between. See SPEC.md §4.

Both functions read the full serialized payload (`Payload.to_dict`) the
transport already holds. `resolve_detail` is a pure function of that board, so
the same board answers the same way every time — the stability gate survives.
"""

from __future__ import annotations

from typing import Any

# What every board row keeps inline. `ecr` is optional on the row; the rest are
# always present.
LEAN_ROW_KEYS = frozenset(
    {"player_id", "name", "position", "vols", "adp", "ecr", "legal_slots"}
)

# What moves behind `detail`. `points` and `delta_starter_points` are always
# present; `bye`, `gp`, and the ECR spread are optional.
DETAIL_ROW_KEYS = frozenset(
    {"bye", "points", "gp", "delta_starter_points", "ecr_min", "ecr_max", "ecr_std"}
)


def lean_view(payload: dict[str, Any]) -> dict[str, Any]:
    """The payload the model reads: every board row cut to `LEAN_ROW_KEYS`.

    Returns a shallow copy — the caller's full payload keeps its detail columns
    for the tool and for the cassette key.
    """
    lean = dict(payload)
    lean["board"] = [
        {key: value for key, value in row.items() if key in LEAN_ROW_KEYS}
        for row in payload["board"]
    ]
    return lean


def resolve_detail(
    payload: dict[str, Any], player_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """The `detail` tool: heavier columns for each on-board id, keyed by id.

    An id not on the board is dropped, never raised — the tool answers what is
    valid and blocks nothing, the same treatment an off-board rec gets in the
    validator. An absent optional column (a None on the row) stays absent.
    """
    by_id = {row["player_id"]: row for row in payload["board"]}
    detail: dict[str, dict[str, Any]] = {}
    for player_id in player_ids:
        row = by_id.get(player_id)
        if row is None:
            continue
        detail[player_id] = {
            key: value for key, value in row.items() if key in DETAIL_ROW_KEYS
        }
    return detail
