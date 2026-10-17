"""Unit tests for SCRUM-44's hold clauses — an active hold counts as a clash.

A tentative hold occupies its venue like a confirmed booking, setup and turnaround
included, so it refuses an overlapping approval or hold; an expired hold does not
(ADR-0045). A hold is placed on the first request of the ``multi_venue_request``
fixture, 09:00-12:00 at an auditorium; another event's request or booking is then set
against it. Whether the hold itself is accepted is in ``test_tentative_holds.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.venue.models import (
    Booking,
    BookingRequestStatus,
    BookingStatus,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    SaveBooking,
    SavedEvent,
    at,
    decide,
    hours_from_now,
    locked_venue_reads,
    period,
    place_hold,
    raise_booking,
)

pytestmark = pytest.mark.scrum_44


def _venue_of(request: VenueBookingRequest, session: Session) -> Venue:
    return session.get(Venue, request.venue_id)


def _hold_booking(request: VenueBookingRequest, session: Session) -> Booking:
    session.expire_all()
    return session.get(VenueBookingRequest, request.id).booking


def _add_padding(
    venue: Venue, save: Callable[..., None], setup_minutes: int, turnaround_minutes: int
) -> None:
    venue.setup_minutes = setup_minutes
    venue.turnaround_minutes = turnaround_minutes
    save(venue)


def _other_event_request(
    held: VenueBookingRequest,
    session: Session,
    saved_event: SavedEvent,
    start: datetime,
    end: datetime,
) -> VenueBookingRequest:
    """Another event's Pending request at the venue the hold is on."""
    return raise_booking(_venue_of(held, session), saved_event(), session, **period(start, end))


def _refused(action: Callable[[], object]) -> ConflictError:
    with pytest.raises(ConflictError) as refusal:
        action()
    return refusal.value


# --------------------------------------------------------------------------
# An active hold refuses an overlapping approval
# --------------------------------------------------------------------------


def test_an_approval_overlapping_an_active_hold_is_refused_and_names_the_hold(
    db_session: Session, multi_venue_request: VenueBookingRequest, saved_event: SavedEvent
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    other = _other_event_request(multi_venue_request, db_session, saved_event, at(11), at(14))

    refusal = _refused(lambda: decide(other.id, "approved", db_session))

    hold = _hold_booking(multi_venue_request, db_session)
    assert refusal.status_code == 409
    assert refusal.details["booking_id"] == hold.id
    assert db_session.get(VenueBookingRequest, other.id).status is BookingRequestStatus.PENDING


def test_an_approval_inside_a_holds_setup_and_turnaround_is_refused(
    db_session: Session,
    save: Callable[..., None],
    multi_venue_request: VenueBookingRequest,
    saved_event: SavedEvent,
) -> None:
    """The hold occupies 08:30-12:30, so a request from 12:15 is too close."""
    _add_padding(_venue_of(multi_venue_request, db_session), save, 30, 30)
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    other = _other_event_request(multi_venue_request, db_session, saved_event, at(12, 15), at(15))

    refusal = _refused(lambda: decide(other.id, "approved", db_session))

    assert refusal.details["in_buffer"] is True


def test_an_expired_hold_does_not_block_an_approval(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    saved_event: SavedEvent,
    tentative_hold: SaveBooking,
) -> None:
    venue = _venue_of(multi_venue_request, db_session)
    tentative_hold(venue, at(9), at(12), hold_expires_at=hours_from_now(-1))
    other = _other_event_request(multi_venue_request, db_session, saved_event, at(11), at(14))

    decided = decide(other.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


@pytest.mark.parametrize(
    ("same_venue", "day"),
    [
        pytest.param(False, 1, id="another venue"),
        pytest.param(True, 2, id="another day"),
    ],
)
def test_a_hold_elsewhere_does_not_block_an_approval(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    saved_event: SavedEvent,
    tentative_hold: SaveBooking,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    same_venue: bool,
    day: int,
) -> None:
    other_venue = make_venue(name="Elsewhere")
    save(other_venue)
    venue = _venue_of(multi_venue_request, db_session) if same_venue else other_venue
    tentative_hold(venue, at(9, day=day), at(12, day=day))
    other = _other_event_request(multi_venue_request, db_session, saved_event, at(9), at(12))

    decided = decide(other.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


# --------------------------------------------------------------------------
# A hold is checked as an approval is
# --------------------------------------------------------------------------


def test_a_hold_overlapping_a_confirmed_booking_is_refused_and_saves_nothing(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    confirmed_booking: SaveBooking,
) -> None:
    venue = _venue_of(multi_venue_request, db_session)
    existing = confirmed_booking(venue, at(11), at(14))

    refusal = _refused(lambda: place_hold(multi_venue_request.id, hours_from_now(48), db_session))

    assert refusal.details["booking_id"] == existing.id
    assert db_session.query(Booking).all() == [existing]
    assert db_session.get(VenueBookingRequest, multi_venue_request.id).status is (
        BookingRequestStatus.PENDING
    )


def test_a_hold_inside_a_confirmed_bookings_setup_and_turnaround_is_refused(
    db_session: Session,
    save: Callable[..., None],
    multi_venue_request: VenueBookingRequest,
    confirmed_booking: SaveBooking,
) -> None:
    """The booking occupies 11:45-15:30 with its padding, which reaches 12:00."""
    venue = _venue_of(multi_venue_request, db_session)
    _add_padding(venue, save, 30, 30)
    confirmed_booking(venue, at(12, 15), at(15))

    refusal = _refused(lambda: place_hold(multi_venue_request.id, hours_from_now(48), db_session))

    assert refusal.details["in_buffer"] is True


def test_a_hold_overlapping_another_active_hold_is_refused_and_names_it(
    db_session: Session, multi_venue_request: VenueBookingRequest, tentative_hold: SaveBooking
) -> None:
    other_hold = tentative_hold(_venue_of(multi_venue_request, db_session), at(11), at(14))

    refusal = _refused(lambda: place_hold(multi_venue_request.id, hours_from_now(48), db_session))

    assert refusal.details["booking_id"] == other_hold.id


def test_a_hold_may_overlap_an_expired_hold(
    db_session: Session, multi_venue_request: VenueBookingRequest, tentative_hold: SaveBooking
) -> None:
    tentative_hold(
        _venue_of(multi_venue_request, db_session),
        at(11),
        at(14),
        hold_expires_at=hours_from_now(-1),
    )

    held = place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    assert held.status is BookingRequestStatus.ON_HOLD


def test_a_cancelled_booking_does_not_block_a_hold(
    db_session: Session, multi_venue_request: VenueBookingRequest, confirmed_booking: SaveBooking
) -> None:
    confirmed_booking(
        _venue_of(multi_venue_request, db_session),
        at(11),
        at(14),
        status=BookingStatus.CANCELLED,
    )

    held = place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    assert held.status is BookingRequestStatus.ON_HOLD


def test_a_hold_that_ends_as_the_approval_starts_does_not_block_it(
    db_session: Session, multi_venue_request: VenueBookingRequest, saved_event: SavedEvent
) -> None:
    """With no setup or turnaround, a hold to 12:00 leaves the venue free from 12:00."""
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    other = _other_event_request(multi_venue_request, db_session, saved_event, at(12), at(14))

    decided = decide(other.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


# --------------------------------------------------------------------------
# A hold stops counting at the instant it expires, decided when it is read
# --------------------------------------------------------------------------


def test_a_hold_still_blocks_an_approval_just_before_it_expires(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    saved_event: SavedEvent,
    tentative_hold: SaveBooking,
    pin_now: Callable[[datetime], None],
) -> None:
    expires_at = hours_from_now(1)
    hold = tentative_hold(
        _venue_of(multi_venue_request, db_session), at(9), at(12), hold_expires_at=expires_at
    )
    other = _other_event_request(multi_venue_request, db_session, saved_event, at(11), at(14))
    pin_now(expires_at - timedelta(microseconds=1))

    refusal = _refused(lambda: decide(other.id, "approved", db_session))

    assert refusal.details["booking_id"] == hold.id


@pytest.mark.parametrize(
    "after_expiry",
    [
        pytest.param(timedelta(0), id="at the expiry"),
        pytest.param(timedelta(microseconds=1), id="just after the expiry"),
    ],
)
def test_a_hold_no_longer_blocks_an_approval_from_the_instant_it_expires(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    saved_event: SavedEvent,
    tentative_hold: SaveBooking,
    pin_now: Callable[[datetime], None],
    after_expiry: timedelta,
) -> None:
    expires_at = hours_from_now(1)
    tentative_hold(
        _venue_of(multi_venue_request, db_session), at(9), at(12), hold_expires_at=expires_at
    )
    other = _other_event_request(multi_venue_request, db_session, saved_event, at(11), at(14))
    pin_now(expires_at + after_expiry)

    decided = decide(other.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


# --------------------------------------------------------------------------
# A hold and an approval at one venue take turns — the venue row is locked
# --------------------------------------------------------------------------


@pytest.mark.scrum_75
def test_placing_a_hold_locks_the_venue_row_before_checking_for_a_clash(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    """A hold and an approval for one venue at once must queue, as two approvals do."""
    reads = locked_venue_reads(
        db_session, lambda: place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    )

    assert len(reads) == 1
