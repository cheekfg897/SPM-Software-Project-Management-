"""Business logic for the venue module.

Same shape as ``app.modules.auth.services``: routes call these functions, tests
call them directly, and other modules call them instead of touching the models.
Every function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from flask import current_app
from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.clock import to_business_time
from app.common.database import resolve_session
from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.auth.permissions import Role
from app.modules.auth.services import list_user_ids_with_role
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users
from app.modules.venue.models import (
    RETIRED_REQUEST_STATUSES,
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
    RaiseBookingRequestSchema,
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


def _confirmed_bookings(venue: Venue, session: Session) -> list[Booking]:
    """The venue's confirmed bookings, in start order."""
    stmt = (
        select(Booking)
        .where(Booking.venue_id == venue.id, Booking.status == BookingStatus.CONFIRMED)
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


def update_venue(
    venue_id: int, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> tuple[Venue, list[OverlapWarning], list[BlockOverlapWarning]]:
    """Update a venue's editable fields (SCRUM-25 AC1/AC2, SCRUM-67 AC1/AC4).

    Only the fields present in ``payload`` are changed. ``opening_hours``, if
    present, replaces the whole weekly schedule (ADR-0008).

    If the setup or turnaround time changes, confirmed bookings and blocks are left as
    they are but re-checked against the new padding (ADR-0033). Every pair of confirmed
    bookings that now overlaps is returned, and so is every confirmed booking that now
    runs into a block.

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

    sess.commit()
    if _buffers(venue) == buffers_before:
        return venue, [], []
    bookings = _confirmed_bookings(venue, sess)
    return venue, _confirmed_overlaps(venue, bookings), _block_overlaps(venue, bookings, sess)


def deactivate_venue(venue_id: int, *, session: Session | None = None) -> Venue:
    """Deactivate a venue (SCRUM-25 AC5): drops out of listing and search."""
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    venue.is_active = False
    sess.commit()
    return venue


def reactivate_venue(venue_id: int, *, session: Session | None = None) -> Venue:
    """Reactivate a previously deactivated venue (SCRUM-25 AC6)."""
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)
    venue.is_active = True
    sess.commit()
    return venue


# --------------------------------------------------------------------------
# SCRUM-26 — availability calendar
# --------------------------------------------------------------------------

#: How each non-cancelled booking status shows on the calendar.
_CALENDAR_KIND_BY_STATUS = {
    BookingStatus.CONFIRMED: CalendarEntryKind.CONFIRMED_BOOKING,
    BookingStatus.TENTATIVE: CalendarEntryKind.TENTATIVE_HOLD,
}


def _overlaps(
    model: type[Booking] | type[VenueBlock], start: datetime, end: datetime
) -> ColumnElement[bool]:
    """SQL condition: the row's period overlaps ``start``-``end``.

    Periods that only touch (one ends at 11:00, the next starts at 11:00) don't overlap.
    """
    return and_(model.start_time < end, model.end_time > start)


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
    with its kind; cancelled bookings aren't. How much of the reason a viewer sees
    depends on their role (AC3). A booking is shown as the period it holds the venue,
    padded by setup and turnaround, with the event's own times alongside (SCRUM-67);
    a block isn't padded, so its event times are ``None``.

    Raises:
        NotFoundError: 404 — no such venue.
    """
    sess = resolve_session(session)
    venue = get_venue(venue_id, session=sess)

    bookings = sess.scalars(
        select(Booking).where(
            Booking.status != BookingStatus.CANCELLED,
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


def _booking_clash(venue: Venue, start: datetime, end: datetime) -> ColumnElement[bool]:
    """SQL condition: a booking on ``venue`` too close to ``start``-``end``.

    The booking and the requested event each hold the venue from their start minus
    setup to their end plus turnaround, so they clash unless setup + turnaround
    separates them (ADR-0011).
    """
    setup, turnaround = _buffers(venue)
    gap = setup + turnaround
    return and_(Booking.venue_id == venue.id, _overlaps(Booking, start - gap, end + gap))


def search_venues(
    payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> list[VenueMatch]:
    """Active venues that meet an event's requirements and are free for its period.

    Two queries. The first selects active venues by capacity and location and leaves
    out any blocked during the period (AC1, AC2). Facilities, accessibility and layout
    are stored as joined strings, so they're checked on the venues it returns. The
    second finds which of those have a non-cancelled booking too close to the period,
    each venue padded by its own setup and turnaround (SCRUM-67, ADR-0011); that
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
        Booking.status != BookingStatus.CANCELLED, or_(*clash_conditions)
    )
    busy_venue_ids = set(sess.scalars(clashing_bookings))
    return [match for match in matches if match.venue.id not in busy_venue_ids]


# --------------------------------------------------------------------------
# SCRUM-34 — block a venue for maintenance or internal use
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ConflictingBooking:
    """A confirmed booking a new block cuts into (SCRUM-34 AC2).

    ``start_time`` and ``end_time`` are the period the booking holds the venue,
    setup and turnaround included (ADR-0011), as the calendar shows it.
    """

    booking_id: int
    event_id: int | None
    start_time: datetime
    end_time: datetime


def _bookings_cut_by(venue: Venue, block: VenueBlock, session: Session) -> list[ConflictingBooking]:
    """The venue's confirmed bookings that hold it at some time during ``block``."""
    bookings = session.scalars(
        select(Booking)
        .where(
            Booking.status == BookingStatus.CONFIRMED,
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
    """Block a venue for a period, with a reason (SCRUM-34 AC1).

    The block is saved even if it cuts into confirmed bookings; those are returned
    so Venue Staff can see what they're blocking (AC2, ADR-0016). Nothing happens to
    the bookings themselves. Once saved, the calendar shows the block and search
    leaves the venue out for that period (AC3).

    Args:
        venue_id: The venue to block.
        payload: Decoded JSON body: ``start_time``, ``end_time`` and ``reason``.
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
    sess.commit()
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

    The block must belong to the venue in the request (ADR-0016).

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

    Raises:
        ValidationError: 400 — invalid payload, unknown venue, a period outside the
            venue's operating hours, or no justification.
        NotFoundError: 404 — no such event, or ``requested_by`` doesn't coordinate it.
        ConflictError: 409 — the event isn't approved.
    """
    from app.modules.events import services as event_services  # circular at import time

    data = load_or_raise(RaiseBookingRequestSchema(), payload)
    event = event_services.get_approved_event_for_coordinator(
        reference, requested_by, session=session
    )
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


ARRANGEMENT_NOT_FOUND_MESSAGE = "Venue arrangement not found."
WITHDRAW_NOT_PENDING_MESSAGE = "Only a pending arrangement can be withdrawn; this one is {status}."
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
        ConflictError: 409 — the arrangement is no longer pending.
    """
    from app.modules.events import services as event_services  # circular at import time

    if arrangement.status is not BookingRequestStatus.PENDING:
        raise ConflictError(WITHDRAW_NOT_PENDING_MESSAGE.format(status=arrangement.status.value))
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
    """Retract one of an event's arrangements before Venue Staff decide it (AC6).

    The event's other arrangements are untouched. The withdrawal and its history entry
    are saved in one commit.

    Raises:
        NotFoundError: 404 — no such event among the coordinator's own, or no such
            arrangement on it.
        ConflictError: 409 — the arrangement is no longer pending.
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
    Every active arrangement is pending today, so each is withdrawn; SCRUM-43 adds
    cancelling the approved ones. An event with none is not an error.

    Returns:
        The retired arrangements, earliest period first, or an empty list.

    Raises:
        NotFoundError: 404 — no such event among the coordinator's own.
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


def list_pending_booking_requests(*, session: Session | None = None) -> list[BookingRequestAsShown]:
    """Every request waiting for a decision, the earliest event first (AC1, AC2).

    Any Venue Staff member sees the whole queue: staff are not assigned to venues
    (ADR-0035 decision 1). The order is the event's date, then its start time, then the
    request's id, so a queue read twice is in the same order. The events are read
    through the events service and the ordering is done here, because the date lives in
    the events module and this module may not join across it.
    """
    from app.modules.events import services as event_services  # circular at import time

    requests = list(
        resolve_session(session).scalars(
            select(VenueBookingRequest).where(
                VenueBookingRequest.status == BookingRequestStatus.PENDING
            )
        )
    )
    events = event_services.get_events_for_booking(
        {request.event_id for request in requests}, session=session
    )
    waiting = [(events[request.event_id], request) for request in requests]
    waiting.sort(key=lambda pair: (pair[0].proposed_date, pair[0].start_time, pair[1].id))
    return [show_booking_request(request, event) for event, request in waiting]


def _request_to_decide(request_id: int, session: Session | None) -> VenueBookingRequest:
    """The request ``request_id`` names, if it is still waiting for a decision.

    The row is locked while it is read, as the equipment type is before a reservation is
    counted (ADR-0037): two Venue Staff deciding the same request at the same moment
    would otherwise both see it Pending and both book the venue. ``populate_existing``
    is needed with it, because a copy the session loaded earlier may predate the other
    decision's commit, and the locked row has to overwrite it rather than be skipped as
    already known.

    Raises:
        NotFoundError: 404 — no such request.
        ConflictError: 409 — it was decided or withdrawn already; the message names
            the status it is in.
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
    if request.status is not BookingRequestStatus.PENDING:
        raise ConflictError(DECISION_NOT_PENDING_MESSAGE.format(status=request.status.value))
    return request


def _booking_for(request: VenueBookingRequest) -> Booking:
    """The confirmed booking an approval makes, for the period asked for (AC3).

    Whether the period clashes with another booking is SCRUM-44's check; this story's
    ACs do not ask for one (ADR-0042).
    """
    return Booking(
        venue_id=request.venue_id,
        event_id=request.event_id,
        start_time=request.starts_at,
        end_time=request.ends_at,
        status=BookingStatus.CONFIRMED,
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

    Holding a request instead of approving it is SCRUM-75, and refusing a period that
    clashes with another booking is SCRUM-44.

    Args:
        request_id: The request's own id, as the queue lists it.
        payload: Decoded JSON body: ``outcome`` and an optional ``reason``.
        decided_by: The deciding Venue Staff user's id, taken from their token.
        session: Database session; defaults to ``db.session``.

    Returns:
        The decided request, with its event's details beside it.

    Raises:
        NotFoundError: 404 — no such request.
        ConflictError: 409 — the request is not Pending.
        ValidationError: 400 — payload invalid, or a rejection without a reason.
    """
    from app.modules.events import services as event_services  # circular at import time

    request = _request_to_decide(request_id, session)
    data = load_or_raise(DecideBookingRequestSchema(), payload)
    decision = data["outcome"]
    reason = data["reason"]
    if decision is BookingDecision.REJECTED and reason is None:
        raise ValidationError(
            "Invalid request.", details={"reason": [REJECTION_REASON_REQUIRED_MESSAGE]}
        )

    # The request's event_id is a foreign key, so the event is always there.
    event = event_services.get_events_for_booking([request.event_id], session=session)[
        request.event_id
    ]
    request.decision_reason = reason
    booking = _booking_for(request) if decision is BookingDecision.APPROVED else None
    _save_decision(request, decision, booking, decided_by=decided_by, session=session)
    _notify_about_booking(
        [request.requested_by],
        event,
        _NOTIFICATION_BY_DECISION[decision],
        detail=reason,
        session=session,
    )
    return show_booking_request(request, event)
