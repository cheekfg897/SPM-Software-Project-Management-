"""Unit tests for SCRUM-59 AC5: Venue Staff reject a booking a change flagged.

Rejecting needs a reason (blank counts as missing). The venue becomes available for
that period again, the booking shows as Rejected, the event stays Approved and its
current coordinator is told, with the reason. A Rejected booking stays active and holds
back Safety Review until the coordinator withdraws it (SCRUM-93, SCRUM-97). Venue Staff
may reject any flagged booking, not only one that is no longer suitable (ADR-0112
decision 2), and a request they haven't decided is rejected as in SCRUM-43 (AC11).
Each booking is decided on its own (AC8).

The services run against ``db_session``. The event is the ``saved_event`` fixture's:
approved, 80 attending, from 09:00 on 1 November 2026. The Auditorium (capacity 100) is
booked 09:00-12:00 for everyone; the Breakout room (capacity 40) 13:00-16:00 for 30.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import SafetyReviewNotAllowedError, submit_for_safety_review
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue import services
from app.modules.venue.models import Booking, BookingRequestStatus, BookingStatus, Venue
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    approved_arrangement,
    at,
    block,
    decide,
    edit_event,
    flags_on,
    history_entries,
    locked_request_reads,
    raise_booking,
    reload_event,
    reload_request,
)

pytestmark = pytest.mark.scrum_59

TIMING_REASON = "The event's date or time changed."
CAPACITY_REASON = "Expected attendance of 150 exceeds the venue's capacity of 100."
REASON = "The hall is booked for exams that day."
#: The ``saved_users`` coordinator who isn't the event's, for a reassignment.
OTHER_COORDINATOR_ID = 9


def _reject(session: Session, request_id: int, reason: Any = REASON) -> None:
    """Reject the booking as Venue Staff; ``reason`` is left out when ``None``."""
    payload = {} if reason is None else {"reason": reason}
    services.reject_flagged_booking(
        request_id, payload, rejected_by=VENUE_STAFF_ID, session=session
    )


def _bookings_of(session: Session, venue: Venue) -> list[BookingStatus]:
    session.expire_all()
    stmt = select(Booking).where(Booking.venue_id == venue.id).order_by(Booking.id)
    return [booking.status for booking in session.scalars(stmt)]


def _rejected_notices(user_id: int) -> list[str | None]:
    rows = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is NotificationKind.VENUE_BOOKING_REJECTED:
            rows.append(notification.detail)
    return rows


@pytest.fixture()
def event(saved_users: list[User], saved_event: SavedEvent) -> EventRequest:
    """The approved event, 80 attending, with Venue Staff saved to be told."""
    return saved_event()


@pytest.fixture()
def main_id(db_session: Session, auditorium: Venue, event: EventRequest) -> int:
    """The approved Auditorium booking, 09:00-12:00, for the whole audience of 80."""
    return approved_arrangement(auditorium, event, db_session)


@pytest.fixture()
def breakout_id(db_session: Session, breakout_room: Venue, event: EventRequest) -> int:
    """The approved Breakout room booking, 13:00-16:00, for 30 of them."""
    return approved_arrangement(
        breakout_room, event, db_session, expected_occupancy=30, **SECOND_PERIOD
    )


@pytest.fixture()
def too_big(db_session: Session, event: EventRequest, main_id: int, breakout_id: int) -> None:
    """Attendance rises to 150, so the Auditorium is no longer suitable."""
    edit_event(db_session, event, {"end_time": "18:00", "expected_attendance": 150})


# --------------------------------------------------------------------------
# AC5 — rejecting frees the venue, and the booking shows as Rejected
# --------------------------------------------------------------------------


def test_rejecting_marks_the_booking_rejected_with_the_reason(
    db_session: Session, main_id: int, too_big: None
) -> None:
    _reject(db_session, main_id)

    rejected = reload_request(db_session, main_id)
    assert rejected.status is BookingRequestStatus.REJECTED
    assert rejected.decision_reason == REASON


def test_rejecting_frees_the_venue_for_that_period(
    db_session: Session,
    saved_event: SavedEvent,
    auditorium: Venue,
    main_id: int,
    too_big: None,
) -> None:
    _reject(db_session, main_id)

    assert _bookings_of(db_session, auditorium) == [BookingStatus.CANCELLED]
    other_event = saved_event()
    taken = raise_booking(auditorium, other_event, db_session)
    assert decide(taken.id, "approved", db_session).status is BookingRequestStatus.APPROVED


def test_the_flags_stay_as_the_record_of_why(
    db_session: Session, main_id: int, too_big: None
) -> None:
    _reject(db_session, main_id)

    assert flags_on(db_session, main_id) == [
        ("requires_reconfirmation", TIMING_REASON),
        ("no_longer_suitable", CAPACITY_REASON),
    ]
    assert reload_request(db_session, main_id).is_flagged_after_change is False


def test_the_event_stays_approved_and_its_current_coordinator_is_told_the_reason(
    db_session: Session, event: EventRequest, main_id: int, too_big: None
) -> None:
    event.coordinator_id = OTHER_COORDINATOR_ID
    db_session.commit()

    _reject(db_session, main_id)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert _rejected_notices(OTHER_COORDINATOR_ID) == [REASON]
    assert _rejected_notices(COORDINATOR_ID) == []


def test_the_events_history_records_the_rejection(
    db_session: Session, event: EventRequest, auditorium: Venue, main_id: int, too_big: None
) -> None:
    _reject(db_session, main_id)

    entry = history_entries(db_session, event.id)[-1]
    assert entry.kind is EventHistoryKind.VENUE_BOOKING_REJECTED
    assert entry.actor_id == VENUE_STAFF_ID
    assert entry.details == {
        "venue_booking_request_id": main_id,
        "venue_id": auditorium.id,
        "booking_id": None,
        "reason": REASON,
        "replaces_request_id": None,
    }


def test_a_rejected_booking_holds_the_event_back_until_the_coordinator_withdraws_it(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int, too_big: None
) -> None:
    _reject(db_session, main_id)
    _reject(db_session, breakout_id, reason="Room needed elsewhere.")

    with pytest.raises(SafetyReviewNotAllowedError) as excinfo:
        submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)
    assert excinfo.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {main_id} is rejected.",
            f"Venue arrangement {breakout_id} is rejected.",
        ]
    }

    services.withdraw_arrangement(
        event.reference, main_id, coordinator_id=COORDINATOR_ID, session=db_session
    )
    assert reload_request(db_session, main_id).status is BookingRequestStatus.WITHDRAWN


def test_a_booking_that_only_needs_reconfirming_may_be_rejected_too(
    db_session: Session, event: EventRequest, breakout_room: Venue, breakout_id: int
) -> None:
    """Decision 2: Venue Staff may reject any flagged booking, with a reason."""
    edit_event(db_session, event, {"end_time": "18:00"})

    _reject(db_session, breakout_id)

    assert reload_request(db_session, breakout_id).status is BookingRequestStatus.REJECTED
    assert _bookings_of(db_session, breakout_room) == [BookingStatus.CANCELLED]


def test_rejecting_one_booking_leaves_the_events_others_as_they_are(
    db_session: Session, breakout_room: Venue, main_id: int, breakout_id: int, too_big: None
) -> None:
    _reject(db_session, main_id)

    breakout = reload_request(db_session, breakout_id)
    assert breakout.status is BookingRequestStatus.APPROVED
    assert flags_on(db_session, breakout_id) == [("requires_reconfirmation", TIMING_REASON)]
    assert _bookings_of(db_session, breakout_room) == [BookingStatus.CONFIRMED]


@pytest.mark.parametrize("status", [BookingRequestStatus.PENDING, BookingRequestStatus.CONFLICTING])
def test_an_undecided_request_is_rejected_as_the_queue_rejects_one(
    db_session: Session, event: EventRequest, auditorium: Venue, status: BookingRequestStatus
) -> None:
    request = raise_booking(auditorium, event, db_session)
    reload_request(db_session, request.id).status = status
    db_session.commit()
    edit_event(db_session, event, {"end_time": "18:00"})

    _reject(db_session, request.id)

    assert reload_request(db_session, request.id).status is BookingRequestStatus.REJECTED
    assert _bookings_of(db_session, auditorium) == []
    assert _rejected_notices(COORDINATOR_ID) == [REASON]


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("reason", [None, "", "   "], ids=["missing", "empty", "spaces"])
def test_a_rejection_needs_a_reason(
    db_session: Session, main_id: int, too_big: None, reason: str | None
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _reject(db_session, main_id, reason=reason)

    assert excinfo.value.details == {
        "reason": ["A reason is required to reject a booking request."]
    }
    assert reload_request(db_session, main_id).status is BookingRequestStatus.APPROVED


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        (7, "Not a valid string."),
        (True, "Not a valid string."),
        (["Closed."], "Not a valid string."),
    ],
    ids=["number", "boolean", "list"],
)
def test_a_reason_that_is_not_text_is_refused(
    db_session: Session, main_id: int, too_big: None, reason: Any, message: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _reject(db_session, main_id, reason=reason)

    assert excinfo.value.details == {"reason": [message]}


def test_an_unknown_field_is_refused(db_session: Session, main_id: int, too_big: None) -> None:
    with pytest.raises(ValidationError) as excinfo:
        services.reject_flagged_booking(
            main_id,
            {"reason": REASON, "status": "rejected"},
            rejected_by=VENUE_STAFF_ID,
            session=db_session,
        )

    assert excinfo.value.details == {"status": ["Unknown field."]}


def test_an_unknown_booking_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        _reject(db_session, 404)


def test_a_booking_no_change_flagged_is_refused(db_session: Session, main_id: int) -> None:
    with pytest.raises(ConflictError) as excinfo:
        _reject(db_session, main_id)

    assert excinfo.value.message == (
        "This booking is not flagged after a change, so there is nothing to reconfirm or reject."
    )
    assert reload_request(db_session, main_id).status is BookingRequestStatus.APPROVED


def test_a_booking_already_rejected_is_refused_the_second_time(
    db_session: Session, main_id: int, too_big: None
) -> None:
    _reject(db_session, main_id)

    with pytest.raises(ConflictError):
        _reject(db_session, main_id)


def test_a_booking_that_needs_an_alternative_venue_is_refused(
    db_session: Session, auditorium: Venue, main_id: int, too_big: None
) -> None:
    block(auditorium, at(10), at(11), db_session)

    with pytest.raises(ConflictError) as excinfo:
        _reject(db_session, main_id)

    assert excinfo.value.message == (
        "This booking needs an alternative venue, which only a replacement settles."
    )


def test_the_booking_is_read_under_a_lock(db_session: Session, main_id: int, too_big: None) -> None:
    """ADR-0112 decision 7: two Venue Staff settling one booking take turns."""
    reads = locked_request_reads(db_session, lambda: _reject(db_session, main_id))

    assert len(reads) == 1
