"""Business logic for the venue module.

Same shape as ``app.modules.auth.services``: routes call these functions,
tests call them directly against a mocked session, and (eventually) other
modules would call them instead of touching the models directly. Every
function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from flask import current_app, has_app_context
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.extensions import db
from app.modules.auth.permissions import Role
from app.modules.venue.models import (
    Booking,
    BookingStatus,
    Venue,
    VenueBlock,
    _to_csv,
    venue_to_dict,
)
from app.modules.venue.schemas import (
    VenueBlockSchema,
    VenueSchema,
    VenueSearchSchema,
    load_or_raise,
)

#: Defaults used when SCRUM-67's buffer fields are not set explicitly
#: (AC2). Configurable — see STORIES.md for the open customer question on
#: whether this should ever vary by event type / room layout.
DEFAULT_SETUP_MINUTES = 30
DEFAULT_TURNAROUND_MINUTES = 30

_LIST_FIELDS = ("facilities", "accessibility_features", "supported_layouts")


def _session(session: Session | None) -> Session:
    return session if session is not None else db.session


def default_setup_minutes() -> int:
    if has_app_context():
        return int(current_app.config.get("DEFAULT_VENUE_SETUP_MINUTES", DEFAULT_SETUP_MINUTES))
    return DEFAULT_SETUP_MINUTES  # pragma: no cover - only hit outside an app context


def default_turnaround_minutes() -> int:
    if has_app_context():
        return int(
            current_app.config.get("DEFAULT_VENUE_TURNAROUND_MINUTES", DEFAULT_TURNAROUND_MINUTES)
        )
    return DEFAULT_TURNAROUND_MINUTES  # pragma: no cover - only hit outside an app context


def _apply_buffer_defaults(data: dict[str, Any]) -> None:
    """Materialise the configured default wherever a buffer field is
    present but explicitly unset (AC2). Applies to both create (where the
    keys are always present, defaulted to ``None`` by the schema) and a
    partial update that explicitly clears a value back to "unset".
    """
    if "setup_minutes" in data and data["setup_minutes"] is None:
        data["setup_minutes"] = default_setup_minutes()
    if "turnaround_minutes" in data and data["turnaround_minutes"] is None:
        data["turnaround_minutes"] = default_turnaround_minutes()


def _effective_window(venue: Venue, start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Expand a booking's start/end by the venue's setup and turnaround buffers."""
    return (
        start - timedelta(minutes=venue.setup_minutes),
        end + timedelta(minutes=venue.turnaround_minutes),
    )


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


# --------------------------------------------------------------------------
# SCRUM-25 / SCRUM-67 — catalogue CRUD, deactivate/reactivate, buffer fields
# --------------------------------------------------------------------------


def get_venue(venue_id: int | str, *, session: Session | None = None) -> Venue:
    """Fetch a venue by primary key, active or not.

    Raises:
        NotFoundError: if no such venue exists.
    """
    venue = _session(session).get(Venue, int(venue_id))
    if venue is None:
        raise NotFoundError("Venue not found.")
    return venue


def list_venues(*, session: Session | None = None) -> list[Venue]:
    """Active venues only — a deactivated venue no longer appears here (AC5)."""
    stmt = select(Venue).where(Venue.is_active.is_(True)).order_by(Venue.name)
    return list(_session(session).scalars(stmt).all())


def create_venue(payload: Mapping[str, Any] | None, *, session: Session | None = None) -> Venue:
    """Create a venue (SCRUM-25 AC1/AC2).

    Raises:
        ValidationError: 400 — missing/blank required fields or invalid values.
    """
    data = load_or_raise(VenueSchema(), payload)
    _apply_buffer_defaults(data)
    sess = _session(session)

    venue = Venue(
        name=data["name"].strip(),
        location=data["location"].strip(),
        capacity=data["capacity"],
        facilities=_to_csv(data["facilities"]),
        accessibility_features=_to_csv(data["accessibility_features"]),
        supported_layouts=_to_csv(data["supported_layouts"]),
        operating_hours_start=data["operating_hours_start"],
        operating_hours_end=data["operating_hours_end"],
        setup_minutes=data["setup_minutes"],
        turnaround_minutes=data["turnaround_minutes"],
    )
    sess.add(venue)
    sess.commit()
    return venue


def update_venue(
    venue_id: int | str, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> tuple[Venue, list[dict[str, Any]]]:
    """Update a venue's editable fields (SCRUM-25 AC1/AC2, SCRUM-67 AC4).

    Only the fields present in ``payload`` are changed. If ``setup_minutes``
    or ``turnaround_minutes`` actually changes, existing confirmed bookings
    are re-checked against the new buffer: they are **not** invalidated, but
    any pair that now overlaps is reported back to the caller.

    Returns:
        The updated venue and a list of overlap-warning dicts (empty if the
        buffers didn't change or nothing now overlaps).

    Raises:
        NotFoundError: 404 — no such venue.
        ValidationError: 400 — invalid values for the supplied fields.
    """
    data = load_or_raise(VenueSchema(), payload, partial=True)
    _apply_buffer_defaults(data)
    sess = _session(session)
    venue = get_venue(venue_id, session=sess)

    buffers_changing = ("setup_minutes" in data and data["setup_minutes"] != venue.setup_minutes) or (
        "turnaround_minutes" in data and data["turnaround_minutes"] != venue.turnaround_minutes
    )

    for field in _LIST_FIELDS:
        if field in data:
            data[field] = _to_csv(data[field])
    for key, value in data.items():
        setattr(venue, key, value)

    sess.commit()

    overlap_warnings = _find_confirmed_overlaps(venue, sess) if buffers_changing else []
    return venue, overlap_warnings


def _find_confirmed_overlaps(venue: Venue, session: Session) -> list[dict[str, Any]]:
    """Pairs of confirmed bookings that overlap under the venue's *current* buffers."""
    stmt = select(Booking).where(Booking.venue_id == venue.id, Booking.status == BookingStatus.CONFIRMED)
    bookings = list(session.scalars(stmt).all())

    warnings: list[dict[str, Any]] = []
    for i, a in enumerate(bookings):
        a_start, a_end = _effective_window(venue, a.start_time, a.end_time)
        for b in bookings[i + 1 :]:
            b_start, b_end = _effective_window(venue, b.start_time, b.end_time)
            if _overlaps(a_start, a_end, b_start, b_end):
                warnings.append(
                    {
                        "booking_ids": [a.id, b.id],
                        "overlap_start": max(a_start, b_start),
                        "overlap_end": min(a_end, b_end),
                    }
                )
    return warnings


def deactivate_venue(venue_id: int | str, *, session: Session | None = None) -> Venue:
    """Deactivate a venue (SCRUM-25 AC5): drops out of search, bookings untouched."""
    sess = _session(session)
    venue = get_venue(venue_id, session=sess)
    venue.is_active = False
    sess.commit()
    return venue


def reactivate_venue(venue_id: int | str, *, session: Session | None = None) -> Venue:
    """Reactivate a previously deactivated venue (SCRUM-25 AC6)."""
    sess = _session(session)
    venue = get_venue(venue_id, session=sess)
    venue.is_active = True
    sess.commit()
    return venue


def create_block(
    venue_id: int | str, payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> VenueBlock:
    """Record a maintenance/renovation/safety block against a venue.

    Minimal supporting endpoint for SCRUM-26 AC2 ("blocked periods... appear
    as unavailable") — there is no dedicated "block a venue" story yet, but
    without a way to create one the AC has no path to exercise via the API.
    """
    data = load_or_raise(VenueBlockSchema(), payload)
    sess = _session(session)
    venue = get_venue(venue_id, session=sess)

    block = VenueBlock(
        venue_id=venue.id,
        start_time=data["start_time"],
        end_time=data["end_time"],
        reason=data["reason"],
    )
    sess.add(block)
    sess.commit()
    return block


# --------------------------------------------------------------------------
# SCRUM-26 — availability calendar
# --------------------------------------------------------------------------


def _booking_reason(booking: Booking, viewer_role: Role | str | None) -> str:
    if viewer_role == Role.VENUE_STAFF:
        return f"Event #{booking.event_id}" if booking.event_id is not None else "Booking (no linked event)"
    return "booking"


def _block_reason(block: VenueBlock, viewer_role: Role | str | None) -> str:
    if viewer_role == Role.VENUE_STAFF:
        return block.reason or "Maintenance"
    return "maintenance"


def get_venue_calendar(
    venue_id: int | str,
    range_start: datetime,
    range_end: datetime,
    *,
    viewer_role: Role | str | None,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """Bookings and blocked periods for a venue across a date range (SCRUM-26).

    ``reason`` detail is role-gated: Venue Staff see the full reason, other
    internal roles (the only other callers permitted through
    ``requires_role(*INTERNAL_ROLES)``) see only a coarse category.

    Raises:
        NotFoundError: 404 — no such venue.
    """
    sess = _session(session)
    venue = get_venue(venue_id, session=sess)

    entries: list[dict[str, Any]] = []

    booking_stmt = select(Booking).where(
        Booking.venue_id == venue.id,
        Booking.status != BookingStatus.CANCELLED,
        Booking.start_time < range_end,
        Booking.end_time > range_start,
    )
    for booking in sess.scalars(booking_stmt).all():
        buf_start, buf_end = _effective_window(venue, booking.start_time, booking.end_time)
        kind = "confirmed_booking" if booking.status == BookingStatus.CONFIRMED else "tentative_hold"
        entries.append(
            {
                "start_time": buf_start,
                "end_time": buf_end,
                "kind": kind,
                "reason": _booking_reason(booking, viewer_role),
            }
        )

    block_stmt = select(VenueBlock).where(
        VenueBlock.venue_id == venue.id,
        VenueBlock.start_time < range_end,
        VenueBlock.end_time > range_start,
    )
    for block in sess.scalars(block_stmt).all():
        entries.append(
            {
                "start_time": block.start_time,
                "end_time": block.end_time,
                "kind": "block",
                "reason": _block_reason(block, viewer_role),
            }
        )

    return sorted(entries, key=lambda e: e["start_time"])


# --------------------------------------------------------------------------
# SCRUM-35 — search and filter
# --------------------------------------------------------------------------


def _has_conflict(venue: Venue, start: datetime, end: datetime, session: Session) -> bool:
    booking_stmt = select(Booking).where(
        Booking.venue_id == venue.id, Booking.status != BookingStatus.CANCELLED
    )
    for booking in session.scalars(booking_stmt).all():
        buf_start, buf_end = _effective_window(venue, booking.start_time, booking.end_time)
        if _overlaps(start, end, buf_start, buf_end):
            return True

    block_stmt = select(VenueBlock).where(VenueBlock.venue_id == venue.id)
    for block in session.scalars(block_stmt).all():
        if _overlaps(start, end, block.start_time, block.end_time):
            return True

    return False


def search_venues(
    payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> list[dict[str, Any]]:
    """Search venues against an event's requirements (SCRUM-35).

    Raises:
        ValidationError: 400 — missing/invalid filters.
    """
    data = load_or_raise(VenueSearchSchema(), payload)
    sess = _session(session)

    stmt = select(Venue).where(Venue.is_active.is_(True), Venue.capacity >= data["min_capacity"])
    candidates = sess.scalars(stmt).all()

    results: list[dict[str, Any]] = []
    for venue in candidates:
        if data["location"] and data["location"].strip().lower() not in venue.location.lower():
            continue

        if data["required_facilities"]:
            if not set(data["required_facilities"]).issubset(set(venue.facilities_list())):
                continue

        if data["required_layout"] and data["required_layout"] not in venue.layouts_list():
            continue

        if data["required_accessibility"]:
            if not set(data["required_accessibility"]).issubset(set(venue.accessibility_list())):
                continue

        if _has_conflict(venue, data["start_time"], data["end_time"], sess):
            continue

        results.append(
            {
                "id": venue.id,
                "name": venue.name,
                "capacity": venue.capacity,
                "location": venue.location,
                "matched_requirements": {
                    "facilities": data["required_facilities"],
                    "layout": data["required_layout"],
                    "accessibility_features": data["required_accessibility"],
                },
            }
        )

    return results
