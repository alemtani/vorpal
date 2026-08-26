"""Classify scoring keys. Longer prefix wins. Never silent-zero."""

from __future__ import annotations

from vorpal.contracts import Banner, Slot

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


def classify_key(key: str) -> str | None:
    """Map a scoring key to QB, OFF, K, DEF, or IDP. None if unclassified."""
    if key.startswith("pass_") or key.startswith("bonus_rush_td_qb"):
        return "QB"
    if key.startswith("idp_"):
        return "IDP"
    if key.startswith(("def_", "pts_allow", "yds_allow", "st_")):
        return "DEF"
    if key.startswith(("fgm", "fgmiss", "xpm", "xpmiss")):
        return "K"
    if key.startswith("fum_rec") or key in {
        "sack",
        "int",
        "ff",
        "safe",
        "blk_kick",
        "pr_td",
        "kr_td",
    }:
        return "DEF"
    if key.startswith(("rush_", "bonus_rec", "rec_", "fum_lost")) or key in {
        "rec",
        "fum",
    }:
        return "OFF"
    return None


def scoring_key_banners(
    scoring: dict[str, float],
    slots: tuple[Slot, ...],
    stat_columns: frozenset[str] | None,
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
        group = classify_key(key)
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
