"""Unit tests for SCRUM-59: Venue Staff reconfirm a booking a change flagged.

Reconfirming moves the booking to the new period, which must lie within the event's
new start and end (AC2), and is refused, naming the conflict, when the period with the
venue's setup and turnaround runs into another booking or a live hold, falls outside
the venue's hours, overlaps a block or overlaps another of the event's arrangements at
the venue (AC3). A venue too small for the booking's occupancy needs a reason (AC4).
It is refused while a replacement is waiting for a decision (AC6). Each booking is
reconfirmed on its own (AC8), its preparation details are kept (AC9), a booking that
held everyone is raised to the new attendance (AC10), and a request Venue Staff
haven't decided is only moved (AC11). The flags clear, the event's history records it
and the event's coordinator is told (AC2, ADR-0112).

The services run against ``db_session``. The event is the ``saved_event`` fixture's:
approved, 80 attending, from 09:00 on 1 November 2026 to 17:30 the next day. The
Auditorium (capacity 100) is booked 09:00-12:00 for everyone; the Breakout room
(capacity 40) 13:00-16:00 for 30.
"""

from __future__ import annotations

from datetime import datetime
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
from app.modules.venue.models import (
    Booking,
    BookingRequestStatus,
    BookingStatus,
    PreparationStatus,
    ReassessmentFlag,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SaveBooking,
    SavedEvent,
    VenueWithBuffers,
    approved_arrangement,
    at,
    block,
    decide,
    edit_event,
    flags_on,
    history_entries,
    hours_from_now,
    locked_request_reads,
    locked_venue_reads,
    raise_booking,
    reload_event,
    reload_request,
)

pytestmark = pytest.mark.scrum_59

TIMING_REASON = "The event's date or time changed."
#: Moves the event from Sunday 1 November to Monday 2 November, keeping its length.
NEXT_DAY = {"proposed_date": "2026-11-02", "end_date": "2026-11-03"}
#: The statuses in which a flag is open (ADR-0094 decision 2), written out so the test
#: doesn't copy the code's own list.
LIVE_STATUSES = [
    BookingRequestStatus.PENDING,
    BookingRequestStatus.CONFLICTING,
    BookingRequestStatus.APPROVED,
]
#: Every other status, built from the enum so a status added later is checked too.
NOT_LIVE_STATUSES = [status for status in BookingRequestStatus if status not in LIVE_STATUSES]
#: The ``saved_users`` coordinator who isn't the event's, for a reassignment.
OTHER_COORDINATOR_ID = 9
CAPACITY_REASON = (
    "A reason is required because the venue's capacity of 100 is below the booking's"
    " expected occupancy of 150."
)


def _payload(starts: datetime, ends: datetime, reason: Any = None) -> dict[str, Any]:
    """A reconfirmation body for ``starts``-``ends``, and ``reason`` if one is given."""
    payload: dict[str, Any] = {"starts_at": starts.isoformat(), "ends_at": ends.isoformat()}
    if reason is not None:
        payload["reason"] = reason
    return payload


def _reconfirm(
    session: Session, request_id: int, starts: datetime, ends: datetime, reason: Any = None
) -> VenueBookingRequest:
    """Reconfirm the booking for ``starts``-``ends`` as Venue Staff."""
    shown = services.reconfirm_flagged_booking(
        request_id, _payload(starts, ends, reason), reconfirmed_by=VENUE_STAFF_ID, session=session
    )
    return shown.request


def _reconfirm_as_listed(
    session: Session, request_id: int, reason: Any = None
) -> VenueBookingRequest:
    """Reconfirm the booking for the period the queue pre-fills (AC2)."""
    for flagged in services.list_flagged_bookings(session=session):
        if flagged.shown.request.id == request_id:
            period = flagged.reconfirm_with
            return _reconfirm(session, request_id, period.starts_at, period.ends_at, reason)
    raise AssertionError(f"booking {request_id} is not listed")


def _period(session: Session, request_id: int) -> tuple[datetime, datetime]:
    request = reload_request(session, request_id)
    return request.starts_at, request.ends_at


def _booking_of(session: Session, event: EventRequest, venue: Venue) -> Booking:
    """The event's one booking at ``venue``."""
    session.expire_all()
    stmt = select(Booking).where(Booking.event_id == event.id, Booking.venue_id == venue.id)
    return session.scalars(stmt).one()


def _refused_while_replacement_waits(
    session: Session, request_id: int, replacement_id: int
) -> None:
    """Reconfirming the booking is refused, naming the replacement that waits (AC6)."""
    with pytest.raises(ConflictError) as excinfo:
        _reconfirm_as_listed(session, request_id)
    assert excinfo.value.message == (
        f"Cannot reconfirm: replacement request #{replacement_id} for this booking is still"
        " waiting for a decision."
    )


def _reconfirmed_notices(user_id: int) -> list[str | None]:
    rows = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is NotificationKind.VENUE_BOOKING_RECONFIRMED:
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
def moved(db_session: Session, event: EventRequest, main_id: int, breakout_id: int) -> None:
    """The event moved to the next day, which flags both bookings."""
    edit_event(db_session, event, NEXT_DAY)


@pytest.fixture()
def buffered(
    db_session: Session, event: EventRequest, venue_with_buffers: VenueWithBuffers
) -> tuple[Venue, int]:
    """A venue with 30 minutes of setup and 30 of turnaround, and the booking there.

    The booking is approved for 10:00-12:00, and the move to the next day flagged it.
    """
    venue = venue_with_buffers(30, 30)
    request_id = approved_arrangement(venue, event, db_session, starts_at=at(10).isoformat())
    edit_event(db_session, event, NEXT_DAY)
    return venue, request_id


@pytest.fixture()
def replacement(
    db_session: Session, event: EventRequest, breakout_room: Venue, main_id: int, moved: None
) -> VenueBookingRequest:
    """A Pending replacement for the Auditorium booking, at the Breakout room."""
    return raise_booking(
        breakout_room,
        event,
        db_session,
        replaces_request_id=main_id,
        expected_occupancy=30,
        starts_at=at(9, day=2).isoformat(),
        ends_at=at(12, day=2).isoformat(),
    )


# --------------------------------------------------------------------------
# AC2 — reconfirming moves the booking to the new period
# --------------------------------------------------------------------------


def test_reconfirming_moves_the_booking_and_its_venue_booking_to_the_new_period(
    db_session: Session, event: EventRequest, auditorium: Venue, main_id: int, moved: None
) -> None:
    reconfirmed = _reconfirm_as_listed(db_session, main_id)

    assert reconfirmed.status is BookingRequestStatus.APPROVED
    assert _period(db_session, main_id) == (at(9, day=2), at(12, day=2))
    booking = _booking_of(db_session, event, auditorium)
    assert (booking.start_time, booking.end_time) == (at(9, day=2), at(12, day=2))
    assert booking.status is BookingStatus.CONFIRMED


def test_reconfirming_clears_the_bookings_flags(
    db_session: Session, main_id: int, moved: None
) -> None:
    _reconfirm_as_listed(db_session, main_id)

    assert flags_on(db_session, main_id) == []
    assert reload_request(db_session, main_id).is_flagged_after_change is False
    flag_rows = db_session.scalars(
        select(ReassessmentFlag).where(ReassessmentFlag.booking_request_id == main_id)
    ).all()
    assert flag_rows == []


def test_venue_staff_may_adjust_the_period_within_the_event(
    db_session: Session, main_id: int, moved: None
) -> None:
    _reconfirm(db_session, main_id, at(14, day=3), at(17, day=3))

    assert _period(db_session, main_id) == (at(14, day=3), at(17, day=3))


@pytest.mark.parametrize(
    ("starts", "ends"),
    [(at(9, day=2), at(10, day=2)), (at(16, 30, day=3), at(17, 30, day=3))],
    ids=["at-the-event-start", "at-the-event-end"],
)
def test_a_period_that_starts_or_ends_with_the_event_is_within_it(
    db_session: Session, main_id: int, moved: None, starts: datetime, ends: datetime
) -> None:
    _reconfirm(db_session, main_id, starts, ends)

    assert _period(db_session, main_id) == (starts, ends)


def test_a_period_that_starts_before_the_event_is_refused(
    db_session: Session, main_id: int, moved: None
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _reconfirm(db_session, main_id, at(9), at(12))

    assert excinfo.value.status_code == 400
    assert excinfo.value.details == {
        "starts_at": [
            "The period must lie within the event's start and end:"
            " 2026-11-02 09:00 to 2026-11-03 17:30."
        ]
    }
    assert _period(db_session, main_id) == (at(9), at(12))
    assert flags_on(db_session, main_id) == [("requires_reconfirmation", TIMING_REASON)]


def test_a_period_that_ends_after_the_event_is_refused(
    db_session: Session, main_id: int, moved: None
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _reconfirm(db_session, main_id, at(16, 30, day=3), at(17, 31, day=3))

    assert excinfo.value.details == {
        "ends_at": [
            "The period must lie within the event's start and end:"
            " 2026-11-02 09:00 to 2026-11-03 17:30."
        ]
    }


def test_a_change_that_did_not_touch_the_timing_keeps_the_period_and_clears_the_flag(
    db_session: Session, event: EventRequest, breakout_id: int
) -> None:
    edit_event(db_session, event, {"venue_requirements": "A stage."})

    _reconfirm_as_listed(db_session, breakout_id)

    assert _period(db_session, breakout_id) == (at(13), at(16))
    assert flags_on(db_session, breakout_id) == []


@pytest.mark.parametrize(
    ("starts", "ends", "field"),
    [(at(14), at(16), "starts_at"), (at(13), at(15), "ends_at")],
    ids=["new-start", "new-end"],
)
def test_a_period_the_change_did_not_retime_cannot_be_adjusted(
    db_session: Session,
    event: EventRequest,
    breakout_id: int,
    starts: datetime,
    ends: datetime,
    field: str,
) -> None:
    """AC2: Venue Staff adjust the period only to apply a change to its timing (A75)."""
    edit_event(db_session, event, {"venue_requirements": "A stage."})

    with pytest.raises(ValidationError) as excinfo:
        _reconfirm(db_session, breakout_id, starts, ends)

    assert excinfo.value.details == {
        field: [
            "The event's date and times haven't changed, so the booking keeps its period:"
            " 2026-11-01 13:00 to 2026-11-01 16:00."
        ]
    }
    assert _period(db_session, breakout_id) == (at(13), at(16))


def test_a_change_to_the_events_end_alone_lets_the_period_be_adjusted(
    db_session: Session, event: EventRequest, breakout_id: int
) -> None:
    """The event now ends at 15:00, so the 13:00-16:00 booking has to move to fit it."""
    edit_event(db_session, event, {"end_date": "2026-11-01", "end_time": "15:00"})

    _reconfirm(db_session, breakout_id, at(12), at(15))

    assert _period(db_session, breakout_id) == (at(12), at(15))


def test_the_coordinator_is_told_of_the_new_period(
    db_session: Session, main_id: int, moved: None
) -> None:
    _reconfirm_as_listed(db_session, main_id)

    assert _reconfirmed_notices(COORDINATOR_ID) == [
        f"Venue arrangement {main_id} at Auditorium is reconfirmed for 2026-11-02 09:00 to"
        " 2026-11-02 12:00."
    ]


def test_the_events_current_coordinator_is_told_not_the_one_who_raised_it(
    db_session: Session, event: EventRequest, main_id: int, moved: None
) -> None:
    event.coordinator_id = OTHER_COORDINATOR_ID
    db_session.commit()

    _reconfirm_as_listed(db_session, main_id)

    assert len(_reconfirmed_notices(OTHER_COORDINATOR_ID)) == 1
    assert _reconfirmed_notices(COORDINATOR_ID) == []


def test_the_events_history_records_the_reconfirmation(
    db_session: Session, event: EventRequest, auditorium: Venue, main_id: int, moved: None
) -> None:
    _reconfirm_as_listed(db_session, main_id)

    entry = history_entries(db_session, event.id)[-1]
    assert entry.kind is EventHistoryKind.VENUE_BOOKING_RECONFIRMED
    assert entry.actor_id == VENUE_STAFF_ID
    assert entry.details == {
        "venue_booking_request_id": main_id,
        "venue_id": auditorium.id,
        "status": "approved",
        "previous_starts_at": "2026-11-01T01:00:00+00:00",
        "previous_ends_at": "2026-11-01T04:00:00+00:00",
        "starts_at": "2026-11-02T01:00:00+00:00",
        "ends_at": "2026-11-02T04:00:00+00:00",
        "previous_expected_occupancy": 80,
        "expected_occupancy": 80,
        "reason": None,
        "flags": [{"kind": "requires_reconfirmation", "reason": TIMING_REASON}],
    }


def test_the_next_reconfirmation_moves_from_the_reconfirmed_period(
    db_session: Session, event: EventRequest, main_id: int, moved: None
) -> None:
    """A reconfirmation sets the period, so a later change moves it from there."""
    _reconfirm(db_session, main_id, at(14, day=2), at(16, day=2))
    edit_event(db_session, event, {"start_time": "10:00"})

    _reconfirm_as_listed(db_session, main_id)

    assert _period(db_session, main_id) == (at(15, day=2), at(17, day=2))


def test_a_reconfirmed_booking_no_longer_holds_the_event_back(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int, moved: None
) -> None:
    """AC7's gate (SCRUM-97) clears once each flagged booking is decided."""
    _reconfirm_as_listed(db_session, main_id)
    _reconfirm_as_listed(db_session, breakout_id)

    submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.SAFETY_REVIEW


def test_a_booking_that_is_still_flagged_holds_the_event_back(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int, moved: None
) -> None:
    _reconfirm_as_listed(db_session, main_id)

    with pytest.raises(SafetyReviewNotAllowedError) as excinfo:
        submit_for_safety_review(COORDINATOR_ID, event.reference, session=db_session)

    assert excinfo.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {breakout_id} is flagged (requires reconfirmation): {TIMING_REASON}"
        ]
    }


# --------------------------------------------------------------------------
# AC3 — a period that conflicts is refused, naming the conflict
# --------------------------------------------------------------------------


def test_a_period_that_runs_into_another_booking_is_refused_naming_it(
    db_session: Session,
    auditorium: Venue,
    confirmed_booking: SaveBooking,
    main_id: int,
    moved: None,
) -> None:
    other = confirmed_booking(auditorium, at(11, day=2), at(13, day=2), event_id=99)

    with pytest.raises(ConflictError) as excinfo:
        _reconfirm_as_listed(db_session, main_id)

    assert excinfo.value.status_code == 409
    assert excinfo.value.message == (
        f"Cannot reconfirm: booking #{other.id} holds this venue from 2026-11-02 11:00 to"
        " 2026-11-02 13:00, setup and turnaround included."
    )
    assert excinfo.value.details == {"booking_id": other.id}
    assert _period(db_session, main_id) == (at(9), at(12))
    assert flags_on(db_session, main_id) == [("requires_reconfirmation", TIMING_REASON)]


@pytest.mark.parametrize(
    ("ends_at", "clashes"),
    [(at(12, day=2), False), (at(12, 1, day=2), True)],
    ids=["setup-and-turnaround-fit", "one-minute-too-close"],
)
def test_the_venues_setup_and_turnaround_count_towards_a_clash(
    db_session: Session,
    buffered: tuple[Venue, int],
    confirmed_booking: SaveBooking,
    ends_at: datetime,
    clashes: bool,
) -> None:
    """30 minutes of turnaround and 30 of setup must fit before the 13:00 booking."""
    venue, request_id = buffered
    confirmed_booking(venue, at(13, day=2), at(14, day=2), event_id=99)

    if clashes:
        with pytest.raises(ConflictError):
            _reconfirm(db_session, request_id, at(10, day=2), ends_at)
    else:
        _reconfirm(db_session, request_id, at(10, day=2), ends_at)
        assert _period(db_session, request_id) == (at(10, day=2), ends_at)


def test_a_live_hold_conflicts_but_one_that_has_expired_does_not(
    db_session: Session,
    auditorium: Venue,
    tentative_hold: SaveBooking,
    main_id: int,
    moved: None,
) -> None:
    hold = tentative_hold(auditorium, at(9, day=2), at(10, day=2))
    with pytest.raises(ConflictError):
        _reconfirm_as_listed(db_session, main_id)

    hold.hold_expires_at = hours_from_now(-1)
    db_session.commit()
    _reconfirm_as_listed(db_session, main_id)

    assert _period(db_session, main_id) == (at(9, day=2), at(12, day=2))


def test_the_booking_never_conflicts_with_itself(
    db_session: Session, event: EventRequest, auditorium: Venue, main_id: int
) -> None:
    edit_event(db_session, event, {"end_time": "18:00"})

    _reconfirm_as_listed(db_session, main_id)

    assert _period(db_session, main_id) == (at(9), at(12))
    assert _booking_of(db_session, event, auditorium).start_time == at(9)


def test_a_period_outside_the_venues_hours_is_refused(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    """The venue opens at 09:00 every day; the event now starts at 07:00."""
    edit_event(db_session, event, {"start_time": "07:00"})

    with pytest.raises(ValidationError) as excinfo:
        _reconfirm_as_listed(db_session, main_id)

    assert excinfo.value.details == {
        "starts_at": [
            "The request falls outside the venue's operating hours."
            " The venue is open 09:00-18:00 on Sunday."
        ]
    }


def test_a_period_that_overlaps_a_block_is_refused_naming_it(
    db_session: Session, auditorium: Venue, main_id: int, moved: None
) -> None:
    block(auditorium, at(11, day=2), at(15, day=2), db_session)

    with pytest.raises(ConflictError) as excinfo:
        _reconfirm_as_listed(db_session, main_id)

    assert excinfo.value.message == (
        "Cannot reconfirm: the venue is blocked from 2026-11-02 11:00 to 2026-11-02 15:00"
        " (maintenance)."
    )


def test_the_venues_turnaround_counts_towards_a_block(
    db_session: Session, buffered: tuple[Venue, int]
) -> None:
    """A block isn't padded, so only the 30 minutes of turnaround must fit before it."""
    venue, request_id = buffered
    block(venue, at(13, day=2), at(14, day=2), db_session)

    with pytest.raises(ConflictError) as excinfo:
        _reconfirm(db_session, request_id, at(10, day=2), at(12, 31, day=2))
    assert excinfo.value.message == (
        "Cannot reconfirm: the venue is blocked from 2026-11-02 13:00 to 2026-11-02 14:00"
        " (maintenance)."
    )

    _reconfirm(db_session, request_id, at(10, day=2), at(12, 30, day=2))
    assert _period(db_session, request_id) == (at(10, day=2), at(12, 30, day=2))


def test_a_period_that_overlaps_another_of_the_events_arrangements_at_the_venue_is_refused(
    db_session: Session, event: EventRequest, auditorium: Venue, main_id: int, moved: None
) -> None:
    other = raise_booking(
        auditorium,
        event,
        db_session,
        starts_at=at(11, day=2).isoformat(),
        ends_at=at(13, day=2).isoformat(),
    )

    with pytest.raises(ConflictError) as excinfo:
        _reconfirm_as_listed(db_session, main_id)

    assert excinfo.value.message == (
        f"Cannot reconfirm: the new period overlaps venue arrangement #{other.id} of the"
        " same event at this venue."
    )


def test_the_venues_setup_and_turnaround_count_towards_the_events_other_arrangements(
    db_session: Session, event: EventRequest, buffered: tuple[Venue, int]
) -> None:
    """30 minutes of turnaround and 30 of setup must fit before the 13:00 request.

    The request is Pending, so it has no booking of its own for the clash check to find.
    """
    venue, request_id = buffered
    other = raise_booking(
        venue,
        event,
        db_session,
        starts_at=at(13, day=2).isoformat(),
        ends_at=at(14, day=2).isoformat(),
    )

    with pytest.raises(ConflictError) as excinfo:
        _reconfirm(db_session, request_id, at(10, day=2), at(12, 1, day=2))
    assert excinfo.value.message == (
        f"Cannot reconfirm: the new period overlaps venue arrangement #{other.id} of the"
        " same event at this venue."
    )

    _reconfirm(db_session, request_id, at(10, day=2), at(12, day=2))
    assert _period(db_session, request_id) == (at(10, day=2), at(12, day=2))


def test_the_events_arrangements_at_other_venues_do_not_conflict(
    db_session: Session, main_id: int, breakout_id: int, moved: None
) -> None:
    _reconfirm(db_session, main_id, at(13, day=2), at(16, day=2))

    assert _period(db_session, main_id) == (at(13, day=2), at(16, day=2))


def test_another_pending_request_the_new_period_clashes_with_is_marked_conflicting(
    db_session: Session,
    saved_event: SavedEvent,
    auditorium: Venue,
    main_id: int,
    moved: None,
) -> None:
    """Reconfirming books the new period, as approving does (SCRUM-44)."""
    other_event = saved_event(proposed_date=at(9, day=2).date())
    waiting = raise_booking(
        auditorium,
        other_event,
        db_session,
        starts_at=at(11, day=2).isoformat(),
        ends_at=at(13, day=2).isoformat(),
    )

    _reconfirm_as_listed(db_session, main_id)

    assert reload_request(db_session, waiting.id).status is BookingRequestStatus.CONFLICTING


def test_the_venue_is_read_under_a_lock_while_the_period_is_checked(
    db_session: Session, main_id: int, moved: None
) -> None:
    """ADR-0045: two reconfirmations or approvals at one venue take turns."""
    reads = locked_venue_reads(db_session, lambda: _reconfirm_as_listed(db_session, main_id))

    assert len(reads) == 1


def test_the_booking_is_read_under_a_lock(db_session: Session, main_id: int, moved: None) -> None:
    """ADR-0112 decision 7: two Venue Staff settling one booking take turns."""
    reads = locked_request_reads(db_session, lambda: _reconfirm_as_listed(db_session, main_id))

    assert len(reads) == 1


# --------------------------------------------------------------------------
# AC4 and AC10 — capacity, against the booking's own occupancy
# --------------------------------------------------------------------------


def test_a_booking_that_held_everyone_is_raised_to_the_new_attendance(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    edit_event(db_session, event, {"expected_attendance": 90})

    _reconfirm_as_listed(db_session, main_id)

    assert reload_request(db_session, main_id).expected_occupancy == 90


def test_a_venue_too_small_for_the_new_attendance_needs_a_reason(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    edit_event(db_session, event, {"expected_attendance": 150})

    with pytest.raises(ValidationError) as excinfo:
        _reconfirm_as_listed(db_session, main_id)

    assert excinfo.value.details == {"reason": [CAPACITY_REASON]}
    assert reload_request(db_session, main_id).expected_occupancy == 80


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
def test_a_blank_reason_counts_as_missing(
    db_session: Session, event: EventRequest, main_id: int, blank: str
) -> None:
    edit_event(db_session, event, {"expected_attendance": 150})

    with pytest.raises(ValidationError) as excinfo:
        _reconfirm_as_listed(db_session, main_id, reason=blank)

    assert excinfo.value.details == {"reason": [CAPACITY_REASON]}


def test_with_a_reason_a_venue_too_small_is_reconfirmed_and_the_reason_shown(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    edit_event(db_session, event, {"expected_attendance": 150})

    _reconfirm_as_listed(db_session, main_id, reason="  Standing room agreed.  ")

    reconfirmed = reload_request(db_session, main_id)
    assert reconfirmed.expected_occupancy == 150
    assert reconfirmed.decision_reason == "Standing room agreed."
    assert _reconfirmed_notices(COORDINATOR_ID) == [
        f"Venue arrangement {main_id} at Auditorium is reconfirmed for 2026-11-01 09:00 to"
        " 2026-11-01 12:00. Expected occupancy is now 150. Reason: Standing room agreed."
    ]


def test_a_venue_that_holds_exactly_the_occupancy_needs_no_reason(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    edit_event(db_session, event, {"expected_attendance": 100})

    _reconfirm_as_listed(db_session, main_id)

    assert reload_request(db_session, main_id).expected_occupancy == 100


def test_without_a_reason_the_previous_decision_reason_is_kept(
    db_session: Session, event: EventRequest, auditorium: Venue
) -> None:
    request = raise_booking(auditorium, event, db_session)
    decide(request.id, "approved", db_session, reason="Booked as asked.")
    edit_event(db_session, event, NEXT_DAY)

    _reconfirm_as_listed(db_session, request.id)

    assert reload_request(db_session, request.id).decision_reason == "Booked as asked."


def test_a_breakout_room_keeps_its_occupancy_whatever_the_attendance(
    db_session: Session, event: EventRequest, breakout_id: int
) -> None:
    edit_event(db_session, event, {"end_time": "18:00", "expected_attendance": 150})

    _reconfirm_as_listed(db_session, breakout_id)

    assert reload_request(db_session, breakout_id).expected_occupancy == 30


# --------------------------------------------------------------------------
# AC6, AC8 and AC9 — what else reconfirming leaves alone, or waits for
# --------------------------------------------------------------------------


def test_reconfirming_waits_while_a_replacement_for_the_booking_is_pending(
    db_session: Session, main_id: int, replacement: VenueBookingRequest
) -> None:
    _refused_while_replacement_waits(db_session, main_id, replacement.id)

    decide(replacement.id, "rejected", db_session, reason="Room taken.")
    _reconfirm_as_listed(db_session, main_id)

    assert _period(db_session, main_id) == (at(9, day=2), at(12, day=2))


@pytest.mark.parametrize(
    "status",
    [BookingRequestStatus.CONFLICTING, BookingRequestStatus.ON_HOLD],
    ids=lambda status: status.value,
)
def test_reconfirming_waits_while_a_replacement_is_conflicting_or_on_hold_too(
    db_session: Session,
    main_id: int,
    replacement: VenueBookingRequest,
    status: BookingRequestStatus,
) -> None:
    """Both still wait for Venue Staff's decision (ADR-0112 decision 8)."""
    replacement.status = status
    db_session.commit()

    _refused_while_replacement_waits(db_session, main_id, replacement.id)


def test_reconfirming_one_booking_leaves_the_events_others_flagged(
    db_session: Session, main_id: int, breakout_id: int, moved: None
) -> None:
    _reconfirm_as_listed(db_session, main_id)

    assert _period(db_session, breakout_id) == (at(13), at(16))
    assert flags_on(db_session, breakout_id) == [("requires_reconfirmation", TIMING_REASON)]


def test_the_bookings_preparation_details_are_kept(
    db_session: Session, main_id: int, moved: None
) -> None:
    request = reload_request(db_session, main_id)
    request.preparation_status = PreparationStatus.IN_PROGRESS
    request.preparation_notes = "Chairs ordered."
    db_session.commit()

    _reconfirm_as_listed(db_session, main_id)

    kept = reload_request(db_session, main_id)
    assert kept.preparation_status is PreparationStatus.IN_PROGRESS
    assert kept.preparation_notes == "Chairs ordered."


# --------------------------------------------------------------------------
# AC11 — a request Venue Staff haven't decided is moved, not approved
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [BookingRequestStatus.PENDING, BookingRequestStatus.CONFLICTING])
def test_an_undecided_request_moves_to_the_new_period_and_waits_to_be_decided(
    db_session: Session, event: EventRequest, auditorium: Venue, status: BookingRequestStatus
) -> None:
    """Moved clear of every booking, a Conflicting request no longer clashes."""
    request = raise_booking(auditorium, event, db_session)
    reload_request(db_session, request.id).status = status
    db_session.commit()
    edit_event(db_session, event, NEXT_DAY)

    _reconfirm_as_listed(db_session, request.id)

    moved_request = reload_request(db_session, request.id)
    assert moved_request.status is BookingRequestStatus.PENDING
    assert (moved_request.starts_at, moved_request.ends_at) == (at(9, day=2), at(12, day=2))
    assert flags_on(db_session, request.id) == []
    assert db_session.scalars(select(Booking)).all() == []
    assert _reconfirmed_notices(COORDINATOR_ID) == [
        f"Venue arrangement {request.id} at Auditorium moved to 2026-11-02 09:00 to"
        " 2026-11-02 12:00 and waits for Venue Staff's decision."
    ]


def test_a_moved_request_is_then_approved_through_the_queue(
    db_session: Session, event: EventRequest, auditorium: Venue
) -> None:
    request = raise_booking(auditorium, event, db_session)
    edit_event(db_session, event, NEXT_DAY)
    _reconfirm_as_listed(db_session, request.id)

    decide(request.id, "approved", db_session)

    booking = _booking_of(db_session, event, auditorium)
    assert (booking.start_time, booking.end_time) == (at(9, day=2), at(12, day=2))


# --------------------------------------------------------------------------
# Refusals — what can't be reconfirmed here, and what the payload must hold
# --------------------------------------------------------------------------


def test_an_unknown_booking_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as excinfo:
        _reconfirm(db_session, 404, at(9), at(12))

    assert excinfo.value.message == "Booking request not found."


def test_a_booking_no_change_flagged_is_refused(db_session: Session, main_id: int) -> None:
    with pytest.raises(ConflictError) as excinfo:
        _reconfirm(db_session, main_id, at(9), at(12))

    assert excinfo.value.message == (
        "This booking is not flagged after a change, so there is nothing to reconfirm or reject."
    )


def test_a_booking_already_reconfirmed_is_refused_the_second_time(
    db_session: Session, main_id: int, moved: None
) -> None:
    _reconfirm_as_listed(db_session, main_id)

    with pytest.raises(ConflictError):
        _reconfirm(db_session, main_id, at(9, day=2), at(12, day=2))


@pytest.mark.parametrize("status", NOT_LIVE_STATUSES, ids=lambda status: status.value)
def test_a_flagged_arrangement_that_is_no_longer_live_is_refused(
    db_session: Session, main_id: int, moved: None, status: BookingRequestStatus
) -> None:
    """Its flags stay as the record of why (ADR-0094 decision 2), but are not open."""
    reload_request(db_session, main_id).status = status
    db_session.commit()

    with pytest.raises(ConflictError):
        _reconfirm(db_session, main_id, at(9, day=2), at(12, day=2))


def test_a_booking_that_needs_an_alternative_venue_is_refused(
    db_session: Session, auditorium: Venue, main_id: int, moved: None
) -> None:
    block(auditorium, at(10), at(11), db_session)

    with pytest.raises(ConflictError) as excinfo:
        _reconfirm(db_session, main_id, at(9, day=2), at(12, day=2))

    assert excinfo.value.message == (
        "This booking needs an alternative venue, which only a replacement settles."
    )


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        (
            {"ends_at": "2026-11-02T12:00:00+08:00"},
            {"starts_at": ["Missing data for required field."]},
        ),
        (
            {"starts_at": "2026-11-02T09:00:00+08:00"},
            {"ends_at": ["Missing data for required field."]},
        ),
        (
            {"starts_at": "2026-11-02T12:00:00+08:00", "ends_at": "2026-11-02T09:00:00+08:00"},
            {"ends_at": ["ends_at must be after starts_at."]},
        ),
        (
            {
                "starts_at": "2026-11-02T09:00:00+08:00",
                "ends_at": "2026-11-02T12:00:00+08:00",
                "status": "approved",
            },
            {"status": ["Unknown field."]},
        ),
        (
            {
                "starts_at": "2026-11-02T09:00:00+08:00",
                "ends_at": "2026-11-02T12:00:00+08:00",
                "reason": 7,
            },
            {"reason": ["Not a valid string."]},
        ),
        (
            {
                "starts_at": "2026-11-02T09:00:00+08:00",
                "ends_at": "2026-11-02T12:00:00+08:00",
                "reason": True,
            },
            {"reason": ["Not a valid string."]},
        ),
        (
            {
                "starts_at": "2026-11-02T09:00:00+08:00",
                "ends_at": "2026-11-02T12:00:00+08:00",
                "reason": ["A"],
            },
            {"reason": ["Not a valid string."]},
        ),
        (
            {"starts_at": "Monday", "ends_at": "2026-11-02T12:00:00+08:00"},
            {"starts_at": ["Not a valid datetime."]},
        ),
    ],
    ids=[
        "no-start",
        "no-end",
        "ends-first",
        "unknown-field",
        "number-reason",
        "boolean-reason",
        "list-reason",
        "not-a-datetime",
    ],
)
def test_an_invalid_payload_is_refused_per_field(
    db_session: Session,
    main_id: int,
    moved: None,
    payload: dict[str, Any],
    details: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        services.reconfirm_flagged_booking(
            main_id, payload, reconfirmed_by=VENUE_STAFF_ID, session=db_session
        )

    assert excinfo.value.details == details


def test_a_body_that_is_not_an_object_is_refused(
    db_session: Session, main_id: int, moved: None
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        services.reconfirm_flagged_booking(
            main_id, None, reconfirmed_by=VENUE_STAFF_ID, session=db_session
        )

    assert excinfo.value.message == "Request body must be a JSON object."
