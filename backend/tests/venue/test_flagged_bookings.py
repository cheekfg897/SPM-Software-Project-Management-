"""Unit tests for SCRUM-59 AC1, AC2 and AC9: flagged bookings in Venue Staff's queue.

A booking a change flagged (SCRUM-33 AC6, SCRUM-58) appears in Venue Staff's queue with
the reason it was flagged (AC1); one that needs an alternative venue is settled under
SCRUM-92, not here. Each one comes with what reconfirming it gives it by default
(ADR-0112):

* the period, moved by the amount the event's start moved since the booking's period
  was last set, however many edits that took (AC2), so a 14:00-15:00 breakout room on
  Monday becomes 14:00-15:00 on Tuesday; a change that didn't touch the timing leaves
  the period as it is;
* the expected occupancy, raised to the new attendance when the booking held the whole
  audience and the attendance outgrew it (AC9).

The services run against ``db_session``. The event is the ``saved_event`` fixture's:
approved, 80 attending, from 09:00 on 1 November 2026 to 17:30 the next day. The
Auditorium (capacity 100) is booked 09:00-12:00 for everyone; the Breakout room
(capacity 40) 13:00-16:00 for 30.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from app.modules.venue.schemas import FlaggedBookingAsShown, FlaggedBookingSchema
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    SavedEvent,
    approved_arrangement,
    at,
    block,
    decide,
    edit_event,
    raise_booking,
)

pytestmark = pytest.mark.scrum_59

TIMING_REASON = "The event's date or time changed."
#: Moves the event from Sunday 1 November to Monday 2 November, keeping its length.
NEXT_DAY = {"proposed_date": "2026-11-02", "end_date": "2026-11-03"}


def _flagged(session: Session) -> list[FlaggedBookingAsShown]:
    return services.list_flagged_bookings(session=session)


def _listed_ids(session: Session) -> list[int]:
    return [flagged.shown.request.id for flagged in _flagged(session)]


def _reconfirm_with(session: Session, request_id: int) -> tuple[datetime, datetime, int]:
    """What reconfirming the flagged booking gives it: (starts, ends, occupancy)."""
    for flagged in _flagged(session):
        if flagged.shown.request.id == request_id:
            reconfirmation = flagged.reconfirm_with
            return (
                reconfirmation.starts_at,
                reconfirmation.ends_at,
                reconfirmation.expected_occupancy,
            )
    raise AssertionError(f"booking {request_id} is not listed")


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


# --------------------------------------------------------------------------
# AC1 — a flagged booking appears in the queue with the reason it was flagged
# --------------------------------------------------------------------------


def test_nothing_is_listed_while_no_booking_is_flagged(
    db_session: Session, main_id: int, breakout_id: int
) -> None:
    assert _flagged(db_session) == []


def test_each_booking_a_change_flagged_is_listed_with_its_reasons(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    edit_event(db_session, event, {"end_time": "18:00", "expected_attendance": 90})

    flagged = _flagged(db_session)

    assert [entry.shown.request.id for entry in flagged] == [main_id, breakout_id]
    main_reasons = [flag.reason for flag in flagged[0].shown.request.reassessment_flags]
    assert main_reasons == [
        TIMING_REASON,
        "The event's expected attendance rose from 80 to 90,"
        " above this arrangement's expected occupancy of 80.",
    ]
    breakout_reasons = [flag.reason for flag in flagged[1].shown.request.reassessment_flags]
    assert breakout_reasons == [TIMING_REASON]


def test_a_booking_the_change_did_not_affect_is_left_out(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    """A rise in attendance flags only the booking that held everyone (SCRUM-58 AC5)."""
    edit_event(db_session, event, {"expected_attendance": 90})

    assert _listed_ids(db_session) == [main_id]


def test_a_flagged_request_venue_staff_have_not_decided_is_listed_too(
    db_session: Session, event: EventRequest, auditorium: Venue
) -> None:
    """AC10: a Pending request moves to the new period before it is decided."""
    pending = raise_booking(auditorium, event, db_session)

    edit_event(db_session, event, NEXT_DAY)

    assert _listed_ids(db_session) == [pending.id]


def test_a_booking_that_needs_an_alternative_venue_is_left_out(
    db_session: Session, event: EventRequest, auditorium: Venue, main_id: int, breakout_id: int
) -> None:
    """AC1: that flag clears only under SCRUM-92, so the booking isn't decided here."""
    edit_event(db_session, event, {"end_time": "18:00"})
    block(auditorium, at(10), at(11), db_session)

    assert _listed_ids(db_session) == [breakout_id]


def test_a_flagged_booking_that_was_rejected_is_left_out(
    db_session: Session, event: EventRequest, auditorium: Venue, breakout_id: int
) -> None:
    pending = raise_booking(auditorium, event, db_session)
    edit_event(db_session, event, {"end_time": "18:00"})

    decide(pending.id, "rejected", db_session, reason="Hall closed that week.")

    assert _listed_ids(db_session) == [breakout_id]


def test_the_earliest_event_is_listed_first(
    db_session: Session,
    saved_users: list[User],
    saved_event: SavedEvent,
    auditorium: Venue,
    breakout_room: Venue,
) -> None:
    later = saved_event()
    earlier = saved_event()
    earlier.start_time = time(8, 0)
    db_session.commit()
    later_id = approved_arrangement(auditorium, later, db_session)
    earlier_id = approved_arrangement(
        breakout_room, earlier, db_session, expected_occupancy=30, **SECOND_PERIOD
    )
    edit_event(db_session, later, {"end_time": "18:00"})
    edit_event(db_session, earlier, {"end_time": "18:00"})

    assert _listed_ids(db_session) == [earlier_id, later_id]


def test_the_listed_booking_dumps_with_what_reconfirming_gives_it(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    edit_event(db_session, event, NEXT_DAY)

    body = FlaggedBookingSchema().dump(_flagged(db_session), many=True)

    assert body[0]["booking"]["id"] == main_id
    assert body[0]["booking"]["flagged_after_change"] is True
    assert body[0]["booking"]["reassessment_flags"] == [
        {"kind": "requires_reconfirmation", "reason": TIMING_REASON}
    ]
    assert body[0]["reconfirm_with"] == {
        "starts_at": "2026-11-02T09:00:00+08:00",
        "ends_at": "2026-11-02T12:00:00+08:00",
        "expected_occupancy": 80,
    }


# --------------------------------------------------------------------------
# AC2 — the new period moves by the amount the event's start moved
# --------------------------------------------------------------------------


def test_a_date_change_moves_each_booking_to_the_same_times_on_the_new_day(
    db_session: Session, event: EventRequest, main_id: int, breakout_id: int
) -> None:
    edit_event(db_session, event, NEXT_DAY)

    assert _reconfirm_with(db_session, main_id) == (at(9, day=2), at(12, day=2), 80)
    assert _reconfirm_with(db_session, breakout_id) == (at(13, day=2), at(16, day=2), 30)


def test_a_later_start_time_moves_the_booking_by_as_much(
    db_session: Session, event: EventRequest, breakout_id: int
) -> None:
    edit_event(db_session, event, {"start_time": "10:30"})

    assert _reconfirm_with(db_session, breakout_id) == (at(14, 30), at(17, 30), 30)


def test_several_edits_move_the_booking_by_their_total(
    db_session: Session, event: EventRequest, breakout_id: int
) -> None:
    """Decision 1: the total since the period was set, whatever the number of edits."""
    edit_event(db_session, event, NEXT_DAY)
    edit_event(db_session, event, {"start_time": "10:00"})
    edit_event(db_session, event, {"start_time": "11:00"})

    assert _reconfirm_with(db_session, breakout_id) == (at(15, day=2), at(18, day=2), 30)


def test_an_edit_that_moves_the_start_back_again_leaves_the_period_as_it_was(
    db_session: Session, event: EventRequest, breakout_id: int
) -> None:
    edit_event(db_session, event, NEXT_DAY)
    edit_event(db_session, event, {"proposed_date": "2026-11-01", "end_date": "2026-11-02"})

    assert _reconfirm_with(db_session, breakout_id) == (at(13), at(16), 30)


@pytest.mark.parametrize(
    "payload",
    [{"end_time": "18:00"}, {"end_date": "2026-11-03"}, {"venue_requirements": "A stage."}],
    ids=["end-time", "end-date", "venue-requirements"],
)
def test_a_change_that_does_not_move_the_start_leaves_the_period_as_it_is(
    db_session: Session, event: EventRequest, breakout_id: int, payload: dict[str, str]
) -> None:
    edit_event(db_session, event, payload)

    assert _reconfirm_with(db_session, breakout_id) == (at(13), at(16), 30)


def test_a_booking_with_no_record_of_being_raised_moves_by_every_change_to_the_start(
    db_session: Session, event: EventRequest, auditorium: Venue, save: Callable[..., None]
) -> None:
    """A booking saved straight to the database has no record of being raised."""
    booking = VenueBookingRequest(
        event_id=event.id,
        venue_id=auditorium.id,
        requested_by=COORDINATOR_ID,
        starts_at=at(13),
        ends_at=at(14),
        purpose="Workshop",
        expected_occupancy=20,
        status=BookingRequestStatus.APPROVED,
    )
    save(booking)

    edit_event(db_session, event, NEXT_DAY)

    assert _reconfirm_with(db_session, booking.id) == (at(13, day=2), at(14, day=2), 20)


def test_the_period_moves_from_when_a_request_raised_after_an_earlier_edit_was_set(
    db_session: Session, event: EventRequest, auditorium: Venue
) -> None:
    """An edit before the request was raised has nothing to do with its period."""
    edit_event(db_session, event, {"start_time": "10:00"})
    pending = raise_booking(auditorium, event, db_session, starts_at=at(10).isoformat())

    edit_event(db_session, event, NEXT_DAY)

    assert _reconfirm_with(db_session, pending.id) == (at(10, day=2), at(12, day=2), 80)


# --------------------------------------------------------------------------
# AC9 — a booking that held everyone is reconfirmed for the new attendance
# --------------------------------------------------------------------------


@pytest.mark.parametrize("attendance", [90, 150], ids=["within-capacity", "over-capacity"])
def test_a_rise_the_booking_was_outgrown_by_raises_its_occupancy_to_the_new_attendance(
    db_session: Session, event: EventRequest, main_id: int, attendance: int
) -> None:
    edit_event(db_session, event, {"expected_attendance": attendance})

    assert _reconfirm_with(db_session, main_id) == (at(9), at(12), attendance)


def test_occupancy_follows_the_attendance_as_it_is_now_after_several_edits(
    db_session: Session, event: EventRequest, main_id: int
) -> None:
    """The first rise flagged it; the later ones add no flag but still count."""
    edit_event(db_session, event, {"expected_attendance": 90})
    edit_event(db_session, event, {"expected_attendance": 95})
    edit_event(db_session, event, {"expected_attendance": 85})

    assert _reconfirm_with(db_session, main_id) == (at(9), at(12), 85)


def test_a_booking_that_did_not_hold_everyone_keeps_its_occupancy(
    db_session: Session, event: EventRequest, breakout_id: int
) -> None:
    edit_event(db_session, event, {"end_time": "18:00", "expected_attendance": 150})

    assert _reconfirm_with(db_session, breakout_id) == (at(13), at(16), 30)


def test_a_booking_for_more_than_the_new_attendance_keeps_its_occupancy(
    db_session: Session, event: EventRequest, auditorium: Venue
) -> None:
    """Both sides of the threshold: 100 already covers a rise to 100."""
    roomy_id = approved_arrangement(auditorium, event, db_session, expected_occupancy=100)

    edit_event(db_session, event, {"end_time": "18:00", "expected_attendance": 100})

    assert _reconfirm_with(db_session, roomy_id) == (at(9), at(12), 100)
