"""Unit tests for SCRUM-75 — Venue Staff place a tentative hold on a venue.

A hold follows Venue Staff's approval of one venue of a multi-venue event: it holds the
venue until an expiry Venue Staff choose, shows as Tentative, and is turned into the
confirmed booking by their final approval or released by a rejection (ADR-0045). The
clash rules against other bookings and holds are in ``test_hold_clashes.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, ValidationError
from app.modules.auth.permissions import Role
from app.modules.events.models import EventRequest
from app.modules.notifications.models import Notification, NotificationKind
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
    COORDINATOR_ID,
    SINGAPORE,
    SavedEvent,
    at,
    change_expiry,
    decide,
    event_starts_at,
    hours_from_now,
    place_hold,
    raise_booking,
)

pytestmark = pytest.mark.scrum_75

#: Every status a hold is refused in: all but the two that are still waiting. Built from
#: the enum, so a status added later is checked too.
NOT_HOLDABLE_STATUSES = [
    status
    for status in BookingRequestStatus
    if status not in {BookingRequestStatus.PENDING, BookingRequestStatus.CONFLICTING}
]


def _write_status(
    request: VenueBookingRequest, status: BookingRequestStatus, session: Session
) -> None:
    """Put ``request`` in ``status`` straight in the table, as no flow here can."""
    request.status = status
    session.commit()


def _bookings(session: Session) -> list[Booking]:
    return list(session.scalars(select(Booking).order_by(Booking.id)))


def _hold_of(request: VenueBookingRequest, session: Session) -> Booking:
    """The booking that holds the venue for ``request``, read back from the database."""
    session.expire_all()
    booking = session.get(VenueBookingRequest, request.id).booking
    assert booking is not None
    return booking


def _hold_notices(session: Session) -> list[Notification]:
    kinds = (NotificationKind.VENUE_HOLD_PLACED, NotificationKind.VENUE_HOLD_EXPIRY_CHANGED)
    query = select(Notification).where(Notification.kind.in_(kinds)).order_by(Notification.id)
    return list(session.scalars(query))


def _venue_ids_found(session: Session) -> list[int]:
    """The venues a search for 10:00-11:00 on 1 November 2026 finds."""
    payload = {
        "start_time": at(10).isoformat(),
        "end_time": at(11).isoformat(),
        "min_capacity": 1,
    }
    return [match.venue.id for match in services.search_venues(payload, session=session)]


def _calendar_kinds(venue_id: int, session: Session) -> list[CalendarEntryKind]:
    entries = services.get_venue_calendar(
        venue_id, at(0), at(23), viewer_role=Role.VENUE_STAFF, session=session
    )
    return [entry.kind for entry in entries]


def _expire(request: VenueBookingRequest, session: Session) -> None:
    """Move the hold's expiry into the past, as the passing of time would."""
    _hold_of(request, session).hold_expires_at = hours_from_now(-1)
    session.commit()


# --------------------------------------------------------------------------
# AC1 — a hold on a multi-venue event's request puts it On Hold
# --------------------------------------------------------------------------


def test_placing_a_hold_puts_the_request_on_hold_and_holds_the_venue_tentatively(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    expires_at = hours_from_now(48)

    held = place_hold(multi_venue_request.id, expires_at, db_session)

    booking = _hold_of(held, db_session)
    assert held.status is BookingRequestStatus.ON_HOLD
    assert (booking.status, booking.venue_id, booking.event_id) == (
        BookingStatus.TENTATIVE,
        multi_venue_request.venue_id,
        multi_venue_request.event_id,
    )
    assert (booking.start_time, booking.end_time) == (at(9), at(12))
    assert booking.hold_expires_at == expires_at


def test_the_hold_and_its_expiry_are_shown_on_the_events_requests(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    """AC9: the coordinator sees the hold and its expiry on the event record."""
    expires_at = hours_from_now(48)
    place_hold(multi_venue_request.id, expires_at, db_session)

    shown = services.list_booking_requests_for_event(
        multi_venue_event.reference, coordinator_id=COORDINATOR_ID, session=db_session
    )

    assert [(entry.request.status, entry.hold_expires_at) for entry in shown] == [
        (BookingRequestStatus.ON_HOLD, expires_at),
        (BookingRequestStatus.PENDING, None),
    ]


@pytest.mark.scrum_43  # "Any Venue Staff member can see every Pending and On Hold request"
def test_a_request_on_hold_stays_in_the_queue_with_its_expiry(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    expires_at = hours_from_now(48)
    place_hold(multi_venue_request.id, expires_at, db_session)

    queue = services.list_pending_booking_requests(session=db_session)

    assert [(entry.request.status, entry.hold_expires_at) for entry in queue] == [
        (BookingRequestStatus.ON_HOLD, expires_at),
        (BookingRequestStatus.PENDING, None),
    ]


def test_a_request_of_a_single_venue_event_cannot_be_held(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[object]
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    with pytest.raises(ConflictError) as refusal:
        place_hold(request.id, hours_from_now(48), db_session)

    assert refusal.value.message == (
        "A hold can only be placed on a request of an event with more than one venue."
    )
    assert _bookings(db_session) == []
    assert db_session.get(VenueBookingRequest, request.id).status is BookingRequestStatus.PENDING


def test_a_withdrawn_arrangement_no_longer_makes_the_event_multi_venue(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    second = services.list_active_arrangements(multi_venue_event.id, session=db_session)[1]
    services.withdraw_arrangement(
        multi_venue_event.reference, second.id, coordinator_id=COORDINATOR_ID, session=db_session
    )

    with pytest.raises(ConflictError):
        place_hold(multi_venue_request.id, hours_from_now(48), db_session)


def test_a_rejected_arrangement_still_makes_the_event_multi_venue(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    """Rejected is active until the coordinator withdraws it."""
    second = services.list_active_arrangements(multi_venue_event.id, session=db_session)[1]
    decide(second.id, "rejected", db_session, reason="Closed that day")

    held = place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    assert held.status is BookingRequestStatus.ON_HOLD


def test_a_hold_stands_when_the_event_later_drops_to_one_venue(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    """AC10: eligibility is checked when the hold is placed, not again afterwards."""
    second = services.list_active_arrangements(multi_venue_event.id, session=db_session)[1]
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    services.withdraw_arrangement(
        multi_venue_event.reference, second.id, coordinator_id=COORDINATOR_ID, session=db_session
    )

    status_after_move = change_expiry(multi_venue_request.id, hours_from_now(72), db_session).status
    approved = decide(multi_venue_request.id, "approved", db_session)

    assert status_after_move is BookingRequestStatus.ON_HOLD
    assert approved.status is BookingRequestStatus.APPROVED


@pytest.mark.parametrize("status", ["approved", "rejected", "on_hold"])
def test_only_a_request_still_waiting_can_be_held(
    db_session: Session, multi_venue_request: VenueBookingRequest, status: str
) -> None:
    if status == "on_hold":
        place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    else:
        decide(multi_venue_request.id, status, db_session, reason="Decided")
    bookings_before = len(_bookings(db_session))

    with pytest.raises(ConflictError) as refusal:
        place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    assert refusal.value.message == (
        f"Only a pending or conflicting request can be held; this one is {status}."
    )
    assert len(_bookings(db_session)) == bookings_before


def test_a_conflicting_request_can_be_held(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    """Conflicting (SCRUM-44) is still waiting for a decision, so it can be held."""
    _write_status(multi_venue_request, BookingRequestStatus.CONFLICTING, db_session)

    held = place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    assert held.status is BookingRequestStatus.ON_HOLD


@pytest.mark.parametrize("status", NOT_HOLDABLE_STATUSES, ids=lambda status: status.value)
def test_a_request_in_any_other_status_cannot_be_held(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    status: BookingRequestStatus,
) -> None:
    """Withdrawn included, which no decision reaches; nothing is booked."""
    _write_status(multi_venue_request, status, db_session)

    with pytest.raises(ConflictError) as refusal:
        place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    assert refusal.value.message == (
        f"Only a pending or conflicting request can be held; this one is {status.value}."
    )
    assert _bookings(db_session) == []


# --------------------------------------------------------------------------
# AC3 — the expiry is in the future and before the event starts
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expires_at", "message"),
    [
        pytest.param(hours_from_now(-1), "The expiry must be in the future.", id="already passed"),
        pytest.param(
            event_starts_at(), "The expiry must be before the event starts.", id="at the start"
        ),
        pytest.param(
            event_starts_at() + timedelta(hours=1),
            "The expiry must be before the event starts.",
            id="after the start",
        ),
    ],
)
def test_an_expiry_that_is_past_or_not_before_the_event_starts_is_refused(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    expires_at: datetime,
    message: str,
) -> None:
    with pytest.raises(ValidationError) as refusal:
        place_hold(multi_venue_request.id, expires_at, db_session)

    assert refusal.value.details == {"expires_at": [message]}
    assert _bookings(db_session) == []
    assert db_session.get(VenueBookingRequest, multi_venue_request.id).status is (
        BookingRequestStatus.PENDING
    )


def test_an_expiry_just_before_the_event_starts_is_accepted(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    held = place_hold(multi_venue_request.id, event_starts_at() - timedelta(minutes=1), db_session)

    assert held.status is BookingRequestStatus.ON_HOLD


def test_a_hold_needs_an_expiry(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    with pytest.raises(ValidationError) as refusal:
        services.place_booking_hold(multi_venue_request.id, {}, session=db_session)

    assert list(refusal.value.details) == ["expires_at"]


# --------------------------------------------------------------------------
# AC4 — Venue Staff can change an active hold's expiry
# --------------------------------------------------------------------------


def test_changing_the_expiry_moves_it_and_keeps_the_hold(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    later = hours_from_now(96)

    changed = change_expiry(multi_venue_request.id, later, db_session)

    assert changed.status is BookingRequestStatus.ON_HOLD
    assert _hold_of(changed, db_session).hold_expires_at == later


def test_a_new_expiry_is_held_to_the_same_rules(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    original = hours_from_now(48)
    place_hold(multi_venue_request.id, original, db_session)

    with pytest.raises(ValidationError):
        change_expiry(multi_venue_request.id, event_starts_at(), db_session)

    assert _hold_of(multi_venue_request, db_session).hold_expires_at == original


def test_the_expiry_of_a_request_that_is_not_on_hold_cannot_be_changed(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    with pytest.raises(ConflictError) as refusal:
        change_expiry(multi_venue_request.id, hours_from_now(48), db_session)

    assert (
        refusal.value.message
        == "Only a request on hold has an expiry to change; this one is pending."
    )


def test_the_expiry_of_a_hold_that_has_already_expired_cannot_be_changed(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    _expire(multi_venue_request, db_session)

    with pytest.raises(ConflictError) as refusal:
        change_expiry(multi_venue_request.id, hours_from_now(96), db_session)

    assert refusal.value.message == "This hold has expired."


# --------------------------------------------------------------------------
# AC6 — an active hold shows as Tentative and rules the venue out of search
# --------------------------------------------------------------------------


def test_an_active_hold_is_tentative_on_the_calendar_and_out_of_search(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    assert _calendar_kinds(multi_venue_request.venue_id, db_session) == [
        CalendarEntryKind.TENTATIVE_HOLD
    ]
    assert multi_venue_request.venue_id not in _venue_ids_found(db_session)


def test_an_expired_hold_is_off_the_calendar_and_back_in_search(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)
    _expire(multi_venue_request, db_session)

    assert _calendar_kinds(multi_venue_request.venue_id, db_session) == []
    assert multi_venue_request.venue_id in _venue_ids_found(db_session)


# --------------------------------------------------------------------------
# AC7 — final approval confirms the hold, a rejection releases the venue
# --------------------------------------------------------------------------


@pytest.mark.scrum_44  # "Approving a request that is On Hold does not conflict with its own hold"
def test_final_approval_just_before_the_expiry_turns_the_hold_into_the_confirmed_booking(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    pin_now: Callable[[datetime], None],
) -> None:
    expires_at = hours_from_now(48)
    place_hold(multi_venue_request.id, expires_at, db_session)
    pin_now(expires_at - timedelta(microseconds=1))

    approved = decide(multi_venue_request.id, "approved", db_session)

    (booking,) = _bookings(db_session)
    assert approved.status is BookingRequestStatus.APPROVED
    assert (booking.status, booking.hold_expires_at) == (BookingStatus.CONFIRMED, None)
    assert (booking.start_time, booking.end_time) == (at(9), at(12))


def test_rejecting_a_hold_releases_the_venue_at_once(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    place_hold(multi_venue_request.id, hours_from_now(48), db_session)

    rejected = decide(multi_venue_request.id, "rejected", db_session, reason="Not needed")

    (booking,) = _bookings(db_session)
    assert rejected.status is BookingRequestStatus.REJECTED
    assert booking.status is BookingStatus.CANCELLED
    assert multi_venue_request.venue_id in _venue_ids_found(db_session)


@pytest.mark.parametrize(
    "after_expiry",
    [
        pytest.param(timedelta(0), id="at the expiry"),
        pytest.param(timedelta(microseconds=1), id="just after the expiry"),
    ],
)
def test_final_approval_from_the_instant_the_hold_expires_is_refused(
    db_session: Session,
    multi_venue_request: VenueBookingRequest,
    pin_now: Callable[[datetime], None],
    after_expiry: timedelta,
) -> None:
    expires_at = hours_from_now(48)
    place_hold(multi_venue_request.id, expires_at, db_session)
    pin_now(expires_at + after_expiry)

    with pytest.raises(ConflictError) as refusal:
        decide(multi_venue_request.id, "approved", db_session)

    assert refusal.value.message == "This hold has expired."
    (booking,) = _bookings(db_session)
    assert booking.status is BookingStatus.TENTATIVE


# --------------------------------------------------------------------------
# AC9 — the coordinator is told when a hold is placed and when its expiry changes
# --------------------------------------------------------------------------


def test_the_coordinator_is_told_when_a_hold_is_placed_and_when_its_expiry_changes(
    db_session: Session, multi_venue_event: EventRequest, multi_venue_request: VenueBookingRequest
) -> None:
    first_expiry, second_expiry = hours_from_now(48), hours_from_now(96)

    place_hold(multi_venue_request.id, first_expiry, db_session)
    change_expiry(multi_venue_request.id, second_expiry, db_session)

    assert [
        (n.recipient_id, n.kind, n.event_reference, n.detail) for n in _hold_notices(db_session)
    ] == [
        (
            COORDINATOR_ID,
            NotificationKind.VENUE_HOLD_PLACED,
            multi_venue_event.reference,
            first_expiry.astimezone(SINGAPORE).isoformat(),
        ),
        (
            COORDINATOR_ID,
            NotificationKind.VENUE_HOLD_EXPIRY_CHANGED,
            multi_venue_event.reference,
            second_expiry.astimezone(SINGAPORE).isoformat(),
        ),
    ]


def test_a_refused_hold_tells_nobody(
    db_session: Session, multi_venue_request: VenueBookingRequest
) -> None:
    with pytest.raises(ValidationError):
        place_hold(multi_venue_request.id, hours_from_now(-1), db_session)

    assert _hold_notices(db_session) == []
