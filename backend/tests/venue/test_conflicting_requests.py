"""Unit tests for SCRUM-44 slice B — an approval marks the requests it clashes with.

When Venue Staff approve a request, every other Pending request at the same venue that
clashes with it, setup and turnaround included, becomes Conflicting before it can be
approved (AC5, ADR-0045). Raising a request marks nothing. Conflicts are per venue,
whatever the event (AC8). Venue Staff can still reject a Conflicting request.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from tests.venue.conftest import (
    COORDINATOR_ID,
    SavedEvent,
    VenueWithBuffers,
    at,
    decide,
    period,
    raise_booking,
)

pytestmark = pytest.mark.scrum_44

PENDING = BookingRequestStatus.PENDING
CONFLICTING = BookingRequestStatus.CONFLICTING


def _request_for(
    venue: Venue, event: EventRequest, session: Session, start: datetime, end: datetime
) -> VenueBookingRequest:
    return raise_booking(venue, event, session, **period(start, end))


# --------------------------------------------------------------------------
# AC5 — approving one request marks the Pending requests that clash with it
# --------------------------------------------------------------------------


def test_raising_overlapping_requests_marks_neither(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = venue_with_buffers(0, 0)

    first = _request_for(venue, saved_event(), db_session, at(9), at(12))
    second = _request_for(venue, saved_event(), db_session, at(11), at(14))

    assert (first.status, second.status) == (PENDING, PENDING)


def test_approving_a_request_marks_the_pending_requests_that_overlap_it(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = venue_with_buffers(0, 0)
    first = _request_for(venue, saved_event(), db_session, at(9), at(12))
    overlapping = _request_for(venue, saved_event(), db_session, at(11), at(14))
    also_overlapping = _request_for(venue, saved_event(), db_session, at(9), at(10))

    decide(first.id, "approved", db_session)

    assert first.status is BookingRequestStatus.APPROVED
    assert (overlapping.status, also_overlapping.status) == (CONFLICTING, CONFLICTING)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (at(9), at(11), PENDING),
        (at(9), at(11, 15), CONFLICTING),
        (at(15), at(17), PENDING),
        (at(14, 45), at(16), CONFLICTING),
    ],
    ids=[
        "ends-as-the-padding-starts",
        "ends-inside-the-padding",
        "starts-as-the-padding-ends",
        "starts-inside-the-padding",
    ],
)
def test_the_venues_setup_and_turnaround_decide_whether_requests_clash(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
    start: datetime,
    end: datetime,
    expected: BookingRequestStatus,
) -> None:
    """With 30 and 30 minutes, 12:00-14:00 needs an hour clear on each side."""
    venue = venue_with_buffers(30, 30)
    approved = _request_for(venue, saved_event(), db_session, at(12), at(14))
    other = _request_for(venue, saved_event(), db_session, start, end)

    decide(approved.id, "approved", db_session)

    assert other.status is expected


def test_a_request_at_another_venue_is_not_marked(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue, other_venue = venue_with_buffers(0, 0), venue_with_buffers(0, 0)
    approved = _request_for(venue, saved_event(), db_session, at(9), at(12))
    other = _request_for(other_venue, saved_event(), db_session, at(9), at(12))

    decide(approved.id, "approved", db_session)

    assert other.status is PENDING


def test_a_request_on_another_day_is_not_marked(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = venue_with_buffers(0, 0)
    approved = _request_for(venue, saved_event(), db_session, at(9), at(12))
    other = _request_for(venue, saved_event(), db_session, at(9, day=2), at(12, day=2))

    decide(approved.id, "approved", db_session)

    assert other.status is PENDING


def test_a_request_that_is_not_pending_is_not_marked(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = venue_with_buffers(0, 0)
    approved = _request_for(venue, saved_event(), db_session, at(9), at(12))
    rejected = _request_for(venue, saved_event(), db_session, at(11), at(14))
    decide(rejected.id, "rejected", db_session, reason="Closed that afternoon")

    decide(approved.id, "approved", db_session)

    assert rejected.status is BookingRequestStatus.REJECTED


def test_rejecting_a_request_leaves_the_ones_it_overlaps_pending(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    venue = venue_with_buffers(0, 0)
    first = _request_for(venue, saved_event(), db_session, at(9), at(12))
    second = _request_for(venue, saved_event(), db_session, at(11), at(14))

    decide(first.id, "rejected", db_session, reason="Not this venue")

    assert second.status is PENDING


def test_a_refused_approval_marks_nothing(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    """11:00-14:00 clashes with the booking 09:00-12:00 makes; it can't be approved."""
    venue = venue_with_buffers(0, 0)
    first = _request_for(venue, saved_event(), db_session, at(9), at(12))
    clashing = _request_for(venue, saved_event(), db_session, at(11), at(14))
    third = _request_for(venue, saved_event(), db_session, at(13), at(16))
    decide(first.id, "approved", db_session)
    assert (clashing.status, third.status) == (CONFLICTING, PENDING)

    with pytest.raises(ConflictError):
        decide(clashing.id, "approved", db_session)

    assert third.status is PENDING


# --------------------------------------------------------------------------
# AC8 — conflicts are per venue: one event at two venues never conflicts, one event
# twice at the same venue does
# --------------------------------------------------------------------------


def test_one_event_at_two_venues_over_the_same_period_does_not_conflict(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    event = saved_event()
    venue, other_venue = venue_with_buffers(0, 0), venue_with_buffers(0, 0)
    first = _request_for(venue, event, db_session, at(9), at(12))
    second = _request_for(other_venue, event, db_session, at(9), at(12))

    decide(first.id, "approved", db_session)

    assert second.status is PENDING


def test_one_event_twice_at_a_venue_over_overlapping_periods_conflicts(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> None:
    event = saved_event()
    venue = venue_with_buffers(0, 0)
    first = _request_for(venue, event, db_session, at(9), at(12))
    second = _request_for(venue, event, db_session, at(11), at(14))

    decide(first.id, "approved", db_session)

    assert second.status is CONFLICTING


# --------------------------------------------------------------------------
# ADR-0045 — a Conflicting request stays in the queue; Venue Staff can reject it and the
# coordinator can withdraw it, but approving it is still refused by the clash check
# --------------------------------------------------------------------------


@pytest.fixture()
def conflicting_pair(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    saved_users: list[object],
) -> tuple[VenueBookingRequest, VenueBookingRequest, EventRequest]:
    """An approved request, the Conflicting one it made, and that one's event."""
    venue = venue_with_buffers(0, 0)
    approved = _request_for(venue, saved_event(), db_session, at(9), at(12))
    event = saved_event()
    conflicting = _request_for(venue, event, db_session, at(11), at(14))
    decide(approved.id, "approved", db_session)
    assert conflicting.status is CONFLICTING
    return approved, conflicting, event


def test_a_conflicting_request_is_in_the_venue_staff_queue(
    db_session: Session,
    conflicting_pair: tuple[VenueBookingRequest, VenueBookingRequest, EventRequest],
) -> None:
    _, conflicting, _ = conflicting_pair

    queue = services.list_pending_booking_requests(session=db_session)

    assert [(shown.request.id, shown.request.status) for shown in queue] == [
        (conflicting.id, CONFLICTING)
    ]


def test_venue_staff_can_reject_a_conflicting_request(
    db_session: Session,
    conflicting_pair: tuple[VenueBookingRequest, VenueBookingRequest, EventRequest],
) -> None:
    _, conflicting, _ = conflicting_pair

    rejected = decide(conflicting.id, "rejected", db_session, reason="Clashes with another event")

    assert rejected.status is BookingRequestStatus.REJECTED


def test_approving_a_conflicting_request_is_still_refused_by_the_clash_check(
    db_session: Session,
    conflicting_pair: tuple[VenueBookingRequest, VenueBookingRequest, EventRequest],
) -> None:
    _, conflicting, _ = conflicting_pair

    with pytest.raises(ConflictError) as refusal:
        decide(conflicting.id, "approved", db_session)

    assert refusal.value.status_code == 409
    assert conflicting.status is CONFLICTING


def test_the_coordinator_can_withdraw_a_conflicting_request(
    db_session: Session,
    conflicting_pair: tuple[VenueBookingRequest, VenueBookingRequest, EventRequest],
) -> None:
    _, conflicting, event = conflicting_pair

    withdrawn = services.withdraw_arrangement(
        event.reference, conflicting.id, coordinator_id=COORDINATOR_ID, session=db_session
    )

    assert withdrawn.request.status is BookingRequestStatus.WITHDRAWN


def test_a_second_request_for_the_same_period_is_refused_while_the_first_is_conflicting(
    db_session: Session,
    conflicting_pair: tuple[VenueBookingRequest, VenueBookingRequest, EventRequest],
) -> None:
    """The one-request-per-event-venue-and-period rule (SCRUM-42 AC6) still holds."""
    _, conflicting, event = conflicting_pair
    venue = db_session.get(Venue, conflicting.venue_id)

    with pytest.raises(ConflictError) as refusal:
        raise_booking(venue, event, db_session, **period(at(11), at(14)))

    assert refusal.value.message == (
        "A pending request for this event, venue and period already exists."
    )
