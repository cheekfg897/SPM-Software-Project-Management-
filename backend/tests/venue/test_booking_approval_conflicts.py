"""Unit tests for SCRUM-44 slice A — approving a request that clashes is refused.

Approving a booking request is refused with a 409 when its period, padded by the
venue's setup and turnaround time, overlaps a confirmed booking at the same venue; the
body names that booking and whether only the padding clashes (ADR-0045). The first four
ACs' own examples are tests here. Marking pending requests Conflicting, re-checking
after a buffer change and the hold clauses are not in this slice.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sqlalchemy_event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.events.models import EventRequest
from app.modules.venue.models import (
    Booking,
    BookingRequestStatus,
    BookingStatus,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import SavedEvent, decide, raise_booking

pytestmark = pytest.mark.scrum_44

SINGAPORE = timezone(timedelta(hours=8))
VenueWithBuffers = Callable[..., Venue]
SaveBooking = Callable[..., Booking]


def _at(hour: int, minute: int = 0, *, day: int = 1) -> datetime:
    """A moment on 1 November 2026 (or ``day``) in Singapore time."""
    return datetime(2026, 11, day, hour, minute, tzinfo=SINGAPORE)


def _period(start: datetime, end: datetime) -> dict[str, str]:
    """The ``raise_booking`` overrides for a request from ``start`` to ``end``."""
    return {"starts_at": start.isoformat(), "ends_at": end.isoformat()}


@pytest.fixture()
def venue_with_buffers(
    make_venue: Callable[..., Venue], save: Callable[..., None]
) -> VenueWithBuffers:
    """Save a venue with the given setup and turnaround minutes."""

    def _save(setup_minutes: int, turnaround_minutes: int) -> Venue:
        saved = make_venue(setup_minutes=setup_minutes, turnaround_minutes=turnaround_minutes)
        save(saved)
        return saved

    return _save


@pytest.fixture()
def confirmed_booking(
    make_booking: Callable[..., Booking], save: Callable[..., None]
) -> SaveBooking:
    """Save a booking at a venue; it is confirmed unless ``status`` says otherwise."""

    def _save(
        venue: Venue,
        start: datetime,
        end: datetime,
        *,
        status: BookingStatus = BookingStatus.CONFIRMED,
        event_id: int | None = None,
    ) -> Booking:
        booking = make_booking(venue, start, end, status=status, event_id=event_id)
        save(booking)
        return booking

    return _save


def _request_for(
    venue: Venue, event: EventRequest, session: Session, start: datetime, end: datetime
) -> VenueBookingRequest:
    return raise_booking(venue, event, session, **_period(start, end))


def _refused_approval(request: VenueBookingRequest, session: Session) -> ConflictError:
    """Approve ``request``, expecting the 409 for a clash, and return it."""
    with pytest.raises(ConflictError) as refusal:
        decide(request.id, "approved", session)
    return refusal.value


def _bookings(session: Session) -> list[Booking]:
    return list(session.scalars(select(Booking).order_by(Booking.id)))


# --------------------------------------------------------------------------
# AC1 — an overlapping approved booking refuses the approval and is named
# --------------------------------------------------------------------------


def test_an_approval_overlapping_a_confirmed_booking_is_refused_and_names_it(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """AC1: 09:00-12:00 is booked, so 11:00-14:00 cannot be approved."""
    venue = venue_with_buffers(0, 0)
    existing = confirmed_booking(venue, _at(9), _at(12))
    request = _request_for(venue, saved_event(), db_session, _at(11), _at(14))

    refusal = _refused_approval(request, db_session)

    assert refusal.status_code == 409
    assert refusal.message == (
        f"Cannot approve: booking #{existing.id} already holds this venue "
        "during the requested period."
    )
    assert refusal.details == {
        "booking_id": existing.id,
        "in_buffer": False,
        "occupied_from": "2026-11-01T09:00:00+08:00",
        "occupied_until": "2026-11-01T12:00:00+08:00",
    }


def test_a_refused_approval_books_nothing_and_leaves_the_request_pending(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = venue_with_buffers(0, 0)
    existing = confirmed_booking(venue, _at(9), _at(12))
    request = _request_for(venue, saved_event(), db_session, _at(11), _at(14))

    _refused_approval(request, db_session)

    assert _bookings(db_session) == [existing]
    assert db_session.get(VenueBookingRequest, request.id).status is BookingRequestStatus.PENDING


def test_when_two_bookings_clash_the_earliest_is_named(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = venue_with_buffers(0, 0)
    # The later booking is saved first, so only the ordering puts the earlier one first.
    confirmed_booking(venue, _at(13), _at(15))
    earlier = confirmed_booking(venue, _at(10), _at(12))
    request = _request_for(venue, saved_event(), db_session, _at(11), _at(14))

    refusal = _refused_approval(request, db_session)

    assert refusal.details["booking_id"] == earlier.id


# --------------------------------------------------------------------------
# AC2, AC6 — the stored times are padded by setup and turnaround
# --------------------------------------------------------------------------


def test_the_conflicting_booking_is_reported_with_its_setup_and_turnaround(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """AC2: 30 minutes setup and 45 turnaround make 10:00-12:00 occupy 09:30-12:45."""
    venue = venue_with_buffers(30, 45)
    confirmed_booking(venue, _at(10), _at(12))
    request = _request_for(venue, saved_event(), db_session, _at(11), _at(14))

    refusal = _refused_approval(request, db_session)

    assert refusal.details["occupied_from"] == "2026-11-01T09:30:00+08:00"
    assert refusal.details["occupied_until"] == "2026-11-01T12:45:00+08:00"


# --------------------------------------------------------------------------
# AC3, AC4 — the padding decides near misses
# --------------------------------------------------------------------------


def test_a_request_far_enough_after_a_booking_for_its_padding_is_approved(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """AC3: 15 minutes setup, 30 turnaround, booked 09:00-12:00, so 13:00 is clear."""
    venue = venue_with_buffers(15, 30)
    confirmed_booking(venue, _at(9), _at(12))
    request = _request_for(venue, saved_event(), db_session, _at(13), _at(16))

    decided = decide(request.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED
    assert len(_bookings(db_session)) == 2


def test_a_request_inside_the_padding_is_refused_and_the_buffer_is_named(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """AC4: 30 minutes setup and turnaround, booking ends 12:00, 12:45 is too soon."""
    venue = venue_with_buffers(30, 30)
    existing = confirmed_booking(venue, _at(9), _at(12))
    request = _request_for(venue, saved_event(), db_session, _at(12, 45), _at(15))

    refusal = _refused_approval(request, db_session)

    assert refusal.message == (
        f"Cannot approve: the requested period is too close to booking #{existing.id}; this "
        "venue needs 30 minutes of setup and 30 minutes of turnaround around each event."
    )
    assert refusal.details["in_buffer"] is True
    assert refusal.details["booking_id"] == existing.id


@pytest.mark.parametrize(
    ("setup", "turnaround", "request_start"),
    [
        pytest.param(0, 0, _at(12), id="touching with no padding"),
        pytest.param(30, 30, _at(13), id="exactly the padding apart"),
    ],
)
def test_a_request_that_only_touches_the_padding_is_approved(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
    setup: int,
    turnaround: int,
    request_start: datetime,
) -> None:
    """The edges are free: periods that meet, or are exactly the padding apart."""
    venue = venue_with_buffers(setup, turnaround)
    confirmed_booking(venue, _at(9), _at(12))
    request = _request_for(venue, saved_event(), db_session, request_start, _at(15))

    decided = decide(request.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


# --------------------------------------------------------------------------
# Bookings that don't count
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("same_venue", "day", "status"),
    [
        pytest.param(False, 1, BookingStatus.CONFIRMED, id="another venue"),
        pytest.param(True, 2, BookingStatus.CONFIRMED, id="another day"),
        pytest.param(True, 1, BookingStatus.CANCELLED, id="a cancelled booking"),
    ],
)
def test_a_booking_that_is_elsewhere_or_cancelled_does_not_block_an_approval(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
    same_venue: bool,
    day: int,
    status: BookingStatus,
) -> None:
    venue = venue_with_buffers(0, 0)
    other_venue = venue_with_buffers(0, 0)
    booked_venue = venue if same_venue else other_venue
    confirmed_booking(booked_venue, _at(9, day=day), _at(12, day=day), status=status)
    request = _request_for(venue, saved_event(), db_session, _at(9), _at(12))

    decided = decide(request.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


# --------------------------------------------------------------------------
# The same event — conflicts are per venue
# --------------------------------------------------------------------------


def test_the_same_event_at_a_different_venue_never_conflicts(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """The conflict rule: one event can use two venues in the same period."""
    event = saved_event()
    auditorium = venue_with_buffers(0, 0)
    breakout = venue_with_buffers(0, 0)
    confirmed_booking(auditorium, _at(9), _at(12), event_id=event.id)
    request = _request_for(breakout, event, db_session, _at(9), _at(12))

    decided = decide(request.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


def test_the_same_event_at_the_same_venue_overlapping_does_conflict(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """The conflict rule: one event cannot book a venue twice for one period."""
    event = saved_event()
    venue = venue_with_buffers(0, 0)
    existing = confirmed_booking(venue, _at(9), _at(12), event_id=event.id)
    request = _request_for(venue, event, db_session, _at(11), _at(14))

    refusal = _refused_approval(request, db_session)

    assert refusal.details["booking_id"] == existing.id


# --------------------------------------------------------------------------
# Only an approval is checked
# --------------------------------------------------------------------------


def test_rejecting_a_clashing_request_is_not_refused(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """Rejection books nothing, so there is nothing for it to clash with."""
    venue = venue_with_buffers(0, 0)
    confirmed_booking(venue, _at(9), _at(12))
    request = _request_for(venue, saved_event(), db_session, _at(11), _at(14))

    decided = decide(request.id, "rejected", db_session, reason="The hall is taken")

    assert decided.status is BookingRequestStatus.REJECTED


# --------------------------------------------------------------------------
# Two simultaneous approvals — the venue row is locked
# --------------------------------------------------------------------------


def test_an_approval_locks_the_venue_row_before_checking_for_a_clash(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """Two approvals for one venue at once must queue, so the second sees the first.

    SQLite ignores ``FOR UPDATE``, so this cannot show the two really queue; it shows
    the venue is read under a lock, in the SQL Postgres is sent (ADR-0045).
    """
    venue = venue_with_buffers(0, 0)
    request = _request_for(venue, saved_event(), db_session, _at(9), _at(12))
    sent: list[str] = []

    def _record(connection: object, clause: object, *args: object) -> None:
        sent.append(str(clause.compile(dialect=postgresql.dialect())))  # type: ignore[attr-defined]

    sqlalchemy_event.listen(db_session.get_bind(), "before_execute", _record)
    try:
        decide(request.id, "approved", db_session)
    finally:
        sqlalchemy_event.remove(db_session.get_bind(), "before_execute", _record)

    locked_venue_reads = [sql for sql in sent if "FROM venues" in sql and "FOR UPDATE" in sql]
    assert len(locked_venue_reads) == 1
