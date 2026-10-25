"""Unit tests for SCRUM-49 AC10 — releasing an event's venues when it is rejected.

When the assigned coordinator rejects an event during planning, its venue bookings and
holds are released, as for a cancelled event (SCRUM-61 AC3, AC8, ADR-0093).
``release_event_arrangements`` does the venue module's part without committing: an
arrangement Venue Staff haven't approved is withdrawn as the coordinator would withdraw
it (SCRUM-93), and one that holds the venue, Approved or On Hold, is Released with its
booking or hold cancelled. Each one released is named, for Venue Staff to be told
(the Product Owner's answer of 25 Oct, ADR-0103). Runs against ``db_session``, so the
queries really run.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    BookingStatus,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    COORDINATOR_ID,
    SavedEvent,
    bookings,
    decide,
    history_entries,
    hours_from_now,
    place_hold,
    raise_booking,
    reload_request,
)

pytestmark = pytest.mark.scrum_49

#: Arrangements Venue Staff haven't approved, which are withdrawn (SCRUM-93 AC6).
WITHDRAWN_STATUSES = [
    BookingRequestStatus.PENDING,
    BookingRequestStatus.CONFLICTING,
    BookingRequestStatus.REJECTED,
    BookingRequestStatus.EXPIRED,
]
#: Arrangements already out of the event's venues, which are left as they are.
RETIRED_STATUSES = [BookingRequestStatus.WITHDRAWN, BookingRequestStatus.RELEASED]


def _release(event: EventRequest, session: Session) -> list[str]:
    released = services.release_event_arrangements(
        event.id, coordinator_id=COORDINATOR_ID, session=session
    )
    session.commit()
    return released


def _arrangement_in(
    status: BookingRequestStatus, venue: Venue, event: EventRequest, session: Session
) -> VenueBookingRequest:
    """An arrangement of the event's at ``venue``, put straight into ``status``."""
    arrangement = raise_booking(venue, event, session)
    arrangement.status = status
    session.commit()
    return arrangement


def _history_kinds(session: Session, event: EventRequest) -> list[EventHistoryKind]:
    return [entry.kind for entry in history_entries(session, event.id)]


@pytest.fixture()
def event(saved_event: SavedEvent) -> EventRequest:
    """An approved event of coordinator 3's."""
    return saved_event()


# --------------------------------------------------------------------------
# An arrangement Venue Staff haven't approved is withdrawn
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", WITHDRAWN_STATUSES, ids=lambda status: status.value)
def test_an_unapproved_arrangement_is_withdrawn_and_written_to_the_history(
    db_session: Session, event: EventRequest, venue: Venue, status: BookingRequestStatus
) -> None:
    arrangement = _arrangement_in(status, venue, event, db_session)

    _release(event, db_session)

    assert reload_request(db_session, arrangement.id).status is BookingRequestStatus.WITHDRAWN
    withdrawal = history_entries(db_session, event.id)[-1]
    assert (withdrawal.kind, withdrawal.actor_id, withdrawal.details) == (
        EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN,
        COORDINATOR_ID,
        {"venue_booking_request_id": arrangement.id, "venue_id": arrangement.venue_id},
    )


# --------------------------------------------------------------------------
# An arrangement that holds the venue is Released, and the venue is free again
# --------------------------------------------------------------------------


def test_an_approved_arrangement_is_released_and_its_booking_cancelled(
    db_session: Session, event: EventRequest, venue: Venue
) -> None:
    arrangement = raise_booking(venue, event, db_session)
    decide(arrangement.id, "approved", db_session)
    assert [status for _, status in bookings(db_session)] == [BookingStatus.CONFIRMED]

    _release(event, db_session)

    assert reload_request(db_session, arrangement.id).status is BookingRequestStatus.RELEASED
    assert [status for _, status in bookings(db_session)] == [BookingStatus.CANCELLED]


def test_a_hold_is_released_and_cancelled(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(24), db_session)

    _release(multi_venue_event, db_session)

    released = reload_request(db_session, multi_venue_request.id)
    assert released.status is BookingRequestStatus.RELEASED
    assert released.booking is not None
    assert released.booking.status is BookingStatus.CANCELLED


def test_a_booking_made_from_a_hold_is_cancelled_too(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    """SCRUM-75 AC7: the final approval turns the hold into the booking."""
    place_hold(multi_venue_request.id, hours_from_now(24), db_session)
    decide(multi_venue_request.id, "approved", db_session)

    _release(multi_venue_event, db_session)

    released = reload_request(db_session, multi_venue_request.id)
    assert released.status is BookingRequestStatus.RELEASED
    assert released.booking is not None
    assert released.booking.status is BookingStatus.CANCELLED


def test_the_venue_is_free_for_the_period_again(
    db_session: Session, event: EventRequest, venue: Venue, saved_event: SavedEvent
) -> None:
    """SCRUM-61 AC3: another event can now be booked into the released period."""
    arrangement = raise_booking(venue, event, db_session)
    decide(arrangement.id, "approved", db_session)
    other_event = saved_event()
    waiting = raise_booking(venue, other_event, db_session)

    _release(event, db_session)

    assert decide(waiting.id, "approved", db_session).status is BookingRequestStatus.APPROVED


def test_an_approved_arrangement_whose_booking_is_gone_is_still_released(
    db_session: Session, event: EventRequest, venue: Venue
) -> None:
    arrangement = _arrangement_in(BookingRequestStatus.APPROVED, venue, event, db_session)

    _release(event, db_session)

    assert reload_request(db_session, arrangement.id).status is BookingRequestStatus.RELEASED
    assert bookings(db_session) == []


def test_a_release_writes_no_withdrawal_to_the_history(
    db_session: Session, event: EventRequest, venue: Venue
) -> None:
    """The rejection's own entry says why; the arrangement was never withdrawn."""
    arrangement = raise_booking(venue, event, db_session)
    decide(arrangement.id, "approved", db_session)
    kinds_before = _history_kinds(db_session, event)

    _release(event, db_session)

    assert _history_kinds(db_session, event) == kinds_before


# --------------------------------------------------------------------------
# ADR-0103 — each booking or hold released is named for Venue Staff
# --------------------------------------------------------------------------


def test_a_released_booking_is_named_with_its_venue_and_period(
    db_session: Session, event: EventRequest, venue: Venue
) -> None:
    arrangement = raise_booking(venue, event, db_session)
    decide(arrangement.id, "approved", db_session)

    released = _release(event, db_session)

    assert released == [
        f"Venue arrangement {arrangement.id} at Main Hall, 2026-11-01 09:00 to"
        " 2026-11-01 12:00, was released."
    ]


def test_a_released_hold_is_named_and_the_withdrawn_request_beside_it_is_not(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    """The multi-venue event's other request is only Pending, so it is withdrawn."""
    place_hold(multi_venue_request.id, hours_from_now(24), db_session)

    released = _release(multi_venue_event, db_session)

    assert released == [
        f"Venue arrangement {multi_venue_request.id} at Auditorium, 2026-11-01 09:00 to"
        " 2026-11-01 12:00, was released."
    ]


@pytest.mark.parametrize(
    "status", [*WITHDRAWN_STATUSES, *RETIRED_STATUSES], ids=lambda status: status.value
)
def test_an_arrangement_withdrawn_or_already_retired_is_not_named(
    db_session: Session, event: EventRequest, venue: Venue, status: BookingRequestStatus
) -> None:
    _arrangement_in(status, venue, event, db_session)

    assert _release(event, db_session) == []


def test_another_events_booking_is_not_named(
    db_session: Session, event: EventRequest, venue: Venue, saved_event: SavedEvent
) -> None:
    other_event = saved_event()
    decide(raise_booking(venue, other_event, db_session).id, "approved", db_session)

    assert _release(event, db_session) == []


# --------------------------------------------------------------------------
# What is left alone, and what is not saved
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", RETIRED_STATUSES, ids=lambda status: status.value)
def test_an_arrangement_already_retired_is_left_as_it_is(
    db_session: Session, event: EventRequest, venue: Venue, status: BookingRequestStatus
) -> None:
    arrangement = _arrangement_in(status, venue, event, db_session)
    kinds_before = _history_kinds(db_session, event)

    _release(event, db_session)

    assert reload_request(db_session, arrangement.id).status is status
    assert _history_kinds(db_session, event) == kinds_before


def test_another_events_arrangements_are_left_alone(
    db_session: Session, event: EventRequest, venue: Venue, saved_event: SavedEvent
) -> None:
    other_event = saved_event()
    theirs = _arrangement_in(BookingRequestStatus.PENDING, venue, other_event, db_session)

    _release(event, db_session)

    assert reload_request(db_session, theirs.id).status is BookingRequestStatus.PENDING


def test_nothing_is_saved_until_the_caller_commits(
    db_session: Session, event: EventRequest, venue: Venue
) -> None:
    """The rejection commits the release with its own status change (ADR-0093)."""
    pending = _arrangement_in(BookingRequestStatus.PENDING, venue, event, db_session)
    approved = raise_booking(
        venue,
        event,
        db_session,
        starts_at="2026-11-01T13:00:00+08:00",
        ends_at="2026-11-01T16:00:00+08:00",
    )
    decide(approved.id, "approved", db_session)
    kinds_before = _history_kinds(db_session, event)

    services.release_event_arrangements(event.id, coordinator_id=COORDINATOR_ID, session=db_session)
    db_session.rollback()

    assert reload_request(db_session, pending.id).status is BookingRequestStatus.PENDING
    assert reload_request(db_session, approved.id).status is BookingRequestStatus.APPROVED
    assert [status for _, status in bookings(db_session)] == [BookingStatus.CONFIRMED]
    assert _history_kinds(db_session, event) == kinds_before
