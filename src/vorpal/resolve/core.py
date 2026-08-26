"""Resolve slots, scoring source, seat, and ADP variant. Zero network."""

from __future__ import annotations

from dataclasses import dataclass

from vorpal.contracts import (
    IDP_SLOTS,
    AdpVariant,
    Banner,
    Draft,
    League,
    LeagueConfig,
    LeagueFormat,
    Pick,
    Seat,
    Slot,
    SlotCounts,
    User,
)
from vorpal.errors import DataRefusal, UnsupportedLeague, UserRefusal
from vorpal.resolve.keys import scoring_key_banners

_COUNT_FIELDS: tuple[tuple[str, Slot], ...] = (
    ("qb", Slot.QB),
    ("rb", Slot.RB),
    ("wr", Slot.WR),
    ("te", Slot.TE),
    ("flex", Slot.FLEX),
    ("super_flex", Slot.SUPER_FLEX),
    ("op", Slot.OP),
    ("k", Slot.K),
    ("defense", Slot.DEF),
)


@dataclass(frozen=True, slots=True)
class Resolved:
    config: LeagueConfig
    seat: Seat | None
    ecr_position: str | None
    keeper_ids: frozenset[str]


def resolve(
    draft: Draft,
    *,
    operator: User,
    league: League | None = None,
    scoring_league: League | None = None,
    explicit_slot: int | None = None,
    picks: tuple[Pick, ...] = (),
    stat_columns: frozenset[str] | None = None,
) -> Resolved:
    """Configure one draft. Raise UnsupportedLeague or UserRefusal."""
    _refuse_draft_type(draft)
    source, borrowed = _scoring_source(draft, league, scoring_league)
    _refuse_format(source)
    slots = _resolve_slots(draft, league=league if not borrowed else None)
    _refuse_idp(slots)
    seat = _resolve_seat(draft, operator, explicit_slot)
    rec = float(source.scoring.get("rec", 0.0))
    variant, ecr, ecr_pos = _market(slots, rec)
    banners = _banners(
        source=source,
        borrowed=borrowed,
        slots=slots,
        rec=rec,
        stat_columns=stat_columns,
    )
    config = LeagueConfig(
        teams=draft.teams,
        rounds=draft.rounds,
        slots=slots,
        scoring=dict(source.scoring),
        scoring_summary=_summary(variant, ecr, rec),
        banners=banners,
        slot=None if seat is None else seat.slot,
        draft_id=draft.draft_id,
        league_id=draft.league_id,
        scoring_league_id=source.league_id,
        season=draft.season,
        draft_type=draft.type,
        status=draft.status,
        pick_timer=draft.pick_timer,
        reversal_round=draft.reversal_round,
        adp_variant=variant,
        ecr_scoring=ecr,
    )
    keeper_ids = frozenset(pick.player_id for pick in picks if pick.is_keeper)
    return Resolved(
        config=config,
        seat=seat,
        ecr_position=ecr_pos,
        keeper_ids=keeper_ids,
    )


def _refuse_draft_type(draft: Draft) -> None:
    kind = draft.type.lower()
    if kind == "auction":
        raise UnsupportedLeague("Auction drafts are out of v1.")
    if kind == "linear":
        raise UnsupportedLeague("Linear drafts are out of v1.")
    if draft.reversal_round != 0:
        raise UnsupportedLeague("Third-round reversal is out of v1.")


def _scoring_source(
    draft: Draft,
    league: League | None,
    scoring_league: League | None,
) -> tuple[League, bool]:
    if draft.league_id is not None:
        if league is None:
            raise DataRefusal("Draft belongs to a league; pass that league.")
        if league.league_id != draft.league_id:
            raise DataRefusal(
                f"Draft league_id {draft.league_id} does not match "
                f"the passed league {league.league_id}."
            )
        return league, False
    if scoring_league is None:
        raise UserRefusal("Standalone mock needs a scoring-source league.")
    return scoring_league, True


def _refuse_format(source: League) -> None:
    if source.format is LeagueFormat.KEEPER:
        raise UnsupportedLeague("Keeper leagues are out of v1.")
    if source.format is LeagueFormat.DYNASTY:
        raise UnsupportedLeague("Dynasty leagues are out of v1.")
    if source.format is LeagueFormat.UNKNOWN:
        raise UnsupportedLeague("League type is unknown; v1 only supports redraft.")
    if source.taxi_slots > 0:
        raise UnsupportedLeague("Taxi slots are out of v1.")


def _resolve_slots(draft: Draft, *, league: League | None) -> tuple[Slot, ...]:
    if league is not None:
        return league.roster_positions
    return _slots_from_counts(draft.slot_counts, draft.rounds)


def _slots_from_counts(counts: SlotCounts, rounds: int) -> tuple[Slot, ...]:
    slots: list[Slot] = []
    for field, slot in _COUNT_FIELDS:
        slots.extend([slot] * int(getattr(counts, field)))
    if counts.bn is None:
        slots.extend([Slot.BN] * max(0, rounds - len(slots)))
    else:
        slots.extend([Slot.BN] * counts.bn)
    return tuple(slots)


def _refuse_idp(slots: tuple[Slot, ...]) -> None:
    found = sorted({slot.value for slot in slots if slot.value in IDP_SLOTS})
    if found:
        raise UnsupportedLeague(f"IDP slots are out of v1: {', '.join(found)}.")


def _is_complete(order: dict[str, int], teams: int) -> bool:
    return set(range(1, teams + 1)) <= set(order.values())


def _resolve_seat(
    draft: Draft,
    operator: User,
    explicit_slot: int | None,
) -> Seat | None:
    order = draft.draft_order
    if order and operator.user_id in order:
        slot = order[operator.user_id]
        return Seat(
            user_id=operator.user_id,
            slot=slot,
            roster_id=draft.slot_to_roster_id.get(slot),
        )
    complete = bool(order) and _is_complete(order, draft.teams)
    if complete:
        raise UserRefusal(
            "Operator is not in the draft order. The order is complete, "
            "so the seat cannot be guessed."
        )
    partial = bool(order) and not complete
    if partial and explicit_slot is None:
        raise UserRefusal(
            "Operator is not in the draft order. The order is partial; "
            "pass an explicit slot."
        )
    if explicit_slot is None:
        return None
    return Seat(
        user_id=operator.user_id,
        slot=explicit_slot,
        roster_id=draft.slot_to_roster_id.get(explicit_slot),
    )


def _is_two_qb(slots: tuple[Slot, ...]) -> bool:
    if Slot.SUPER_FLEX in slots or Slot.OP in slots:
        return True
    return slots.count(Slot.QB) >= 2


def _rec_bucket(rec: float) -> tuple[AdpVariant, str]:
    if rec >= 0.75:
        return AdpVariant.PPR, "PPR"
    if rec >= 0.25:
        return AdpVariant.HALF_PPR, "HALF"
    return AdpVariant.STD, "STD"


def _market(slots: tuple[Slot, ...], rec: float) -> tuple[AdpVariant, str, str | None]:
    variant, ecr = _rec_bucket(rec)
    if _is_two_qb(slots):
        return AdpVariant.TWO_QB, ecr, "OP"
    return variant, ecr, None


def _summary(variant: AdpVariant, ecr: str, rec: float) -> str:
    names = {"PPR": "PPR", "HALF": "Half PPR", "STD": "Standard"}
    body = names[ecr]
    if rec not in (0.0, 0.5, 1.0):
        body = f"rec={rec:g}"
    if variant is AdpVariant.TWO_QB:
        return f"2QB {body}"
    return body


def _banners(
    *,
    source: League,
    borrowed: bool,
    slots: tuple[Slot, ...],
    rec: float,
    stat_columns: frozenset[str] | None,
) -> tuple[Banner, ...]:
    banners: list[Banner] = []
    if source.format is LeagueFormat.REDRAFT and source.max_keepers > 0:
        banners.append(
            Banner(
                code="keepers_possible",
                message=(
                    "Keepers possible. Players with a truthy is_keeper "
                    "are dropped from the pool."
                ),
            )
        )
    if borrowed:
        banners.append(
            Banner(
                code="slots_from_mock",
                message=(
                    "Slots come from the standalone mock, not from a league roster."
                ),
            )
        )
        banners.append(
            Banner(
                code="scoring_borrowed",
                message=(
                    f"Scoring comes from league {source.league_id}. "
                    "The mock has no scoring table "
                    "(metadata.scoring_type is a label, not a table). "
                    "Slots and scoring may disagree."
                ),
            )
        )
    if rec not in (0.0, 0.5, 1.0):
        banners.append(
            Banner(
                code="rec_nonstandard",
                message=(
                    f"Reception weight is {rec}, not 1, 0.5, or 0. "
                    "ADP and ECR use the nearest bucket."
                ),
            )
        )
    banners.extend(scoring_key_banners(source.scoring, slots, stat_columns))
    return tuple(banners)
