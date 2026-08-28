"""Classify scoring keys from the shared host table. Never guess from a prefix."""

from __future__ import annotations

from vorpal.contracts import Banner, Host, Slot
from vorpal.platform.scoring_keys import SCORING_KEY_GROUP

_STARTABLE: dict[str, frozenset[Slot]] = {
    "QB": frozenset({Slot.QB, Slot.SUPER_FLEX, Slot.OP}),
    "OFF": frozenset(
        {
            Slot.RB,
            Slot.WR,
            Slot.TE,
            Slot.FLEX,
            Slot.SUPER_FLEX,
            Slot.OP,
            Slot.WRRB_FLEX,
            Slot.REC_FLEX,
        }
    ),
    "K": frozenset({Slot.K}),
    "DEF": frozenset({Slot.DEF}),
    "IDP": frozenset({Slot.DL, Slot.LB, Slot.DB, Slot.IDP_FLEX}),
}

_GROUP_ORDER = ("QB", "OFF", "K", "DEF", "IDP")


def classify_key(key: str, host: Host = Host.SLEEPER) -> str | None:
    """Look up a host scoring key. None if that host has no row for it."""
    return SCORING_KEY_GROUP.get(host, {}).get(key)


def scoring_key_banners(
    scoring: dict[str, float],
    slots: tuple[Slot, ...],
    stat_columns: frozenset[str] | None,
    host: Host = Host.SLEEPER,
) -> tuple[Banner, ...]:
    """Itemise unknown nonzero keys. One line for classified keys with no slot."""
    banners: list[Banner] = []
    if stat_columns is not None:
        unknown = sorted(
            key
            for key, weight in scoring.items()
            if weight != 0 and key not in stat_columns
        )
        if unknown:
            listed = ", ".join(unknown)
            banners.append(
                Banner(
                    code="unknown_scoring_keys",
                    message=(
                        f"Nonzero scoring keys with no matching stat column: "
                        f"{listed}. Those keys score as 0 unless you supply "
                        f"an override."
                    ),
                )
            )
    startable = {slot for slot in slots if slot is not Slot.BN}
    seen: set[str] = set()
    for key, weight in scoring.items():
        if weight == 0:
            continue
        group = classify_key(key, host)
        if group is None or group in seen:
            continue
        if not (_STARTABLE[group] & startable):
            seen.add(group)
    missing = [group for group in _GROUP_ORDER if group in seen]
    if missing:
        names = ", ".join(missing)
        banners.append(
            Banner(
                code="unstartable_scoring",
                message=(
                    f"Scoring includes {names} keys but the roster has no "
                    f"startable {names} slot. Those keys score as 0 unless "
                    f"you supply an override."
                ),
            )
        )
    return tuple(banners)
