"""Business logic for the venue module.

Same shape as ``app.modules.auth.services``: routes call these functions, tests
call them directly, and other modules call them instead of touching the models.
Every function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

from flask import current_app
from sqlalchemy import ColumnElement, and_, delete, not_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.clock import as_utc, to_business_time
from app.common.database import resolve_session
from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.preparation import PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE
from app.common.validation import load_or_raise
from app.modules.auth.permissions import Role
from app.modules.auth.services import list_user_ids_with_role
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users
from app.modules.venue.models import (
    DECIDABLE_REQUEST_STATUSES,
    FLAGGABLE_REQUEST_STATUSES,
    HOLDABLE_REQUEST_STATUSES,
    HOLDING_BOOKING_STATUSES,
    RETIRED_REQUEST_STATUSES,
    AlternativeVenueFlag,
    Booking,
    BookingDecision,
    BookingRequestStatus,
    BookingStatus,
    CalendarEntryKind,
    RequirementKind,
    Venue,
    VenueBlock,
    VenueBookingRequest,
    VenueOpeningPeriod,
    Weekday,
    join_list_field,
)
from app.modules.venue.opening_hours import Period, covers_period
from app.modules.venue.schemas import (
    BlockVenueSchema,
    BookingRequestAsShown,
    ChangeArrangementSchema,
    DecideBookingRequestSchema,
    EditVenueSchema,
    HoldBookingRequestSchema,
    RaiseBookingRequestSchema,
    UnavailabilitySchema,
    UpdatePreparationSchema,
    VenueSearchSchema,
    VenueSuitabilitySchema,
)

if TYPE_CHECKING:
    # Type only: events.services reaches this module through equipment, so
    # raise_booking_request imports the module when it runs.
    from app.modules.events.services import EventForBooking

logger = logging.getLogger("connectsphere.venue")

_LIST_FIELDS = ("facilities", "accessibility_features", "supported_layouts")


def _default_minutes(config_key: str) -> int:
    """The configured setup or turnaround default, for a venue without its own."""
    return int(current_app.config[config_key])


def _buffers(venue: Venue) -> tuple[timedelta, timedelta]:
    """The venue's setup and turnaround time (SCRUM-67)."""
    return timedelta(minutes=venue.setup_minutes), timedelta(minutes=venue.turnaround_minutes)


def _occupied(venue: Venue, start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """The period an event holds the venue, with setup and turnaround (ADR-0011)."""
    setup, turnaround = _buffers(venue)
    return start - setup, end + turnaround


def _build_periods(periods: Iterable[Period]) -> list[VenueOpeningPeriod]:
    return [VenueOpeningPeriod(**period._asdict()) for period in periods]


# --------------------------------------------------------------------------
# SCRUM-25 — catalogue CRUD, deactivate/reactivate
# --------------------------------------------------------------------------


def get_venue(venue_id: int, *, session: Session | None = None) -> Venue:
    """Fetch a venue by primary key, active or not.

    Raises:
        NotFoundError: if no such venue exists.
    """
    venue = resolve_session(session).get(Venue, venue_id)
    if venue is None:
        raise NotFoundError("Venue not found.")
    return venue


def list_venues(*, session: Session | None = None) -> list[Venue]:
    """Active venues only — a deactivated venue no longer appears here (AC5)."""
    stmt = select(Venue).where(Venue.is_active.is_(True)).order_by(Venue.name)
    return list(resolve_session(session).scalars(stmt).all())


def create_venue(payload: Mapping[str, Any] | None, *, session: Session | None = None) -> Venue:
    """Create a venue (SCRUM-25 AC1/AC2).

    Raises:
        ValidationError: 400 — missing/blank required fields or invalid values.
    """
    data = load_or_raise(EditVenueSchema(), payload)
    sess = resolve_session(session)

    venue = Venue(
        name=data["name"],
        location=data["location"],
        capacity=data["capacity"],
        facilities=join_list_field(data["facilities"]),
        accessibility_features=join_list_field(data["accessibility_features"]),
        supported_layouts=join_list_field(data["supported_layouts"]),
        opening_periods=_build_periods(data["opening_hours"]),
        setup_minutes=data.get("setup_minutes", _default_minutes("DEFAULT_VENUE_SETUP_MINUTES")),
        turnaround_minutes=data.get(
            "turnaround_minutes", _default_minutes("DEFAULT_VENUE_TURNAROUND_MINUTES")
        ),
    )
    sess.add(venue)
    sess.commit()
    return venue


@dataclass(frozen=True)
class OverlapWarning:
    """Two confirmed bookings whose padded periods overlap (SCRUM-67 AC4)."""

    booking_ids: tuple[int, int]
    overlap_start: datetime
    overlap_end: datetime


def _shared_period(
    first: tuple[datetime, datetime], second: tuple[datetime, datetime]
) -> tuple[datetime, datetime] | None:
    """The time two periods have in common, or ``None`` if they don't overlap.

    Periods that only touch (one ends at 11:00, the next starts at 11:00) share nothing.
    """
    first_start, first_end = first
    second_start, second_end = second
    shared_start = max(first_start, second_start)
    shared_end = min(first_end, second_end)
    if shared_start < shared_end:
        return shared_start, shared_end
    return None


def _holding_bookings(venue: Venue, session: Session) -> list[Booking]:
    """The venue's confirmed and Conflicting bookings, in start order."""
    stmt = (
        select(Booking)
        .where(Booking.venue_id == venue.id, Booking.status.in_(HOLDING_BOOKING_STATUSES))
        .order_by(Booking.start_time, Booking.id)
    )
    return list(session.scalars(stmt))


def _blocks_in_start_order(venue: Venue, session: Session) -> list[VenueBlock]:
    """The venue's blocks, earliest first."""
    stmt = (
        select(VenueBlock)
        .where(VenueBlock.venue_id == venue.id)
        .order_by(VenueBlock.start_time, VenueBlock.id)
    )
    return list(session.scalars(stmt))


def _confirmed_overlaps(venue: Venue, bookings: list[Booking]) -> list[OverlapWarning]:
    """Every pair of ``bookings`` whose padded periods overlap."""
    warnings: list[OverlapWarning] = []
    for index, first in enumerate(bookings):
        first_held = _occupied(venue, first.start_time, first.end_time)
        for second in bookings[index + 1 :]:
            second_held = _occupied(venue, second.start_time, second.end_time)
            shared = _shared_period(first_held, second_held)
            if shared is not None:
                overlap_start, overlap_end = shared
                warnings.append(OverlapWarning((first.id, second.id), overlap_start, overlap_end))
    return warnings


@dataclass(frozen=True)
class BlockOverlapWarning:
    """A confirmed booking whose padded period overlaps a block (SCRUM-67 AC4)."""

    booking_id: int
    block_id: int
    overlap_start: datetime
    overlap_end: datetime


def _block_overlaps(
    venue: Venue, bookings: list[Booking], session: Session
) -> list[BlockOverlapWarning]:
    """Each of ``bookings`` whose padded period overlaps one of the venue's blocks.

    The block itself isn't padded (ADR-0011), the same rule a new block's conflict
    check uses (ADR-0016).
    """
    blocks = _blocks_in_start_order(venue, session)
    warnings: list[BlockOverlapWarning] = []
    for booking in bookings:
        held = _occupied(venue, booking.start_time, booking.end_time)
        for block in blocks:
            shared = _shared_period(held, (block.start_time, block.end_time))
            if shared is not None:
                overlap_start, overlap_end = shared
                warnings.append(
                    BlockOverlapWarning(booking.id, block.id, overlap_start, overlap_end)
                )
    return warnings


def _mark_conflicting(
    bookings: list[Booking],
    overlaps: list[OverlapWarning],
    block_overlaps: list[BlockOverlapWarning],
) -> None:
    """Mark each of ``bookings`` that a warning names as Conflicting (SCRUM-44)."""
    affected_ids: set[int] = set()
    for overlap in overlaps:
        affected_ids.update(overlap.booking_ids)
    for block_overlap in block_overlaps:
        affected_ids.add(block_overlap.booking_id)
    for booking in bookings:
        if booking.id in affected_ids:
            booking.status = BookingStatus.CONFLICTING


# --------------------------------------------------------------------------
# SCRUM-92 — flag the arrangements a venue becoming unavailable affects
# --------------------------------------------------------------------------

#: How a notice writes a time, in business time (SCRUM-92 AC5).
NOTICE_TIME_FORMAT = "%Y-%m-%d %H:%M"
#: How a notice ends a deactivation's period, which has no end (AC9).
UNTIL_REACTIVATED = "until it is reactivated"


@dataclass(frozen=True)
class AlternativeVenueNotice:
    """What the coordinator of one flagged arrangement's event is to be told (AC5)."""

    event_id: int
    detail: str


def _notice_time(moment: datetime) -> str:
    return to_business_time(as_utc(moment)).strftime(NOTICE_TIME_FORMAT)


def _notice_detail(venue: Venue, flag: AlternativeVenueFlag) -> str:
    """The venue, the reason and the period, as the coordinator is told (AC5).

    For example ``"Main Hall is unavailable from 2026-11-01 10:00 to 2026-11-01 11:00
    (equipment failure): Lift broken."``, in business time.
    """
    until = UNTIL_REACTIVATED if flag.ends_at is None else f"to {_notice_time(flag.ends_at)}"
    return (
        f"{venue.name} is unavailable from {_notice_time(flag.starts_at)} {until}"
        f" ({flag.category.label}): {flag.reason}"
    )


def _flag_details(arrangement: VenueBookingRequest, flag: AlternativeVenueFlag) -> dict[str, Any]:
    """The flag as the event's history entry records it, times in UTC (AC1)."""
    ends_at = None
    if flag.ends_at is not None:
        ends_at = as_utc(flag.ends_at).isoformat()
    return {
        "venue_booking_request_id": arrangement.id,
        "venue_id": arrangement.venue_id,
        "category": flag.category.value,
        "reason": flag.reason,
        "starts_at": as_utc(flag.starts_at).isoformat(),
        "ends_at": ends_at,
    }


def _flag_arrangements(
    arrangements: list[VenueBookingRequest],
    venue: Venue,
    unavailability: Mapping[str, Any],
    session: Session | None,
) -> list[AlternativeVenueNotice]:
    """Flag each arrangement "Needs Alternative Venue", without committing (AC1, AC3).

    Each gets its own flag, made from ``unavailability`` (the flag's columns), and a
    history entry on its event, which sends a Confirmed event back to Approved. The
    notices are returned rather than sent, so they go out after the caller's commit
    (ADR-0015).
    """
    from app.modules.events import services as event_services  # circular at import time

    notices = []
    for arrangement in arrangements:
        flag = AlternativeVenueFlag(**unavailability)
        arrangement.flags.append(flag)
        event_services.record_alternative_venue_needed(
            arrangement.event_id, details=_flag_details(arrangement, flag), session=session
        )
        notices.append(AlternativeVenueNotice(arrangement.event_id, _notice_detail(venue, flag)))
    return notices


def _tell_coordinators(notices: list[AlternativeVenueNotice], session: Session | None) -> None:
    """Tell each flagged arrangement's coordinator, once the flags are saved (AC5)."""
    from app.modules.events import services as event_services  # circular at import time

    for notice in notices:
        event_services.notify_coordinator_alternative_venue_needed(
            notice.event_id, detail=notice.detail, session=session
        )


def _arrangements_held_during(
    venue: Venue, start: datetime, end: datetime, session: Session
) -> list[VenueBookingRequest]:
    """The venue's live arrangements that hold it at any time in ``start``-``end``.

    An arrangement holds the venue from its start minus setup to its end plus
    turnaround (ADR-0011), the rule a block's conflicting bookings use (ADR-0016).
    Earliest first.
    """
    setup, turnaround = _buffers(venue)
    stmt = (
        select(VenueBookingRequest)
        .where(
            VenueBookingRequest.venue_id == venue.id,
            VenueBookingRequest.status.in_(FLAGGABLE_REQUEST_STATUSES),
            VenueBookingRequest.starts_at < end + setup,
            VenueBookingRequest.ends_at > start - turnaround,
        )
        .order_by(VenueBookingRequest.starts_at, VenueBookingRequest.id)
    )
    return list(session.scalars(stmt))


def _arrangements_not_ended(
    venue: Venue, now: datetime, session: Session
) -> list[VenueBookingRequest]:
    """The venue's live arrangements that end after ``now``, earliest first (AC9)."""
    stmt = (
        select(VenueBookingRequest)
        .where(
            VenueBookingRequest.venue_id == venue.id,
            VenueBookingRequest.status.in_(FLAGGABLE_REQUEST_STATUSES),
            VenueBookingRequest.ends_at > now,
        )
        .order_by(VenueBookingRequest.starts_at, VenueBookingRequest.id)
    )
    return list(session.scalars(stmt))


def update_venue(
    venue_id: int, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> tuple[Venue, list[OverlapWarning], list[BlockOverlapWarning]]:
    """Update a venue's editable fields (SCRUM-25 AC1/AC2, SCRUM-67 AC1/AC4).

    Only the fields present in ``payload`` are changed. ``opening_hours``, if
    present, replaces the whole weekly schedule (ADR-0008).

    If the setup or turnaround time changes, bookings and blocks are re-checked against
    the new padding (ADR-0033). Every pair of bookings that now overlaps is returned,
    and so is every booking that now runs into a block. Each booking returned is marked
    Conflicting in the same commit as the change (SCRUM-44, ADR-0045); nothing is
    deleted or cancelled.

    Returns:
        The updated venue, the bookings that overlap each other and the bookings that
        overlap a block; both lists are empty unless a buffer changed.

    Raises:
        NotFoundError: 404 — no such venue.
        ValidationError: 400 — invalid values for the supplied fields.
    """
    schema = EditVenueSchema()
    # Field names, not True: True would also let an incomplete period through.
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    buffers_before = _buffers(venue)

    if "opening_hours" in data:
        venue.opening_periods = _build_periods(data.pop("opening_hours"))
    for field in _LIST_FIELDS:
        if field in data:
            data[field] = join_list_field(data[field])
    for key, value in data.items():
        setattr(venue, key, value)

    if _buffers(venue) == buffers_before:
        sess.commit()
        return venue, [], []
    bookings = _holding_bookings(venue, sess)
    overlaps = _confirmed_overlaps(venue, bookings)
    block_overlaps = _block_overlaps(venue, bookings, sess)
    _mark_conflicting(bookings, overlaps, block_overlaps)
    sess.commit()
    return venue, overlaps, block_overlaps


def deactivate_venue(
    venue_id: int,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> Venue:
    """Deactivate a venue, saying why (SCRUM-25 AC5, SCRUM-92 AC9).

    It drops out of listing and search. Every arrangement at it that has not ended is
    flagged "Needs Alternative Venue" with the category and note, from ``now`` with no
    end, as a block would flag it. The flags, their history entries and any Confirmed
    event's return to Approved are saved with the deactivation, and each coordinator is
    told afterwards (ADR-0053). Deactivating a venue that is already inactive changes
    nothing, so its arrangements are not flagged twice.

    Args:
        venue_id: The venue to deactivate.
        payload: Decoded JSON body: ``category`` and ``reason``, the note.
        session: Database session; defaults to ``db.session``.
        now: When it happened; defaults to the current instant.

    Raises:
        ValidationError: 400 — no category, or no note (details per field).
        NotFoundError: 404 — no such venue.
    """
    data = load_or_raise(UnavailabilitySchema(), payload)
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    if not venue.is_active:
        return venue
    if now is None:
        now = datetime.now(timezone.utc)

    venue.is_active = False
    unavailability = {**data, "venue_block_id": None, "starts_at": now, "ends_at": None}
    arrangements = _arrangements_not_ended(venue, now, sess)
    notices = _flag_arrangements(arrangements, venue, unavailability, session)
    sess.commit()
    _tell_coordinators(notices, session)
    return venue


def reactivate_venue(venue_id: int, *, session: Session | None = None) -> Venue:
    """Reactivate a previously deactivated venue (SCRUM-25 AC6, SCRUM-92 AC8).

    The flags its deactivation left are cleared, so those arrangements stand again;
    flags from blocks stay until each block is removed.
    """
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    venue.is_active = True
    arrangements_here = select(VenueBookingRequest.id).where(
        VenueBookingRequest.venue_id == venue.id
    )
    sess.execute(
        delete(AlternativeVenueFlag).where(
            AlternativeVenueFlag.venue_block_id.is_(None),
            AlternativeVenueFlag.booking_request_id.in_(arrangements_here),
        )
    )
    sess.commit()
    return venue


# --------------------------------------------------------------------------
# SCRUM-26 — availability calendar
# --------------------------------------------------------------------------

#: How each non-cancelled booking status shows on the calendar. A Conflicting booking
#: still holds the venue, so it shows as the confirmed booking it is (SCRUM-44).
_CALENDAR_KIND_BY_STATUS = {
    BookingStatus.CONFIRMED: CalendarEntryKind.CONFIRMED_BOOKING,
    BookingStatus.TENTATIVE: CalendarEntryKind.TENTATIVE_HOLD,
    BookingStatus.CONFLICTING: CalendarEntryKind.CONFIRMED_BOOKING,
}


def _overlaps(
    model: type[Booking] | type[VenueBlock], start: datetime, end: datetime
) -> ColumnElement[bool]:
    """SQL condition: the row's period overlaps ``start``-``end``.

    Periods that only touch (one ends at 11:00, the next starts at 11:00) don't overlap.
    """
    return and_(model.start_time < end, model.end_time > start)


def _utc_now() -> datetime:
    """The current instant, which a hold's expiry is compared with."""
    return datetime.now(timezone.utc)


def _booking_is_live(now: datetime) -> ColumnElement[bool]:
    """SQL condition: the booking holds its venue at ``now`` (SCRUM-75).

    Every booking does except a cancelled one and a tentative hold whose expiry has
    passed. The check is made when the booking is read, so a hold stops counting the
    moment it expires; marking it Expired is SCRUM-94's. A tentative booking with no
    expiry was made before holds had one and never lapses.
    """
    expired_hold = and_(
        Booking.status == BookingStatus.TENTATIVE,
        Booking.hold_expires_at.is_not(None),
        Booking.hold_expires_at <= now,
    )
    return and_(Booking.status != BookingStatus.CANCELLED, not_(expired_hold))


def _booking_holds_venue(venue: Venue, start: datetime, end: datetime) -> ColumnElement[bool]:
    """SQL condition: a booking on ``venue`` holds it at any time in ``start``-``end``.

    A booking holds its venue from ``start - setup`` to ``end + turnaround``
    (ADR-0011), so the period is widened by the same amounts to catch a booking whose
    padding reaches into it.
    """
    setup, turnaround = _buffers(venue)
    return and_(Booking.venue_id == venue.id, _overlaps(Booking, start - turnaround, end + setup))


def _booking_reason(booking: Booking, viewer_role: Role) -> str:
    """Venue Staff see which event holds the venue; others only that it's booked."""
    if viewer_role is not Role.VENUE_STAFF:
        return "booking"
    if booking.event_id is None:
        return "Booking (no linked event)"
    return f"Event #{booking.event_id}"


def _block_reason(block: VenueBlock, viewer_role: Role) -> str:
    """Venue Staff see why a venue is blocked; others only that it's maintenance."""
    if viewer_role is not Role.VENUE_STAFF:
        return "maintenance"
    return block.reason or "Maintenance"


@dataclass(frozen=True)
class CalendarEntry:
    """One period a venue is unavailable, as its calendar shows it."""

    start_time: datetime
    end_time: datetime
    event_start: datetime | None
    event_end: datetime | None
    kind: CalendarEntryKind
    reason: str


def get_venue_calendar(
    venue_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    viewer_role: Role,
    session: Session | None = None,
) -> list[CalendarEntry]:
    """A venue's unavailable periods that overlap a range, in time order (SCRUM-26).

    Confirmed bookings, tentative holds and blocked periods are all shown, each marked
    with its kind; cancelled bookings and expired holds aren't. How much of the reason a
    viewer sees depends on their role (AC3). A booking is shown as the period it holds
    the venue, padded by setup and turnaround, with the event's own times alongside
    (SCRUM-67); a block isn't padded, so its event times are ``None``.

    Raises:
        NotFoundError: 404 — no such venue.
    """
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)

    bookings = sess.scalars(
        select(Booking).where(
            _booking_is_live(_utc_now()),
            _booking_holds_venue(venue, range_start, range_end),
        )
    )
    blocks = sess.scalars(
        select(VenueBlock).where(
            VenueBlock.venue_id == venue.id, _overlaps(VenueBlock, range_start, range_end)
        )
    )

    entries: list[CalendarEntry] = []
    for booking in bookings:
        kind = _CALENDAR_KIND_BY_STATUS[booking.status]
        reason = _booking_reason(booking, viewer_role)
        occupied_start, occupied_end = _occupied(venue, booking.start_time, booking.end_time)
        entries.append(
            CalendarEntry(
                occupied_start, occupied_end, booking.start_time, booking.end_time, kind, reason
            )
        )
    for block in blocks:
        reason = _block_reason(block, viewer_role)
        entries.append(
            CalendarEntry(
                block.start_time, block.end_time, None, None, CalendarEntryKind.BLOCK, reason
            )
        )
    return sorted(entries, key=lambda entry: entry.start_time)


# --------------------------------------------------------------------------
# SCRUM-35 — search and filter venues against event requirements
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UnmetRequirement:
    """One requirement a venue fails, and why (SCRUM-36)."""

    requirement: RequirementKind
    message: str


def _missing_items(required: list[str], offered: list[str]) -> list[str]:
    """The required items the venue doesn't offer, in the order they were asked for."""
    missing: list[str] = []
    for item in required:
        if item not in offered:
            missing.append(item)
    return missing


def _unmet_requirements(venue: Venue, data: Mapping[str, Any]) -> list[UnmetRequirement]:
    """Every facility, accessibility or layout requirement in ``data`` the venue fails.

    Search leaves out a venue that fails any (SCRUM-35 AC1); the suitability check
    names each one (SCRUM-36 AC2). Items arrive trimmed and lower-cased from the
    schema, as the venue's stored items are.
    """
    unmet: list[UnmetRequirement] = []
    for item in _missing_items(data["required_facilities"], venue.facilities_list()):
        message = f"The venue does not offer {item}."
        unmet.append(UnmetRequirement(RequirementKind.FACILITIES, message))
    for item in _missing_items(data["required_accessibility"], venue.accessibility_list()):
        message = f"The venue does not offer {item}."
        unmet.append(UnmetRequirement(RequirementKind.ACCESSIBILITY, message))
    layout = data["required_layout"]
    if layout is not None and layout not in venue.layouts_list():
        message = f"The venue does not support the {layout} layout."
        unmet.append(UnmetRequirement(RequirementKind.LAYOUT, message))
    return unmet


@dataclass(frozen=True)
class VenueMatch:
    """A venue that meets a search, and what it offers of each requested requirement."""

    venue: Venue
    facilities: list[str]
    accessibility_features: list[str]
    layout: str | None


def _match_requirements(venue: Venue, data: Mapping[str, Any]) -> VenueMatch | None:
    """The venue and what it offers of each requirement; ``None`` if it lacks any."""
    if _unmet_requirements(venue, data):
        return None
    # It offers everything asked for, so what it offers is exactly what was requested.
    return VenueMatch(
        venue, data["required_facilities"], data["required_accessibility"], data["required_layout"]
    )


def _clash_window(venue: Venue, start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """``start``-``end`` widened by the venue's setup + turnaround on each side.

    Each event holds the venue from its start minus setup to its end plus turnaround,
    so another period clashes with this one unless setup + turnaround separates them
    (ADR-0011): it clashes exactly when it overlaps this window.
    """
    setup, turnaround = _buffers(venue)
    gap = setup + turnaround
    return start - gap, end + gap


def _booking_clash(venue: Venue, start: datetime, end: datetime) -> ColumnElement[bool]:
    """SQL condition: a booking on ``venue`` too close to ``start``-``end``."""
    window_start, window_end = _clash_window(venue, start, end)
    return and_(Booking.venue_id == venue.id, _overlaps(Booking, window_start, window_end))


def search_venues(
    payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> list[VenueMatch]:
    """Active venues that meet an event's requirements and are free for its period.

    Two queries. The first selects active venues by capacity and location and leaves
    out any blocked during the period (AC1, AC2). Facilities, accessibility and layout
    are stored as joined strings, so they're checked on the venues it returns. The
    second finds which of those have a non-cancelled booking too close to the period,
    each venue padded by its own setup and turnaround (SCRUM-67, ADR-0011); a live
    tentative hold is one of them and an expired hold is not (SCRUM-75); that
    padding differs per venue, which one portable query can't express. Results are
    ordered by name.

    Raises:
        ValidationError: 400 — missing or invalid filters.
    """
    data = load_or_raise(VenueSearchSchema(), payload)
    start, end = data["start_time"], data["end_time"]

    conflicting_block = select(VenueBlock.id).where(
        VenueBlock.venue_id == Venue.id, _overlaps(VenueBlock, start, end)
    )
    stmt = (
        select(Venue)
        .where(
            Venue.is_active.is_(True),
            Venue.capacity >= data["min_capacity"],
            ~conflicting_block.exists(),
        )
        .order_by(Venue.name)
    )
    if data["location"] is not None:
        stmt = stmt.where(Venue.location.icontains(data["location"], autoescape=True))

    sess = resolve_session(session)
    matches: list[VenueMatch] = []
    for venue in sess.scalars(stmt):
        match = _match_requirements(venue, data)
        if match is not None:
            matches.append(match)
    if not matches:
        return []

    clash_conditions = [_booking_clash(match.venue, start, end) for match in matches]
    clashing_bookings = select(Booking.venue_id).where(
        _booking_is_live(_utc_now()), or_(*clash_conditions)
    )
    busy_venue_ids = set(sess.scalars(clashing_bookings))
    return [match for match in matches if match.venue.id not in busy_venue_ids]


# --------------------------------------------------------------------------
# SCRUM-34 — block a venue for maintenance or internal use
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ConflictingBooking:
    """A booking a new block cuts into (SCRUM-34 AC2).

    ``start_time`` and ``end_time`` are the period the booking holds the venue,
    setup and turnaround included (ADR-0011), as the calendar shows it.
    """

    booking_id: int
    event_id: int | None
    start_time: datetime
    end_time: datetime


def _bookings_cut_by(venue: Venue, block: VenueBlock, session: Session) -> list[ConflictingBooking]:
    """The venue's confirmed and Conflicting bookings that hold it during ``block``."""
    bookings = session.scalars(
        select(Booking)
        .where(
            Booking.status.in_(HOLDING_BOOKING_STATUSES),
            _booking_holds_venue(venue, block.start_time, block.end_time),
        )
        .order_by(Booking.start_time, Booking.id)
    )
    conflicts: list[ConflictingBooking] = []
    for booking in bookings:
        held_start, held_end = _occupied(venue, booking.start_time, booking.end_time)
        conflicts.append(ConflictingBooking(booking.id, booking.event_id, held_start, held_end))
    return conflicts


def block_venue(
    venue_id: int,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    today: date | None = None,
) -> tuple[VenueBlock, list[ConflictingBooking]]:
    """Block a venue for a period, with a category and a note (SCRUM-34, SCRUM-92 AC2).

    The block is saved even if it cuts into confirmed bookings; those are returned
    so Venue Staff can see what they're blocking (AC2, ADR-0016). Once saved, the
    calendar shows the block and search leaves the venue out for that period (AC3).

    Every confirmed booking or Pending request the block cuts into is flagged "Needs
    Alternative Venue" with the block's category, note and period (SCRUM-92 AC1); the
    bookings themselves still hold the venue. The flags, their history entries and any
    Confirmed event's return to Approved are saved with the block, and each event's
    coordinator is told afterwards (AC3, AC5, ADR-0053).

    Args:
        venue_id: The venue to block.
        payload: Decoded JSON body: ``start_time``, ``end_time``, ``category`` and
            ``reason``, the note.
        session: Database session; defaults to ``db.session``.
        today: Reference date for the "not ended before today" rule; defaults to
            today in the business timezone.

    Returns:
        The saved block, and the confirmed bookings it cuts into, in start order.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
        NotFoundError: 404 — no such venue.
    """
    data = load_or_raise(BlockVenueSchema(today=today), payload)
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)

    block = VenueBlock(venue_id=venue.id, **data)
    sess.add(block)
    sess.flush()
    unavailability = {
        "venue_block_id": block.id,
        "category": block.category,
        "reason": block.reason,
        "starts_at": block.start_time,
        "ends_at": block.end_time,
    }
    arrangements = _arrangements_held_during(venue, block.start_time, block.end_time, sess)
    notices = _flag_arrangements(arrangements, venue, unavailability, session)
    sess.commit()
    _tell_coordinators(notices, session)
    return block, _bookings_cut_by(venue, block, sess)


def list_venue_blocks(venue_id: int, *, session: Session | None = None) -> list[VenueBlock]:
    """A venue's blocks, with their ids and reasons, in start order (ADR-0016).

    Venue Staff use it to find the block to remove (SCRUM-34 AC4); the calendar
    shows blocks without ids.

    Raises:
        NotFoundError: 404 — no such venue.
    """
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    return _blocks_in_start_order(venue, sess)


def remove_venue_block(venue_id: int, block_id: int, *, session: Session | None = None) -> None:
    """Delete a venue's block, making the period available again (SCRUM-34 AC4).

    The block must belong to the venue in the request (ADR-0016). The flags it left
    are deleted with it, so those arrangements stand again (SCRUM-92 AC8).

    Raises:
        NotFoundError: 404 — no such venue, or no such block on that venue.
    """
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    block = sess.scalar(
        select(VenueBlock).where(VenueBlock.id == block_id, VenueBlock.venue_id == venue.id)
    )
    if block is None:
        raise NotFoundError("Block not found.")
    left_by_block = AlternativeVenueFlag.venue_block_id == block.id
    sess.execute(delete(AlternativeVenueFlag).where(left_by_block))
    sess.delete(block)
    sess.commit()


# --------------------------------------------------------------------------
# SCRUM-36 — check whether a venue suits an event
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SuitabilityResult:
    """Whether a venue can host an event, and every requirement it fails (SCRUM-36).

    SCRUM-42 will require a justification on a booking request when ``suitable`` is
    false (AC4, ADR-0017).
    """

    reasons: list[UnmetRequirement]

    @property
    def suitable(self) -> bool:
        """A venue is suitable when it fails no requirement (AC3)."""
        return not self.reasons


def check_venue_suitability(
    venue_id: int, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> SuitabilityResult:
    """Whether a venue meets an event's requirements, and each one it fails (SCRUM-36).

    Capacity is checked against the expected attendance (AC1); layout, facilities and
    accessibility exactly as search matches them (AC2). Nothing failed means suitable
    (AC3). Availability isn't checked here: search (SCRUM-35) and conflict detection
    (SCRUM-44) do that. Takes the requirements rather than an event (ADR-0017).

    Raises:
        ValidationError: 400 — missing or invalid requirements.
        NotFoundError: 404 — no such venue.
    """
    data = load_or_raise(VenueSuitabilitySchema(), payload)
    venue = get_venue(venue_id, session=session)

    reasons: list[UnmetRequirement] = []
    expected_attendance = data["expected_attendance"]
    if venue.capacity < expected_attendance:
        message = (
            f"Expected attendance of {expected_attendance} exceeds the venue's capacity"
            f" of {venue.capacity}."
        )
        reasons.append(UnmetRequirement(RequirementKind.CAPACITY, message))
    reasons.extend(_unmet_requirements(venue, data))
    return SuitabilityResult(reasons)


# --------------------------------------------------------------------------
# SCRUM-42 — raise a venue booking request for an approved event
# --------------------------------------------------------------------------

JUSTIFICATION_REQUIRED_MESSAGE = "A justification is required because the venue is not suitable."

OUTSIDE_OPENING_HOURS_MESSAGE = "The request falls outside the venue's operating hours."

#: Where a day's opening hours start and end when a period runs over the day boundary.
MIDNIGHT = time(0)


#: An arrangement id that isn't one of the event's (SCRUM-93), or that a replacement
#: names (SCRUM-92 AC6).
ARRANGEMENT_NOT_FOUND_MESSAGE = "Venue arrangement not found."
NOT_FLAGGED_MESSAGE = "This venue arrangement does not need an alternative venue."

PENDING_INDEX_NAME = "uq_venue_booking_requests_pending"
DUPLICATE_REQUEST_MESSAGE = "A pending request for this event, venue and period already exists."


def _is_pending_duplicate(error: IntegrityError) -> bool:
    """Whether the database refused the row because of the pending index (AC6)."""
    message = str(error.orig)
    # Postgres names the index; SQLite (the unit suite) names only the columns.
    return PENDING_INDEX_NAME in message or "UNIQUE constraint failed" in message


def _save_request(request: VenueBookingRequest, session: Session | None) -> None:
    """Save the request and its history entry in one commit; the one place it is saved.

    The database refuses a duplicate Pending request when the row is flushed, so the
    flush and the commit both sit inside the ``try``.

    Raises:
        ConflictError: 409 — a Pending request for this event, venue and period exists.
    """
    from app.modules.events import services as event_services  # circular at import time

    active_session = resolve_session(session)
    try:
        active_session.add(request)
        active_session.flush()
        event_services.record_venue_booking_requested(
            request.event_id,
            actor_id=request.requested_by,
            details={
                "venue_booking_request_id": request.id,
                "venue_id": request.venue_id,
                "starts_at": request.starts_at.isoformat(),
                "ends_at": request.ends_at.isoformat(),
            },
            session=session,
        )
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        if _is_pending_duplicate(exc):
            raise ConflictError(DUPLICATE_REQUEST_MESSAGE) from exc
        raise


def _venue_for_request(venue_id: int, session: Session | None) -> Venue:
    """The venue a request names; an unknown one is reported on ``venue_id`` (AC1)."""
    try:
        return get_venue(venue_id, session=session)
    except NotFoundError:
        raise ValidationError(
            "Invalid request.", details={"venue_id": ["Venue not found."]}
        ) from None


def _weekly_hours(venue: Venue) -> list[Period]:
    """The venue's stored opening periods, as the week timeline's own type."""
    return [
        Period(period.open_day, period.open_time, period.close_day, period.close_time)
        for period in venue.opening_periods
    ]


def _part_of_day_open(period: VenueOpeningPeriod, day: Weekday) -> tuple[time, time] | None:
    """The stretch of ``day`` that ``period`` leaves the venue open, or ``None``.

    An overnight period is clipped to the day asked about: Saturday 20:00 to Sunday
    04:00 is ``20:00``-``00:00`` on the Saturday and ``00:00``-``04:00`` on the Sunday.
    A period closing at exactly 00:00 ends as ``day`` begins, so it opens none of it.
    """
    if period.open_day == day:
        closes = period.close_time if period.close_day == day else MIDNIGHT
        return period.open_time, closes
    if period.close_day == day and period.close_time != MIDNIGHT:
        return MIDNIGHT, period.close_time
    return None


def _hours_on(venue: Venue, day: Weekday) -> str:
    """The parts of ``day`` the venue is open, e.g. ``"09:00-12:00, 13:00-18:00"``.

    Earliest first, counting a period that ran over from the day before. Empty when
    nothing opens any part of the day, which means the venue is closed.
    """
    in_week_order = sorted(venue.opening_periods, key=lambda p: (p.open_day, p.open_time))
    stretches: list[str] = []
    for period in in_week_order:
        open_part = _part_of_day_open(period, day)
        if open_part is not None:
            opens, closes = open_part
            stretches.append(f"{opens:%H:%M}-{closes:%H:%M}")
    return ", ".join(stretches)


def _require_within_opening_hours(venue: Venue, starts_at: datetime, ends_at: datetime) -> None:
    """Refuse a request that doesn't fall inside the venue's operating hours (AC2).

    Hours are weekly and in business time, so the stored UTC instants are converted
    back before they are placed on the week. The message names the hours on the day
    the request starts: hours are agreed outside the system, so the coordinator has
    nothing to change in the request itself.

    Raises:
        ValidationError: 400 — the period falls outside the venue's hours.
    """
    start = to_business_time(starts_at)
    if covers_period(_weekly_hours(venue), start, to_business_time(ends_at)):
        return

    day = Weekday(start.weekday())
    hours = _hours_on(venue, day)
    opening = f"open {hours}" if hours else "closed"
    raise ValidationError(
        "Invalid request.",
        details={
            "starts_at": [
                f"{OUTSIDE_OPENING_HOURS_MESSAGE}"
                f" The venue is {opening} on {day.label.capitalize()}."
            ]
        },
    )


def _venue_is_suitable(
    venue_id: int, occupancy: int, layout: str | None, session: Session | None
) -> bool:
    """Whether the venue suits this request's own occupancy and layout (AC7)."""
    requirements = {"expected_attendance": occupancy, "required_layout": layout}
    return check_venue_suitability(venue_id, requirements, session=session).suitable


def show_booking_request(
    request: VenueBookingRequest, event: EventForBooking
) -> BookingRequestAsShown:
    """The request with its event's timing and accessibility needs beside it (AC4)."""
    return BookingRequestAsShown(
        request=request,
        proposed_date=event.proposed_date,
        end_date=event.end_date,
        start_time=event.start_time,
        end_time=event.end_time,
        accessibility_needs=event.accessibility_needs,
    )


def _notify_about_booking(
    recipient_ids: list[int],
    event: EventForBooking,
    kind: NotificationKind,
    *,
    detail: str | None = None,
    session: Session | None = None,
) -> None:
    """Notify about a booking request after its own commit, in a second (ADR-0015).

    If the notifications can't be saved, only they are lost and a warning is logged:
    the request or decision is already saved, and failing the reply would invite the
    caller to send it again. Shared by the two notices the venue module sends; moving
    it into ``notifications.services`` alongside the events module's copy stays a
    follow-up (ADR-0035, ADR-0042).
    """
    active_session = resolve_session(session)
    summary = EventSummary(id=event.id, reference=event.reference, name=event.name)
    try:
        notify_users(recipient_ids, summary, kind, session=session, detail=detail)
    except SQLAlchemyError:
        active_session.rollback()
        logger.warning("venue_booking_notification_failed reference=%s", event.reference)


def _notify_venue_staff(event: EventForBooking, session: Session | None) -> None:
    """Tell every Venue Staff user the request needs a decision (AC9, ADR-0035)."""
    _notify_about_booking(
        list_user_ids_with_role(Role.VENUE_STAFF, session=session),
        event,
        NotificationKind.VENUE_BOOKING_REQUESTED,
        session=session,
    )


def _check_replaceable(event_id: int, arrangement_id: int, session: Session | None) -> None:
    """Refuse a replacement unless it names a flagged arrangement of the event (AC6).

    An arrangement of another event is reported as missing, as ADR-0035 §6 does for
    the arrangement routes, so it is not discoverable.

    Raises:
        ValidationError: 400 — on ``replaces_request_id``: no such arrangement on the
            event, or it doesn't need an alternative venue.
    """
    replaced = resolve_session(session).get(VenueBookingRequest, arrangement_id)
    if replaced is None or replaced.event_id != event_id:
        raise ValidationError(
            "Invalid request.", details={"replaces_request_id": [ARRANGEMENT_NOT_FOUND_MESSAGE]}
        )
    if not replaced.needs_alternative_venue:
        raise ValidationError(
            "Invalid request.", details={"replaces_request_id": [NOT_FLAGGED_MESSAGE]}
        )


def _event_to_book_for(
    reference: str, data: Mapping[str, Any], requested_by: int, session: Session | None
) -> EventForBooking:
    """The event a request is raised for, checked for the kind of request it is.

    An ordinary request needs an approved event (SCRUM-42). A replacement for a
    flagged arrangement may also be raised in Safety Review, where a flag leaves an
    event that was not yet Confirmed (SCRUM-92 AC3, AC6, ADR-0053).

    Raises:
        NotFoundError: 404 — no such event, or ``requested_by`` doesn't coordinate it.
        ConflictError: 409 — the event isn't at a status that allows the request.
        ValidationError: 400 — a replacement for an arrangement that isn't flagged.
    """
    from app.modules.events import services as event_services  # circular at import time

    replaces = data.get("replaces_request_id")
    if replaces is None:
        return event_services.get_approved_event_for_coordinator(
            reference, requested_by, session=session
        )
    event = event_services.get_event_for_replacement_booking(
        reference, requested_by, session=session
    )
    _check_replaceable(event.id, replaces, session)
    return event


def raise_booking_request(
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    requested_by: int,
    session: Session | None = None,
) -> BookingRequestAsShown:
    """Raise a Pending booking request for an approved event (SCRUM-42 AC1, AC3, AC5).

    Returns the request with its event's details beside it (AC4), taken from the event
    read before saving, so a saved request is never lost to a failed second read.

    Occupancy defaults to the event's expected attendance; the event has no layout, so
    the layout defaults to none. A venue unsuitable for the request's own occupancy
    and layout needs a justification (AC7). The request and the event's history entry
    are saved in one commit; Venue Staff are then notified in a second (AC9).

    The venue must be open for the whole period: hours are agreed outside the system,
    so a request outside them is refused rather than queued for Venue Staff (AC2).

    A request with ``replaces_request_id`` replaces one of the event's arrangements that
    needs an alternative venue (SCRUM-92 AC6); approving it releases that one (AC7).

    Raises:
        ValidationError: 400 — invalid payload, unknown venue, a period outside the
            venue's operating hours, no justification, or a replacement for an
            arrangement that isn't the event's or isn't flagged.
        NotFoundError: 404 — no such event, or ``requested_by`` doesn't coordinate it.
        ConflictError: 409 — the event isn't approved (or, for a replacement, in
            Safety Review).
    """
    data = load_or_raise(RaiseBookingRequestSchema(), payload)
    event = _event_to_book_for(reference, data, requested_by, session)
    data.setdefault("expected_occupancy", event.expected_attendance)
    data.setdefault("required_layout", None)

    venue = _venue_for_request(data["venue_id"], session)
    _require_within_opening_hours(venue, data["starts_at"], data["ends_at"])

    suitable = _venue_is_suitable(
        venue.id, data["expected_occupancy"], data["required_layout"], session
    )
    if not suitable and "justification" not in data:
        raise ValidationError(
            "Invalid request.", details={"justification": [JUSTIFICATION_REQUIRED_MESSAGE]}
        )

    request = VenueBookingRequest(event_id=event.id, requested_by=requested_by, **data)
    _save_request(request, session)
    _notify_venue_staff(event, session)
    return show_booking_request(request, event)


def list_booking_requests_for_event(
    reference: str, *, coordinator_id: int, session: Session | None = None
) -> list[BookingRequestAsShown]:
    """The event's booking requests, earliest period first, with the event's details.

    The event may be at any status: an approved event moves on once a venue is booked.

    Raises:
        NotFoundError: 404 — no such event, or ``coordinator_id`` doesn't coordinate it.
    """
    from app.modules.events import services as event_services  # circular at import time

    event = event_services.get_event_for_coordinator(reference, coordinator_id, session=session)
    query = (
        select(VenueBookingRequest)
        .where(VenueBookingRequest.event_id == event.id)
        .order_by(VenueBookingRequest.starts_at, VenueBookingRequest.id)
    )
    requests = resolve_session(session).scalars(query).all()
    return [show_booking_request(request, event) for request in requests]


# --------------------------------------------------------------------------
# SCRUM-93 — several venue arrangements for one event
# --------------------------------------------------------------------------


WITHDRAW_NOT_ALLOWED_MESSAGE = (
    "Only a pending, conflicting, rejected or expired arrangement can be withdrawn;"
    " this one is {status}."
)
#: A rejected arrangement stays active until its coordinator withdraws it (SCRUM-43), so
#: it can be withdrawn like a pending one, and so can a Conflicting one (SCRUM-44) and
#: one whose hold expired (SCRUM-94). An approved one has made a booking, which
#: withdrawing would leave behind, so it cannot.
WITHDRAWABLE_REQUEST_STATUSES = frozenset(
    {
        BookingRequestStatus.PENDING,
        BookingRequestStatus.CONFLICTING,
        BookingRequestStatus.REJECTED,
        BookingRequestStatus.EXPIRED,
    }
)
CHANGE_NOT_PENDING_MESSAGE = "Only a pending arrangement can be changed; this one is {status}."


def list_active_arrangements(
    event_id: int, *, session: Session | None = None
) -> list[VenueBookingRequest]:
    """The event's arrangements that still count towards its venues.

    Retired ones are left out. The consumers are SCRUM-75 (is the event multi-venue?),
    SCRUM-49 (confirmation) and SCRUM-97 (the Safety Review gate). Earliest period
    first, as the event's own list of requests is.
    """
    query = (
        select(VenueBookingRequest)
        .where(
            VenueBookingRequest.event_id == event_id,
            VenueBookingRequest.status.not_in(RETIRED_REQUEST_STATUSES),
        )
        .order_by(VenueBookingRequest.starts_at, VenueBookingRequest.id)
    )
    return list(resolve_session(session).scalars(query).all())


def count_active_arrangements(event_id: int, *, session: Session | None = None) -> int:
    """How many venues the event still has arranged (SCRUM-75's multi-venue test)."""
    return len(list_active_arrangements(event_id, session=session))


def list_unapproved_arrangements(
    event_id: int, *, session: Session | None = None
) -> list[VenueBookingRequest]:
    """The event's active arrangements Venue Staff haven't approved (SCRUM-97 AC1).

    A Pending or Rejected arrangement is still active, so it is listed until the
    coordinator withdraws it; any one of them keeps the event out of Safety Review.
    """
    unapproved = []
    for arrangement in list_active_arrangements(event_id, session=session):
        if arrangement.status is not BookingRequestStatus.APPROVED:
            unapproved.append(arrangement)
    return unapproved


def list_flagged_arrangements(
    event_id: int, *, session: Session | None = None
) -> list[VenueBookingRequest]:
    """The event's active arrangements that need an alternative venue (SCRUM-92).

    For SCRUM-49 AC6 and SCRUM-97, which hold the event back while any is listed.
    Earliest period first.
    """
    flagged = []
    for arrangement in list_active_arrangements(event_id, session=session):
        if arrangement.needs_alternative_venue:
            flagged.append(arrangement)
    return flagged


@dataclass(frozen=True)
class ArrangedVenue:
    """A venue an event has booked, with what the Safety Officer reviews (SCRUM-97 AC6).

    The venue's name, capacity, supported room layouts, facilities and accessibility
    features, and the period it is booked for. No ids: they are not the reader's to use.
    """

    name: str
    capacity: int
    layouts: list[str]
    facilities: list[str]
    accessibility_features: list[str]
    starts_at: datetime
    ends_at: datetime


def list_arranged_venues(event_id: int, *, session: Session | None = None) -> list[ArrangedVenue]:
    """The venues the event still has arranged, earliest period first (SCRUM-97 AC6).

    Withdrawn arrangements are left out, as :func:`list_active_arrangements` does.
    """
    arranged = []
    for arrangement in list_active_arrangements(event_id, session=session):
        venue = get_venue(arrangement.venue_id, session=session)
        arranged.append(
            ArrangedVenue(
                name=venue.name,
                capacity=venue.capacity,
                layouts=venue.layouts_list(),
                facilities=venue.facilities_list(),
                accessibility_features=venue.accessibility_list(),
                starts_at=arrangement.starts_at,
                ends_at=arrangement.ends_at,
            )
        )
    return arranged


def _arrangement_of_event(
    event_id: int, arrangement_id: int, session: Session
) -> VenueBookingRequest:
    """One of the event's own arrangements.

    An id that belongs to another event is reported as missing, so arrangements of
    events the caller cannot see are not discoverable (ADR-0035 §6).

    Raises:
        NotFoundError: 404 — the event has no arrangement with that id.
    """
    arrangement = session.get(VenueBookingRequest, arrangement_id)
    if arrangement is None or arrangement.event_id != event_id:
        raise NotFoundError(ARRANGEMENT_NOT_FOUND_MESSAGE)
    return arrangement


def _withdraw_and_record(
    arrangement: VenueBookingRequest, coordinator_id: int, session: Session | None
) -> None:
    """Withdraw one arrangement and write its history entry, without committing.

    Raises:
        ConflictError: 409 — the arrangement is not pending, conflicting or rejected.
    """
    from app.modules.events import services as event_services  # circular at import time

    if arrangement.status not in WITHDRAWABLE_REQUEST_STATUSES:
        raise ConflictError(WITHDRAW_NOT_ALLOWED_MESSAGE.format(status=arrangement.status.value))
    arrangement.status = BookingRequestStatus.WITHDRAWN
    event_services.record_venue_arrangement_withdrawn(
        arrangement.event_id,
        actor_id=coordinator_id,
        details={
            "venue_booking_request_id": arrangement.id,
            "venue_id": arrangement.venue_id,
        },
        session=session,
    )


def withdraw_arrangement(
    reference: str,
    arrangement_id: int,
    *,
    coordinator_id: int,
    session: Session | None = None,
) -> BookingRequestAsShown:
    """Retract one of an event's arrangements while it is pending or rejected (AC6).

    The event's other arrangements are untouched. The withdrawal and its history entry
    are saved in one commit.

    Raises:
        NotFoundError: 404 — no such event among the coordinator's own, or no such
            arrangement on it.
        ConflictError: 409 — the arrangement is not pending, conflicting or rejected.
    """
    from app.modules.events import services as event_services  # circular at import time

    sess = resolve_session(session)
    event = event_services.get_event_for_coordinator(reference, coordinator_id, session=session)
    arrangement = _arrangement_of_event(event.id, arrangement_id, sess)
    _withdraw_and_record(arrangement, coordinator_id, session)
    sess.commit()
    return show_booking_request(arrangement, event)


def cancel_all_arrangements(
    reference: str, *, coordinator_id: int, session: Session | None = None
) -> list[BookingRequestAsShown]:
    """Retire every arrangement the event still has (AC6's explicit "cancel all").

    AC6 keeps one arrangement's fate from touching the others unless the coordinator
    asks for all of them, which is this call rather than a loop the client writes.
    Every pending or rejected arrangement is withdrawn. An approved one cannot be (its
    booking would be left behind), so the call is refused while the event has one;
    cancelling an approved booking is not yet in any story. An event with none is not
    an error.

    Returns:
        The retired arrangements, earliest period first, or an empty list.

    Raises:
        NotFoundError: 404 — no such event among the coordinator's own.
        ConflictError: 409 — an arrangement is approved; nothing is withdrawn.
    """
    from app.modules.events import services as event_services  # circular at import time

    sess = resolve_session(session)
    event = event_services.get_event_for_coordinator(reference, coordinator_id, session=session)
    arrangements = list_active_arrangements(event.id, session=session)
    for arrangement in arrangements:
        _withdraw_and_record(arrangement, coordinator_id, session)
    sess.commit()
    return [show_booking_request(arrangement, event) for arrangement in arrangements]


def _changes_to_apply(
    arrangement: VenueBookingRequest, data: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Which of the fields in ``data`` actually alter the arrangement, and from what.

    ``data`` has been through ``ChangeArrangementSchema``, which rejects unknown fields,
    so every key is an attribute of the arrangement. Each is a string, an integer or
    ``None``, so the previous and new values go into the history entry's details as they
    are.
    """
    changes: dict[str, dict[str, Any]] = {}
    for field, new_value in data.items():
        previous = getattr(arrangement, field)
        if previous != new_value:
            changes[field] = {"previous": previous, "new": new_value}
    return changes


def change_arrangement(
    reference: str,
    arrangement_id: int,
    payload: Mapping[str, Any] | None,
    *,
    coordinator_id: int,
    session: Session | None = None,
) -> BookingRequestAsShown:
    """Change a pending arrangement's purpose, occupancy, layout or justification (AC6).

    Only the fields sent change (the layout is cleared by sending it as ``null``), and
    only while Venue Staff have yet to decide: changing a decided arrangement would
    quietly void their decision. Suitability is re-checked against the merged values, so
    a change that outgrows the venue needs a justification just as raising one does.
    That check runs before anything is written, so a refused change leaves the
    arrangement exactly as it was. A change that alters nothing writes no history entry.

    Raises:
        ValidationError: 400 — invalid values, or no justification for a venue the
            changed arrangement no longer suits.
        NotFoundError: 404 — no such event among the coordinator's own, or no such
            arrangement on it.
        ConflictError: 409 — the arrangement is no longer pending.
    """
    from app.modules.events import services as event_services  # circular at import time

    schema = ChangeArrangementSchema()
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    event = event_services.get_event_for_coordinator(reference, coordinator_id, session=session)
    arrangement = _arrangement_of_event(event.id, arrangement_id, sess)
    if arrangement.status is not BookingRequestStatus.PENDING:
        raise ConflictError(CHANGE_NOT_PENDING_MESSAGE.format(status=arrangement.status.value))

    occupancy = data.get("expected_occupancy", arrangement.expected_occupancy)
    layout = data.get("required_layout", arrangement.required_layout)
    justification = data.get("justification", arrangement.justification)
    suitable = _venue_is_suitable(arrangement.venue_id, occupancy, layout, session)
    if not suitable and not justification:
        raise ValidationError(
            "Invalid request.", details={"justification": [JUSTIFICATION_REQUIRED_MESSAGE]}
        )

    changes = _changes_to_apply(arrangement, data)
    if not changes:
        return show_booking_request(arrangement, event)

    for field, change in changes.items():
        setattr(arrangement, field, change["new"])
    event_services.record_venue_arrangement_changed(
        event.id,
        actor_id=coordinator_id,
        details={
            "venue_booking_request_id": arrangement.id,
            "venue_id": arrangement.venue_id,
            "changes": changes,
        },
        session=session,
    )
    sess.commit()
    return show_booking_request(arrangement, event)


# --------------------------------------------------------------------------
# SCRUM-43 — Venue Staff approve or reject a booking request
# --------------------------------------------------------------------------


BOOKING_REQUEST_NOT_FOUND_MESSAGE = "Booking request not found."
DECISION_NOT_PENDING_MESSAGE = "Only a pending request can be decided; this one is {status}."
REJECTION_REASON_REQUIRED_MESSAGE = "A reason is required to reject a booking request."
APPROVAL_OVERLAP_MESSAGE = (
    "Cannot approve: booking #{booking_id} already holds this venue during the requested period."
)
APPROVAL_PADDING_MESSAGE = (
    "Cannot approve: the requested period is too close to booking #{booking_id}; this venue "
    "needs {setup} minutes of setup and {turnaround} minutes of turnaround around each event."
)

#: Where each outcome leaves the request (AC3), and which notice the coordinator gets
#: (AC6). SCRUM-75 adds holding to both.
_STATUS_BY_DECISION = {
    BookingDecision.APPROVED: BookingRequestStatus.APPROVED,
    BookingDecision.REJECTED: BookingRequestStatus.REJECTED,
}
_NOTIFICATION_BY_DECISION = {
    BookingDecision.APPROVED: NotificationKind.VENUE_BOOKING_APPROVED,
    BookingDecision.REJECTED: NotificationKind.VENUE_BOOKING_REJECTED,
}


def _events_of(
    requests: list[VenueBookingRequest], session: Session | None
) -> dict[int, EventForBooking]:
    """The events ``requests`` are for, by id, read in a single query."""
    from app.modules.events import services as event_services  # circular at import time

    event_ids = {request.event_id for request in requests}
    return event_services.get_events_for_booking(event_ids, session=session)


def list_pending_booking_requests(*, session: Session | None = None) -> list[BookingRequestAsShown]:
    """Every request waiting for a decision, the earliest event first (AC1, AC2).

    That includes the Conflicting ones (SCRUM-44), shown with their status.

    Any Venue Staff member sees the whole queue: staff are not assigned to venues
    (ADR-0035 decision 1). The order is the event's date, then its start time, then the
    request's id, so a queue read twice is in the same order. The events are read
    through the events service and the ordering is done here, because the date lives in
    the events module and this module may not join across it.
    """
    requests = list(
        resolve_session(session).scalars(
            select(VenueBookingRequest).where(
                VenueBookingRequest.status.in_(DECIDABLE_REQUEST_STATUSES)
            )
        )
    )
    events = _events_of(requests, session)
    waiting = [(events[request.event_id], request) for request in requests]
    waiting.sort(key=lambda pair: (pair[0].proposed_date, pair[0].start_time, pair[1].id))
    return [show_booking_request(request, event) for event, request in waiting]


def _event_of(request: VenueBookingRequest, session: Session | None) -> EventForBooking:
    """The event ``request`` is for, with the details a booking needs.

    The request's ``event_id`` is a foreign key, so the event is always there.
    """
    from app.modules.events import services as event_services  # circular at import time

    return event_services.get_events_for_booking([request.event_id], session=session)[
        request.event_id
    ]


def _locked_request(request_id: int, session: Session | None) -> VenueBookingRequest:
    """The request ``request_id`` names, read under a row lock.

    The row is locked while it is read, as the equipment type is before a reservation is
    counted (ADR-0037): two Venue Staff deciding the same request at the same moment
    would otherwise both see it Pending and both book the venue. ``populate_existing``
    is needed with it, because a copy the session loaded earlier may predate the other
    decision's commit, and the locked row has to overwrite it rather than be skipped as
    already known.

    Raises:
        NotFoundError: 404 — no such request.
    """
    locked = (
        select(VenueBookingRequest)
        .where(VenueBookingRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    request = resolve_session(session).scalar(locked)
    if request is None:
        raise NotFoundError(BOOKING_REQUEST_NOT_FOUND_MESSAGE)
    return request


def _request_to_decide(request_id: int, session: Session | None) -> VenueBookingRequest:
    """The request ``request_id`` names, if it is still waiting for a decision.

    Raises:
        NotFoundError: 404 — no such request.
        ConflictError: 409 — it was decided or withdrawn already; the message names
            the status it is in. A Conflicting request can still be decided (ADR-0045),
            and so can one On Hold (SCRUM-75).
    """
    request = _locked_request(request_id, session)
    if request.status not in DECIDABLE_REQUEST_STATUSES:
        raise ConflictError(DECISION_NOT_PENDING_MESSAGE.format(status=request.status.value))
    return request


def _lock_venue(venue_id: int, session: Session | None) -> Venue:
    """The venue, read under a row lock so approvals for it take turns (ADR-0045).

    Without the lock, two approvals at one venue could each find it free and each make
    a booking. The lock is held until the approval commits, so the second one waits and
    then sees the first's booking. ``populate_existing`` makes the read return the
    venue's setup and turnaround as they are now, not as the session last saw them.
    """
    locked = (
        select(Venue)
        .where(Venue.id == venue_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return resolve_session(session).scalars(locked).one()


def _clashing_booking(
    venue: Venue, request: VenueBookingRequest, session: Session | None
) -> Booking | None:
    """The earliest booking or live hold that ``request`` clashes with (ADR-0045)."""
    earliest_clash = (
        select(Booking)
        .where(
            _booking_is_live(_utc_now()),
            _booking_clash(venue, request.starts_at, request.ends_at),
        )
        .order_by(Booking.start_time, Booking.id)
    )
    return resolve_session(session).scalars(earliest_clash).first()


def _clash_error(venue: Venue, request: VenueBookingRequest, booking: Booking) -> ConflictError:
    """The 409 for approving ``request`` while ``booking`` holds the venue (SCRUM-44).

    It says whether the periods themselves overlap or only the setup and turnaround
    around them do, and gives the period the booking holds the venue for.
    """
    booked = (booking.start_time, booking.end_time)
    asked_for = (request.starts_at, request.ends_at)
    periods_overlap = _shared_period(booked, asked_for) is not None
    if periods_overlap:
        message = APPROVAL_OVERLAP_MESSAGE.format(booking_id=booking.id)
    else:
        message = APPROVAL_PADDING_MESSAGE.format(
            booking_id=booking.id, setup=venue.setup_minutes, turnaround=venue.turnaround_minutes
        )
    held_from, held_until = _occupied(venue, booking.start_time, booking.end_time)
    return ConflictError(
        message,
        details={
            "booking_id": booking.id,
            "in_buffer": not periods_overlap,
            "occupied_from": to_business_time(held_from).isoformat(),
            "occupied_until": to_business_time(held_until).isoformat(),
        },
    )


def _refuse_clash(request: VenueBookingRequest, session: Session | None) -> None:
    """Refuse to approve or hold ``request`` if it clashes with a booking (SCRUM-44).

    Raises:
        ConflictError: 409 — the period, with the venue's setup and turnaround, runs
            into a confirmed booking or a live hold at the same venue; the body names
            the booking.
    """
    venue = _lock_venue(request.venue_id, session)
    booking = _clashing_booking(venue, request, session)
    if booking is not None:
        raise _clash_error(venue, request, booking)


def _mark_clashing_requests_conflicting(
    approved: VenueBookingRequest, session: Session | None
) -> None:
    """Mark each other Pending request that clashes with ``approved`` as Conflicting.

    Clashing is the rule for bookings: setup and turnaround must fit between the two
    periods (ADR-0011). Whatever event the other request is for, only its venue counts
    (SCRUM-44 AC5, AC8). Nothing is saved here; the approval's commit saves the marks.
    """
    venue = get_venue(approved.venue_id, session=session)
    window_start, window_end = _clash_window(venue, approved.starts_at, approved.ends_at)
    clashing_requests = select(VenueBookingRequest).where(
        VenueBookingRequest.venue_id == venue.id,
        VenueBookingRequest.status == BookingRequestStatus.PENDING,
        VenueBookingRequest.id != approved.id,
        VenueBookingRequest.starts_at < window_end,
        VenueBookingRequest.ends_at > window_start,
    )
    for other in resolve_session(session).scalars(clashing_requests).all():
        other.status = BookingRequestStatus.CONFLICTING


def _booking_for(request: VenueBookingRequest) -> Booking:
    """The confirmed booking an approval makes, for the period asked for (AC3)."""
    return Booking(
        venue_id=request.venue_id,
        event_id=request.event_id,
        start_time=request.starts_at,
        end_time=request.ends_at,
        status=BookingStatus.CONFIRMED,
    )


HOLD_EXPIRED_MESSAGE = "This hold has expired."


def _hold_has_expired(hold: Booking) -> bool:
    """Whether the hold's expiry has passed, as :func:`_booking_is_live` has it."""
    return hold.hold_expires_at is not None and hold.hold_expires_at <= _utc_now()


def _confirm_hold(request: VenueBookingRequest) -> Booking:
    """Turn the request's hold into the confirmed booking (SCRUM-75 AC7).

    The hold already keeps the venue free of other bookings, so there is no clash to
    check: a request On Hold does not clash with its own hold (SCRUM-44).

    Raises:
        ConflictError: 409 — the hold expired before the final approval.
    """
    hold = request.booking
    if _hold_has_expired(hold):
        raise ConflictError(HOLD_EXPIRED_MESSAGE)
    hold.status = BookingStatus.CONFIRMED
    hold.hold_expires_at = None
    return hold


def _booking_to_approve(request: VenueBookingRequest, session: Session | None) -> Booking:
    """The confirmed booking approving ``request`` makes (SCRUM-43 AC3, SCRUM-75 AC7).

    A request On Hold confirms its hold. Any other is refused if it clashes with a
    booking or a live hold (SCRUM-44), and gets a new booking.
    """
    if request.status is BookingRequestStatus.ON_HOLD:
        return _confirm_hold(request)
    _refuse_clash(request, session)
    return _booking_for(request)


def _booking_made_by(arrangement: VenueBookingRequest, session: Session | None) -> Booking | None:
    """The booking approving ``arrangement`` made, if it still holds the venue (AC3).

    The booking has no link to its request, so it is the event's booking at the
    request's venue for exactly the request's period.
    """
    stmt = select(Booking).where(
        Booking.venue_id == arrangement.venue_id,
        Booking.event_id == arrangement.event_id,
        Booking.start_time == arrangement.starts_at,
        Booking.end_time == arrangement.ends_at,
        Booking.status.in_(HOLDING_BOOKING_STATUSES),
    )
    return resolve_session(session).scalars(stmt).first()


def _release_replaced(
    replacement: VenueBookingRequest, decided_by: int, session: Session | None
) -> None:
    """Release what an approved replacement replaces, without committing (SCRUM-92).

    The replaced arrangement is Released and its booking cancelled, unless it has
    already stopped holding its venue, say to an earlier replacement (AC7). Whatever
    it was, the event's venues changed, so a safety approval it had no longer counts
    (AC10). An approval of an ordinary request does nothing here.
    """
    from app.modules.events import services as event_services  # circular at import time

    if replacement.replaces_request_id is None:
        return
    replaced = resolve_session(session).get(VenueBookingRequest, replacement.replaces_request_id)
    if replaced.status in FLAGGABLE_REQUEST_STATUSES:
        booking = _booking_made_by(replaced, session)
        if booking is not None:
            booking.status = BookingStatus.CANCELLED
        replaced.status = BookingRequestStatus.RELEASED
    event_services.withdraw_safety_approval(
        replacement.event_id,
        actor_id=decided_by,
        details={
            "venue_booking_request_id": replacement.id,
            "replaces_request_id": replaced.id,
        },
        session=session,
    )


def _save_decision(
    request: VenueBookingRequest,
    decision: BookingDecision,
    booking: Booking | None,
    *,
    decided_by: int,
    session: Session | None,
) -> None:
    """Save the decision, any booking it makes and the history entry in one commit.

    The event's history entry rides in the same transaction as the decision it
    records, as raising a request does (ADR-0035 decision 8).
    """
    from app.modules.events import services as event_services  # circular at import time

    active_session = resolve_session(session)
    request.status = _STATUS_BY_DECISION[decision]
    if booking is not None:
        active_session.add(booking)
    active_session.flush()
    event_services.record_venue_booking_decided(
        request.event_id,
        outcome=decision.value,
        actor_id=decided_by,
        details={
            "venue_booking_request_id": request.id,
            "venue_id": request.venue_id,
            "booking_id": booking.id if booking is not None else None,
            "reason": request.decision_reason,
            "replaces_request_id": request.replaces_request_id,
        },
        session=session,
    )
    active_session.commit()


def decide_booking_request(
    request_id: int,
    payload: Mapping[str, Any] | None,
    *,
    decided_by: int,
    session: Session | None = None,
) -> BookingRequestAsShown:
    """Approve or reject a Pending booking request (SCRUM-43 AC3, AC6, AC7, AC8).

    Approving makes a confirmed booking for the period asked for, which the venue's
    calendar then shows as unavailable, padded by its setup and turnaround time
    (ADR-0011). Rejecting books nothing and needs a reason. Either way the request
    keeps the reason, the event's history gets an entry in the same commit, and the
    coordinator who raised the request is told in a second commit (ADR-0015). The
    event's other requests are untouched (AC8): each is decided on its own.

    An approval is refused when its period, with the venue's setup and turnaround,
    clashes with a confirmed booking at the venue (SCRUM-44, ADR-0045). Once it passes,
    every other Pending request at the venue that clashes with it is marked Conflicting
    in the same commit. A request On Hold (SCRUM-75) is decided too: approving it turns
    its hold into the confirmed booking, and rejecting it releases the venue.

    Approving a replacement releases the arrangement it replaces and withdraws the
    event's safety approval, in the same commit (SCRUM-92 AC7, AC10, ADR-0053).

    Args:
        request_id: The request's own id, as the queue lists it.
        payload: Decoded JSON body: ``outcome`` and an optional ``reason``.
        decided_by: The deciding Venue Staff user's id, taken from their token.
        session: Database session; defaults to ``db.session``.

    Returns:
        The decided request, with its event's details beside it.

    Raises:
        NotFoundError: 404 — no such request.
        ConflictError: 409 — the request was decided already, approving it clashes with
            a booking or live hold (the body names it), or its hold has expired.
        ValidationError: 400 — payload invalid, or a rejection without a reason.
    """
    request = _request_to_decide(request_id, session)
    data = load_or_raise(DecideBookingRequestSchema(), payload)
    decision = data["outcome"]
    reason = data["reason"]
    if decision is BookingDecision.REJECTED and reason is None:
        raise ValidationError(
            "Invalid request.", details={"reason": [REJECTION_REASON_REQUIRED_MESSAGE]}
        )

    event = _event_of(request, session)
    booking = None
    if decision is BookingDecision.APPROVED:
        booking = _booking_to_approve(request, session)
        _mark_clashing_requests_conflicting(request, session)
        _release_replaced(request, decided_by, session)
    elif request.status is BookingRequestStatus.ON_HOLD:
        # Rejecting a hold releases the venue at once (SCRUM-75 AC7).
        request.booking.status = BookingStatus.CANCELLED
    request.decision_reason = reason
    _save_decision(request, decision, booking, decided_by=decided_by, session=session)
    _notify_about_booking(
        [request.requested_by],
        event,
        _NOTIFICATION_BY_DECISION[decision],
        detail=reason,
        session=session,
    )
    return show_booking_request(request, event)


# --------------------------------------------------------------------------
# SCRUM-84 — Venue Staff record a booking's preparation details
# --------------------------------------------------------------------------

PREPARATION_NOT_APPROVED_MESSAGE = (
    "Preparation can only be recorded for an approved booking; this one is {status}."
)


def update_preparation_details(
    request_id: int,
    payload: Mapping[str, Any] | None,
    *,
    updated_by: int,
    session: Session | None = None,
) -> BookingRequestAsShown:
    """Record the preparation status and notes of an approved booking (SCRUM-84).

    AC1-AC5. Any Venue Staff member may record them for any booking (ADR-0035
    decision 1). Each update replaces the status and notes, and the event's history
    gets an entry naming the user and the time in the same commit (AC4). Nothing else
    of the booking changes (AC3). The Safety Officer must have approved the event
    first (AC5, ADR-0047).

    Args:
        request_id: The booking request's id.
        payload: Decoded JSON body: ``status`` and optional ``notes``.
        updated_by: The Venue Staff user's id, taken from their token.
        session: Database session; defaults to ``db.session``.

    Returns:
        The booking request, with its event's details beside it.

    Raises:
        ValidationError: 400 — payload invalid, or it names a field other than these.
        NotFoundError: 404 — no such booking request.
        ConflictError: 409 — the request isn't approved, or the Safety Officer hasn't
            approved the event.
    """
    from app.modules.events import services as event_services  # circular at import time

    data = load_or_raise(UpdatePreparationSchema(), payload)
    sess = resolve_session(session)
    request = sess.get(VenueBookingRequest, request_id)
    if request is None:
        raise NotFoundError(BOOKING_REQUEST_NOT_FOUND_MESSAGE)
    if request.status is not BookingRequestStatus.APPROVED:
        raise ConflictError(PREPARATION_NOT_APPROVED_MESSAGE.format(status=request.status.value))
    if not event_services.has_safety_approval(request.event_id, session=sess):
        raise ConflictError(PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE)

    request.preparation_status = data["status"]
    request.preparation_notes = data["notes"]
    event_services.record_venue_preparation_updated(
        request.event_id,
        actor_id=updated_by,
        details={
            "venue_booking_request_id": request.id,
            "venue_id": request.venue_id,
            "status": data["status"].value,
            "notes": data["notes"],
        },
        session=sess,
    )
    sess.commit()
    event = event_services.get_events_for_booking([request.event_id], session=sess)[
        request.event_id
    ]
    return show_booking_request(request, event)


# --------------------------------------------------------------------------
# SCRUM-75 — place a tentative hold on a venue
# --------------------------------------------------------------------------

SINGLE_VENUE_HOLD_MESSAGE = (
    "A hold can only be placed on a request of an event with more than one venue."
)
HOLD_NOT_ALLOWED_MESSAGE = (
    "Only a pending or conflicting request can be held; this one is {status}."
)
NOT_ON_HOLD_MESSAGE = "Only a request on hold has an expiry to change; this one is {status}."
EXPIRY_NOT_FUTURE_MESSAGE = "The expiry must be in the future."
EXPIRY_NOT_BEFORE_EVENT_MESSAGE = "The expiry must be before the event starts."


def _expiry_error(message: str) -> ValidationError:
    """The 400 for an expiry that breaks one of AC3's limits, keyed on the field."""
    return ValidationError("Invalid request.", details={"expires_at": [message]})


def _require_valid_expiry(expires_at: datetime, event: EventForBooking) -> None:
    """The expiry must be in the future and before the event starts (SCRUM-75 AC3).

    The system sets no minimum or maximum length: Venue Staff choose it.

    Raises:
        ValidationError: 400 — the expiry has passed, or is not before the event starts.
    """
    if expires_at <= _utc_now():
        raise _expiry_error(EXPIRY_NOT_FUTURE_MESSAGE)
    event_starts_at = as_utc(datetime.combine(event.proposed_date, event.start_time))
    if expires_at >= event_starts_at:
        raise _expiry_error(EXPIRY_NOT_BEFORE_EVENT_MESSAGE)


def _event_to_hold_for(request: VenueBookingRequest, session: Session | None) -> EventForBooking:
    """The request's event, if it has more than one active venue arrangement (AC1).

    A rejected arrangement is still active until the coordinator withdraws it.
    Eligibility is checked when the hold is placed (ADR-0045), so a hold already placed
    stands even if the event later drops to one venue.

    Raises:
        ConflictError: 409 — the event has only this venue.
    """
    if count_active_arrangements(request.event_id, session=session) < 2:
        raise ConflictError(SINGLE_VENUE_HOLD_MESSAGE)
    return _event_of(request, session)


def _notify_hold(
    request: VenueBookingRequest,
    event: EventForBooking,
    kind: NotificationKind,
    session: Session | None,
) -> None:
    """Tell the event's assigned coordinator about its hold, with the expiry.

    The coordinator assigned now, not whoever raised the request: the event may have
    been reassigned since (SCRUM-75 AC9, SCRUM-94 AC3).
    """
    expires_at = to_business_time(request.booking.hold_expires_at)
    _notify_about_booking(
        [event.coordinator_id], event, kind, detail=expires_at.isoformat(), session=session
    )


def place_booking_hold(
    request_id: int, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> BookingRequestAsShown:
    """Hold the venue tentatively instead of confirming the booking (SCRUM-75 AC1-AC3).

    Venue Staff place a hold on a request of a multi-venue event, with an expiry they
    choose. It is checked for clashes exactly as an approval is (SCRUM-44), then makes a
    tentative booking for the request's period and moves the request to On Hold. The
    coordinator who raised the request is told, with the expiry, in a second commit.

    Args:
        request_id: The request's own id, as the queue lists it.
        payload: Decoded JSON body: ``expires_at``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The held request, with its event's details beside it.

    Raises:
        NotFoundError: 404 — no such request.
        ConflictError: 409 — the request is not Pending or Conflicting, the event has
            only one venue, or the hold clashes with a booking or another hold (the
            body names it).
        ValidationError: 400 — the expiry is missing, has passed or is not before the
            event starts.
    """
    request = _locked_request(request_id, session)
    if request.status not in HOLDABLE_REQUEST_STATUSES:
        raise ConflictError(HOLD_NOT_ALLOWED_MESSAGE.format(status=request.status.value))
    data = load_or_raise(HoldBookingRequestSchema(), payload)
    event = _event_to_hold_for(request, session)
    _require_valid_expiry(data["expires_at"], event)
    _refuse_clash(request, session)

    hold = _booking_for(request)
    hold.status = BookingStatus.TENTATIVE
    hold.hold_expires_at = data["expires_at"]
    request.booking = hold
    request.status = BookingRequestStatus.ON_HOLD
    resolve_session(session).commit()
    _notify_hold(request, event, NotificationKind.VENUE_HOLD_PLACED, session)
    return show_booking_request(request, event)


def change_hold_expiry(
    request_id: int, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> BookingRequestAsShown:
    """Move an active hold's expiry (SCRUM-75 AC4).

    The new expiry follows the rules of the first: in the future and before the event
    starts. The coordinator is told the new expiry in a second commit.

    Args:
        request_id: The request's own id.
        payload: Decoded JSON body: ``expires_at``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, with its event's details beside it.

    Raises:
        NotFoundError: 404 — no such request.
        ConflictError: 409 — the request is not On Hold, or its hold has expired.
        ValidationError: 400 — the expiry is missing, has passed or is not before the
            event starts.
    """
    request = _locked_request(request_id, session)
    if request.status is not BookingRequestStatus.ON_HOLD:
        raise ConflictError(NOT_ON_HOLD_MESSAGE.format(status=request.status.value))
    if _hold_has_expired(request.booking):
        raise ConflictError(HOLD_EXPIRED_MESSAGE)
    data = load_or_raise(HoldBookingRequestSchema(), payload)
    event = _event_of(request, session)
    _require_valid_expiry(data["expires_at"], event)

    request.booking.hold_expires_at = data["expires_at"]
    # The warning follows the new expiry (SCRUM-94 AC4), so it may be sent again.
    request.booking.hold_warning_sent_at = None
    resolve_session(session).commit()
    _notify_hold(request, event, NotificationKind.VENUE_HOLD_EXPIRY_CHANGED, session)
    return show_booking_request(request, event)


# --------------------------------------------------------------------------
# SCRUM-94 — expire tentative holds automatically
# --------------------------------------------------------------------------

#: How long before a hold expires its coordinator is warned (SCRUM-94 AC3). The customer
#: gave no lead time, so this is the team's default, pending the customer (ADR-0052).
HOLD_WARNING_LEAD = timedelta(hours=24)


def _requests_on_hold(
    *conditions: ColumnElement[bool], session: Session | None
) -> list[VenueBookingRequest]:
    """The requests On Hold whose hold meets every one of ``conditions``, by id."""
    query = (
        select(VenueBookingRequest)
        .join(Booking, VenueBookingRequest.booking_id == Booking.id)
        .where(VenueBookingRequest.status == BookingRequestStatus.ON_HOLD, *conditions)
        .order_by(VenueBookingRequest.id)
    )
    return list(resolve_session(session).scalars(query))


def _expire_hold(request: VenueBookingRequest, now: datetime, session: Session | None) -> None:
    """Mark the request Expired, with an entry in its event's history, in one commit.

    The hold's booking is left as it is: tentative, with the expiry that has passed, so
    :func:`_booking_is_live` already ignores it and the history can say when it ran out.
    """
    from app.modules.events import services as event_services  # circular at import time

    hold = request.booking
    request.status = BookingRequestStatus.EXPIRED
    event_services.record_venue_hold_expired(
        request.event_id,
        details={
            "venue_booking_request_id": request.id,
            "venue_id": request.venue_id,
            "booking_id": hold.id,
            "expires_at": hold.hold_expires_at.isoformat(),
        },
        now=now,
        session=session,
    )
    resolve_session(session).commit()


def expire_holds(
    *, now: datetime | None = None, session: Session | None = None
) -> list[VenueBookingRequest]:
    """Expire every hold whose expiry has passed (SCRUM-94 AC1, AC2, AC3, AC6).

    Each request On Hold whose expiry is at or before ``now`` moves to Expired, with an
    entry in its event's history, and the event's coordinator is told in a second
    commit (ADR-0015). Only requests still On Hold are read, so running it again expires
    and tells nothing twice. The venue was free from the expiry instant already, because
    an expired hold is ignored when bookings are read (ADR-0045 decision 17).

    Args:
        now: The instant to compare expiries with; defaults to the current one.
        session: Database session; defaults to ``db.session``.

    Returns:
        The requests it expired, by id.
    """
    if now is None:
        now = _utc_now()
    run_out = _requests_on_hold(Booking.hold_expires_at <= now, session=session)
    events = _events_of(run_out, session)
    for request in run_out:
        _expire_hold(request, now, session)
        event = events[request.event_id]
        _notify_hold(request, event, NotificationKind.VENUE_HOLD_EXPIRED, session)
    return run_out


def send_hold_expiry_warnings(
    *, now: datetime | None = None, session: Session | None = None
) -> list[VenueBookingRequest]:
    """Warn coordinators of the holds that expire within 24 hours (SCRUM-94 AC3, AC4).

    A hold is due a warning from 24 hours before its expiry until the expiry itself; a
    hold that has already run out is expired instead, by :func:`expire_holds`. The time
    of the warning is saved on the hold in its own commit before the coordinator is
    told, so running it again warns nobody twice. Changing the expiry clears it
    (:func:`change_hold_expiry`), so the warning follows the new time.

    Args:
        now: The instant to compare expiries with; defaults to the current one.
        session: Database session; defaults to ``db.session``.

    Returns:
        The requests whose coordinators it warned, by id.
    """
    if now is None:
        now = _utc_now()
    due = _requests_on_hold(
        Booking.hold_warning_sent_at.is_(None),
        Booking.hold_expires_at > now,
        Booking.hold_expires_at <= now + HOLD_WARNING_LEAD,
        session=session,
    )
    events = _events_of(due, session)
    for request in due:
        event = events[request.event_id]
        request.booking.hold_warning_sent_at = now
        resolve_session(session).commit()
        _notify_hold(request, event, NotificationKind.VENUE_HOLD_EXPIRING, session)
    return due
