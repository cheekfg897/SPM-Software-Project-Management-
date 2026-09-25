"""Business logic for the venue module.

Same shape as ``app.modules.auth.services``: routes call these functions, tests
call them directly, and other modules call them instead of touching the models.
Every function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.common.errors import NotFoundError
from app.common.validation import load_or_raise
from app.modules.auth.permissions import Role
from app.modules.venue.models import (
    Booking,
    BookingStatus,
    CalendarEntryKind,
    Venue,
    VenueBlock,
    VenueOpeningPeriod,
    join_list_field,
)
from app.modules.venue.opening_hours import Period
from app.modules.venue.schemas import EditVenueSchema, VenueSearchSchema

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


def _confirmed_overlaps(venue: Venue, session: Session) -> list[OverlapWarning]:
    """Every pair of the venue's confirmed bookings whose padded periods overlap."""
    bookings = session.scalars(
        select(Booking)
        .where(Booking.venue_id == venue.id, Booking.status == BookingStatus.CONFIRMED)
        .order_by(Booking.start_time, Booking.id)
    ).all()
    warnings: list[OverlapWarning] = []
    for index, first in enumerate(bookings):
        first_start, first_end = _occupied(venue, first.start_time, first.end_time)
        for second in bookings[index + 1 :]:
            second_start, second_end = _occupied(venue, second.start_time, second.end_time)
            overlap_start = max(first_start, second_start)
            overlap_end = min(first_end, second_end)
            if overlap_start < overlap_end:
                warnings.append(OverlapWarning((first.id, second.id), overlap_start, overlap_end))
    return warnings


def update_venue(
    venue_id: int, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> tuple[Venue, list[OverlapWarning]]:
    """Update a venue's editable fields (SCRUM-25 AC1/AC2, SCRUM-67 AC1/AC4).

    Only the fields present in ``payload`` are changed. ``opening_hours``, if
    present, replaces the whole weekly schedule (ADR-0008).

    If the setup or turnaround time changes, confirmed bookings are left as they are
    but re-checked against the new padding, and any pair that now overlaps is returned.

    Returns:
        The updated venue, and the overlap warnings (empty unless a buffer changed).

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
        return venue, []
    return venue, _confirmed_overlaps(venue, sess)


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
class VenueMatch:
    """A venue that meets a search, and what it offers of each requested requirement."""

    venue: Venue
    facilities: list[str]
    accessibility_features: list[str]
    layout: str | None


def _match_requirements(venue: Venue, data: Mapping[str, Any]) -> VenueMatch | None:
    """What the venue offers of each requested requirement; ``None`` if it lacks any."""
    facilities = [item for item in data["required_facilities"] if item in venue.facilities_list()]
    accessibility = [
        item for item in data["required_accessibility"] if item in venue.accessibility_list()
    ]
    if len(facilities) < len(data["required_facilities"]):
        return None
    if len(accessibility) < len(data["required_accessibility"]):
        return None
    layout = data["required_layout"]
    if layout is not None and layout not in venue.layouts_list():
        return None
    return VenueMatch(venue, facilities, accessibility, layout)


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
