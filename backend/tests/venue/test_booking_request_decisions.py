"""Unit tests for SCRUM-43 — Venue Staff approve or reject a venue booking request.

The queue is every Pending request, ordered by the date of the event it is for (AC1),
each beside its event's details (AC2). Approving creates the confirmed booking and
moves the request to Approved (AC3); rejecting needs a reason and books nothing. The
decision rides in one commit with the event's history entry, as raising one does
(ADR-0035). Holding a request is SCRUM-75, and refusing an overlap is SCRUM-44.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, time

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.permissions import Role
from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from app.modules.venue import services
from app.modules.venue.models import (
    Booking,
    BookingRequestStatus,
    BookingStatus,
    CalendarEntryKind,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    CANCEL_ALL_BODY,
    COORDINATOR_ID,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    decide,
    raise_booking,
    two_venues,
)

pytestmark = pytest.mark.scrum_43

NOVEMBER_FIRST = {
    "starts_at": "2026-11-01T09:00:00+08:00",
    "ends_at": "2026-11-01T12:00:00+08:00",
}


def _bookings(session: Session) -> list[Booking]:
    return list(session.scalars(select(Booking)))


def _queue_ids(session: Session) -> list[int]:
    return [shown.request.id for shown in services.list_pending_booking_requests(session=session)]


def test_the_queue_is_empty_when_no_request_is_waiting(db_session: Session) -> None:
    """What the Venue Staff page shows an empty state for."""
    assert services.list_pending_booking_requests(session=db_session) == []


def test_the_queue_shows_a_pending_request_beside_its_events_details(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC2: the event's timing and accessibility needs travel with the request."""
    event = saved_event()
    raise_booking(venue, event, db_session, expected_occupancy=90, required_layout="theatre")

    queue = services.list_pending_booking_requests(session=db_session)

    assert len(queue) == 1
    shown = queue[0]
    assert shown.request.purpose == "Main hall"
    assert shown.request.expected_occupancy == 90
    assert shown.request.required_layout == "theatre"
    assert shown.proposed_date == event.proposed_date
    assert shown.start_time == event.start_time
    assert shown.accessibility_needs == "Step-free entrance"


def test_the_queue_is_ordered_by_the_events_date_not_the_requests_period(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """AC1. The later event's request is for the earlier period, so the two disagree."""
    auditorium, breakout = two_venues(make_venue, save)
    later_event = saved_event(proposed_date=datetime(2026, 11, 5, tzinfo=UTC).date())
    earlier_event = saved_event(proposed_date=datetime(2026, 11, 1, tzinfo=UTC).date())
    for_later = raise_booking(auditorium, later_event, db_session, **NOVEMBER_FIRST)
    for_earlier = raise_booking(breakout, earlier_event, db_session, **SECOND_PERIOD)

    assert _queue_ids(db_session) == [for_earlier.id, for_later.id]


def test_events_on_the_same_day_are_ordered_by_start_time(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """AC1. The date decides first; the start time only breaks a tie on the date.

    The requests are raised in an order that matches neither sort key, so the queue can
    only come out right if it sorts by date and then by start time.
    """
    auditorium, breakout = two_venues(make_venue, save)
    afternoon_event = saved_event(start_time=time(14, 0))
    next_day_event = saved_event(proposed_date=datetime(2026, 11, 2, tzinfo=UTC).date())
    morning_event = saved_event(start_time=time(8, 0))
    # No two share a venue and period, so none is refused as a second Pending request.
    afternoon = raise_booking(auditorium, afternoon_event, db_session)
    next_day = raise_booking(breakout, next_day_event, db_session)
    morning = raise_booking(auditorium, morning_event, db_session, **SECOND_PERIOD)

    # With the date alone the raising order would survive: afternoon, morning, next day.
    assert _queue_ids(db_session) == [morning.id, afternoon.id, next_day.id]


def test_the_queue_leaves_out_requests_that_are_no_longer_pending(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """A decided or withdrawn request is not waiting for anyone (AC1)."""
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    approved = raise_booking(auditorium, event, db_session)
    still_pending = raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    decide(approved.id, "approved", db_session)

    assert _queue_ids(db_session) == [still_pending.id]


def test_approving_creates_a_confirmed_booking_for_the_requested_period(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """AC3."""
    event = saved_event()
    request = raise_booking(venue, event, db_session)

    decide(request.id, "approved", db_session)

    bookings = _bookings(db_session)
    assert len(bookings) == 1
    booking = bookings[0]
    assert booking.venue_id == venue.id
    assert booking.event_id == event.id
    assert booking.status is BookingStatus.CONFIRMED
    assert booking.start_time == request.starts_at
    assert booking.end_time == request.ends_at


def test_approving_moves_the_request_to_approved(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """AC3."""
    request = raise_booking(venue, saved_event(), db_session)

    decided = decide(request.id, "approved", db_session)

    assert decided.status is BookingRequestStatus.APPROVED


def test_an_approval_may_carry_a_reason_for_the_coordinator(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """AC6: the decision and any reason are visible on the request."""
    request = raise_booking(venue, saved_event(), db_session)

    decided = decide(request.id, "approved", db_session, reason="Stage is already set up")

    assert decided.decision_reason == "Stage is already set up"


def test_the_approved_booking_occupies_the_calendar_with_setup_and_turnaround(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """AC7: the venue is unavailable, padded by its buffers (ADR-0011)."""
    venue = make_venue(setup_minutes=30, turnaround_minutes=45)
    save(venue)
    request = raise_booking(venue, saved_event(), db_session)

    decide(request.id, "approved", db_session)

    entries = services.get_venue_calendar(
        venue.id,
        datetime(2026, 11, 1, tzinfo=UTC),
        datetime(2026, 11, 2, tzinfo=UTC),
        viewer_role=Role.VENUE_STAFF,
        session=db_session,
    )
    assert [entry.kind for entry in entries] == [CalendarEntryKind.CONFIRMED_BOOKING]
    assert entries[0].start_time == datetime(2026, 11, 1, 0, 30, tzinfo=UTC)
    assert entries[0].end_time == datetime(2026, 11, 1, 4, 45, tzinfo=UTC)


def test_rejecting_records_the_reason_and_books_nothing(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """AC3, AC6."""
    request = raise_booking(venue, saved_event(), db_session)

    decided = decide(request.id, "rejected", db_session, reason="Double-booked for maintenance")

    assert decided.status is BookingRequestStatus.REJECTED
    assert decided.decision_reason == "Double-booked for maintenance"
    assert _bookings(db_session) == []


def test_rejecting_without_a_reason_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The coordinator has to be told why, as a rejected event request is (ADR-0028)."""
    request = raise_booking(venue, saved_event(), db_session)

    with pytest.raises(ValidationError) as refusal:
        decide(request.id, "rejected", db_session)

    assert refusal.value.details == {"reason": [services.REJECTION_REASON_REQUIRED_MESSAGE]}
    assert db_session.get(services.VenueBookingRequest, request.id).status is (
        BookingRequestStatus.PENDING
    )


def test_an_outcome_that_is_neither_approved_nor_rejected_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """Holding is SCRUM-75; until then "on_hold" is not an outcome this route takes."""
    request = raise_booking(venue, saved_event(), db_session)

    with pytest.raises(ValidationError) as refusal:
        decide(request.id, "on_hold", db_session)

    assert "outcome" in refusal.value.details


def test_a_request_that_was_already_decided_cannot_be_decided_again(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """The booking is made once; changing a decision is not in this story's ACs."""
    request = raise_booking(venue, saved_event(), db_session)
    decide(request.id, "approved", db_session)

    with pytest.raises(ConflictError) as refusal:
        decide(request.id, "rejected", db_session, reason="Changed my mind")

    assert refusal.value.message == services.DECISION_NOT_PENDING_MESSAGE.format(status="approved")
    assert len(_bookings(db_session)) == 1


def test_the_locked_read_replaces_what_the_session_already_holds(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """Two Venue Staff deciding at once: the second must see the first's decision.

    A copy the session loaded before the lock was taken may be stale, so the locked read
    has to return the row as it is now (ADR-0037's seam, ADR-0042 decision 7).
    """
    request = raise_booking(venue, saved_event(), db_session)
    assert request.status is BookingRequestStatus.PENDING
    # synchronize_session=False leaves the session's copy Pending, as a stale copy is.
    decided_elsewhere = (
        update(VenueBookingRequest)
        .where(VenueBookingRequest.id == request.id)
        .values(status=BookingRequestStatus.APPROVED)
    )
    db_session.execute(decided_elsewhere, execution_options={"synchronize_session": False})
    assert request.status is BookingRequestStatus.PENDING

    with pytest.raises(ConflictError) as refusal:
        decide(request.id, "rejected", db_session, reason="Too late")

    assert refusal.value.message == services.DECISION_NOT_PENDING_MESSAGE.format(status="approved")


def test_a_request_that_does_not_exist_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as refusal:
        decide(404, "approved", db_session)

    assert refusal.value.message == services.BOOKING_REQUEST_NOT_FOUND_MESSAGE


def test_deciding_one_request_leaves_the_events_other_requests_alone(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """AC8: one venue's decision says nothing about the event's other venues."""
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    approved = raise_booking(auditorium, event, db_session)
    untouched = raise_booking(breakout, event, db_session, **SECOND_PERIOD)

    decide(approved.id, "approved", db_session)

    other = db_session.get(services.VenueBookingRequest, untouched.id)
    assert other.status is BookingRequestStatus.PENDING
    assert other.decision_reason is None
    assert [booking.venue_id for booking in _bookings(db_session)] == [auditorium.id]


def test_a_rejected_request_stays_an_active_arrangement_and_the_others_are_untouched(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """AC8 and AC9: a rejection stays on the event and changes nothing else.

    SCRUM-49 and SCRUM-97 hold the event back while any arrangement is not approved, so
    the rejected one must still count as active until the coordinator withdraws it.
    """
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    rejected = raise_booking(auditorium, event, db_session)
    untouched = raise_booking(breakout, event, db_session, **SECOND_PERIOD)

    decide(rejected.id, "rejected", db_session, reason="Closed for repairs")

    # list_active_arrangements puts the earlier period first, so the rejected one leads.
    active = services.list_active_arrangements(event.id, session=db_session)
    assert [(arrangement.id, arrangement.status) for arrangement in active] == [
        (rejected.id, BookingRequestStatus.REJECTED),
        (untouched.id, BookingRequestStatus.PENDING),
    ]
    assert untouched.decision_reason is None
    assert _bookings(db_session) == []


def _withdraw(event: EventRequest, arrangement_id: int, session: Session) -> VenueBookingRequest:
    """Withdraw one of the event's arrangements as its coordinator."""
    shown = services.withdraw_arrangement(
        event.reference, arrangement_id, coordinator_id=COORDINATOR_ID, session=session
    )
    return shown.request


def test_the_coordinator_can_withdraw_a_rejected_arrangement(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """AC9: the rejected arrangement holds the event back until it is withdrawn.

    Without this the event could never move on, because a rejection is final.
    """
    event = saved_event()
    request = raise_booking(venue, event, db_session)
    decide(request.id, "rejected", db_session, reason="Closed for repairs")

    withdrawn = _withdraw(event, request.id, db_session)

    assert withdrawn.status is BookingRequestStatus.WITHDRAWN
    assert services.count_active_arrangements(event.id, session=db_session) == 0


def test_cancelling_all_retires_a_rejected_arrangement_with_the_pending_ones(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """Cancel-all must not stop at a rejected arrangement, nor leave it behind."""
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    rejected = raise_booking(auditorium, event, db_session)
    pending = raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    decide(rejected.id, "rejected", db_session, reason="Closed for repairs")

    retired = services.cancel_all_arrangements(
        event.reference, CANCEL_ALL_BODY, coordinator_id=COORDINATOR_ID, session=db_session
    )

    assert [shown.request.id for shown in retired] == [rejected.id, pending.id]
    assert services.count_active_arrangements(event.id, session=db_session) == 0


def test_an_approved_arrangement_cannot_be_withdrawn(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    """Only a pending or rejected arrangement can be. An approval has made a booking.

    Cancelling an approved booking is not in SCRUM-43's ACs, so it stays refused.
    """
    event = saved_event()
    request = raise_booking(venue, event, db_session)
    decide(request.id, "approved", db_session)

    with pytest.raises(ConflictError) as refusal:
        _withdraw(event, request.id, db_session)

    assert refusal.value.message == services.WITHDRAW_NOT_ALLOWED_MESSAGE.format(status="approved")
    assert len(_bookings(db_session)) == 1


@pytest.mark.parametrize(
    ("outcome", "kind"),
    [
        ("approved", EventHistoryKind.VENUE_BOOKING_APPROVED),
        ("rejected", EventHistoryKind.VENUE_BOOKING_REJECTED),
    ],
)
def test_the_decision_is_recorded_in_the_events_history(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    saved_users: list[object],
    outcome: str,
    kind: EventHistoryKind,
) -> None:
    """Traceable on the event, as raising the request is (ADR-0035 decision 8)."""
    request = raise_booking(venue, saved_event(), db_session)

    decide(request.id, outcome, db_session, reason="As agreed with the organiser")

    entries = list(db_session.scalars(select(EventHistoryEntry).order_by(EventHistoryEntry.id)))
    assert [entry.kind for entry in entries] == [EventHistoryKind.VENUE_BOOKING_REQUESTED, kind]
    assert entries[-1].actor_id == VENUE_STAFF_ID
    assert entries[-1].details["venue_booking_request_id"] == request.id
    assert entries[-1].details["venue_id"] == venue.id
    assert entries[-1].details["reason"] == "As agreed with the organiser"
