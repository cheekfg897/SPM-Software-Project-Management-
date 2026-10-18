"""Unit tests for SCRUM-44 slice B — a buffer change marks the bookings it hits.

When a venue's setup or turnaround time changes, each confirmed booking that now
overlaps another booking or a block, the ones SCRUM-67's report lists, is marked
Conflicting. Nothing is deleted or cancelled, and a Conflicting booking still holds the
venue (ADR-0045).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.auth.permissions import Role
from app.modules.venue import services
from app.modules.venue.models import Booking, BookingStatus, CalendarEntryKind, Venue, VenueBlock
from tests.venue.conftest import (
    SaveBooking,
    SavedEvent,
    VenueWithBuffers,
    at,
    decide,
    period,
    raise_booking,
)

pytestmark = pytest.mark.scrum_44

CONFIRMED = BookingStatus.CONFIRMED
CONFLICTING = BookingStatus.CONFLICTING

MakeBlock = Callable[..., VenueBlock]
Save = Callable[..., None]


def _count(session: Session, model: type[Booking] | type[VenueBlock]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


# --------------------------------------------------------------------------
# AC7 — each affected booking is marked Conflicting, and nothing is deleted
# --------------------------------------------------------------------------


def test_a_buffer_change_marks_bookings_that_now_overlap_each_other(
    db_session: Session, venue_with_buffers: VenueWithBuffers, confirmed_booking: SaveBooking
) -> None:
    venue = venue_with_buffers(0, 0)
    first = confirmed_booking(venue, at(9), at(10))
    second = confirmed_booking(venue, at(10, 30), at(11))

    services.update_venue(venue.id, {"turnaround_minutes": 45}, session=db_session)

    assert (first.status, second.status) == (CONFLICTING, CONFLICTING)
    assert _count(db_session, Booking) == 2


def test_a_buffer_change_marks_a_booking_that_now_runs_into_a_block(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    make_block: MakeBlock,
    save: Save,
) -> None:
    venue = venue_with_buffers(0, 0)
    booking = confirmed_booking(venue, at(9), at(10))
    save(make_block(venue, at(10, 15), at(10, 30)))

    services.update_venue(venue.id, {"turnaround_minutes": 45}, session=db_session)

    assert booking.status is CONFLICTING
    assert _count(db_session, VenueBlock) == 1


@pytest.mark.parametrize(
    ("change", "second_start", "expected"),
    [
        ({"turnaround_minutes": 45}, at(10, 45), CONFIRMED),
        ({"turnaround_minutes": 45}, at(10, 30), CONFLICTING),
        ({"setup_minutes": 30}, at(10, 30), CONFIRMED),
        ({"setup_minutes": 45}, at(10, 30), CONFLICTING),
    ],
    ids=[
        "turnaround-ends-as-next-starts",
        "turnaround-runs-into-next",
        "setup-starts-as-previous-ends",
        "setup-reaches-back-into-previous",
    ],
)
def test_bookings_that_only_touch_after_a_change_are_not_marked(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    change: dict[str, int],
    second_start: datetime,
    expected: BookingStatus,
) -> None:
    """The first booking ends at 10:00; padding that ends as the next begins is fine."""
    venue = venue_with_buffers(0, 0)
    first = confirmed_booking(venue, at(9), at(10))
    second = confirmed_booking(venue, second_start, at(12))

    services.update_venue(venue.id, change, session=db_session)

    assert (first.status, second.status) == (expected, expected)


def test_a_buffer_change_marks_only_the_bookings_it_hits(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
) -> None:
    """Another venue's overlapping bookings and a far-off booking are left alone."""
    venue, other_venue = venue_with_buffers(0, 0), venue_with_buffers(0, 0)
    hit = confirmed_booking(venue, at(9), at(10)), confirmed_booking(venue, at(10, 30), at(11))
    far_off = confirmed_booking(venue, at(15), at(16))
    other_venue_booking = confirmed_booking(other_venue, at(9), at(10))
    confirmed_booking(other_venue, at(10, 30), at(11))

    services.update_venue(venue.id, {"turnaround_minutes": 45}, session=db_session)

    assert [booking.status for booking in hit] == [CONFLICTING, CONFLICTING]
    assert (far_off.status, other_venue_booking.status) == (CONFIRMED, CONFIRMED)


@pytest.mark.parametrize("status", [BookingStatus.TENTATIVE, BookingStatus.CANCELLED])
def test_a_booking_that_is_not_confirmed_is_not_marked(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    status: BookingStatus,
) -> None:
    venue = venue_with_buffers(0, 0)
    first = confirmed_booking(venue, at(9), at(10))
    other = confirmed_booking(venue, at(10, 30), at(11), status=status)

    services.update_venue(venue.id, {"turnaround_minutes": 45}, session=db_session)

    assert (first.status, other.status) == (CONFIRMED, status)


def test_a_change_to_another_field_marks_nothing(
    db_session: Session, venue_with_buffers: VenueWithBuffers, confirmed_booking: SaveBooking
) -> None:
    """The two bookings already overlap through the 45 minutes' turnaround."""
    venue = venue_with_buffers(0, 45)
    first = confirmed_booking(venue, at(9), at(10))
    second = confirmed_booking(venue, at(10, 30), at(11))

    services.update_venue(venue.id, {"capacity": 50}, session=db_session)

    assert (first.status, second.status) == (CONFIRMED, CONFIRMED)


# --------------------------------------------------------------------------
# ADR-0045 — a Conflicting booking still holds the venue
# --------------------------------------------------------------------------


@pytest.fixture()
def conflicting_booking(
    db_session: Session, venue_with_buffers: VenueWithBuffers, confirmed_booking: SaveBooking
) -> Booking:
    """A booking at 09:00-10:00 that a longer turnaround has marked Conflicting."""
    venue = venue_with_buffers(0, 0)
    booking = confirmed_booking(venue, at(9), at(10))
    confirmed_booking(venue, at(10, 30), at(11))
    services.update_venue(venue.id, {"turnaround_minutes": 45}, session=db_session)
    assert booking.status is CONFLICTING
    return booking


def test_a_conflicting_booking_still_refuses_an_approval_that_clashes(
    db_session: Session,
    conflicting_booking: Booking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = db_session.get(Venue, conflicting_booking.venue_id)
    request = raise_booking(venue, saved_event(), db_session, **period(at(9, 30), at(11, 30)))

    with pytest.raises(ConflictError) as refusal:
        decide(request.id, "approved", db_session)

    assert refusal.value.details["booking_id"] == conflicting_booking.id


def test_the_calendar_still_shows_a_conflicting_booking_as_booked(
    db_session: Session, conflicting_booking: Booking
) -> None:
    entries = services.get_venue_calendar(
        conflicting_booking.venue_id, at(8), at(9, 30), viewer_role=Role.VENUE_STAFF
    )

    assert [(entry.event_start, entry.kind) for entry in entries] == [
        (at(9), CalendarEntryKind.CONFIRMED_BOOKING)
    ]


def test_a_conflicting_booking_is_reported_again_by_the_next_buffer_change(
    db_session: Session, conflicting_booking: Booking
) -> None:
    _, overlaps, _ = services.update_venue(
        conflicting_booking.venue_id, {"turnaround_minutes": 50}, session=db_session
    )

    assert [warning.booking_ids[0] for warning in overlaps] == [conflicting_booking.id]


def test_a_new_block_lists_a_conflicting_booking_it_cuts_into(
    db_session: Session, conflicting_booking: Booking
) -> None:
    payload = {
        "start_time": at(9, 15).isoformat(),
        "end_time": at(9, 45).isoformat(),
        "category": "maintenance",
        "reason": "Repairs",
    }

    _, cut_into = services.block_venue(conflicting_booking.venue_id, payload, session=db_session)

    assert [booking.booking_id for booking in cut_into] == [conflicting_booking.id]
