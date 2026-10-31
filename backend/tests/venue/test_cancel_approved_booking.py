"""Unit tests for SCRUM-111 — the coordinator cancels one approved venue booking.

AC1: only that booking is released, its arrangement becomes Cancelled and the venue is
free for that period again. AC2: the event's other bookings are untouched; an Approved
event stays Approved; an event in Safety Review goes back to Approved if the Safety
Officer had passed it (the pass no longer counts) or if the booking was its last active
venue (SCRUM-97 AC3), and otherwise stays. AC4: the refusals. AC5: the history entry.
ADR-0117 records what the ACs leave open. Runs against ``db_session``, so the queries
really run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import has_safety_approval
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, BookingStatus, Venue
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    SavedEvent,
    approve_safety,
    approved_arrangement,
    at,
    bookings,
    decide,
    history_entries,
    period,
    raise_booking,
    reload_event,
    reload_request,
)

pytestmark = pytest.mark.scrum_111

REASON = "The breakout sessions were merged into the main hall."
#: The statuses an event can be cancelled in: the planning stage (AC1).
CANCELLABLE_EVENT_STATUSES = [EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW]
#: Every other status but a draft, which no coordinator can see (ADR-0024). Built from
#: the enum, so a status added later is refused unless it is added above.
REFUSED_EVENT_STATUSES = [
    status
    for status in EventRequestStatus
    if status not in CANCELLABLE_EVENT_STATUSES and status is not EventRequestStatus.DRAFT
]
#: Every arrangement status but Approved: one not yet approved is withdrawn instead
#: (SCRUM-93), and one already retired has no booking left to cancel.
NOT_APPROVED_STATUSES = [
    status for status in BookingRequestStatus if status is not BookingRequestStatus.APPROVED
]


def _cancel(
    event: EventRequest,
    arrangement_id: int,
    session: Session,
    *,
    payload: dict[str, Any] | None = None,
    coordinator_id: int = COORDINATOR_ID,
) -> BookingRequestAsShown:
    body = {"reason": REASON} if payload is None else payload
    return services.cancel_approved_booking(
        event.reference, arrangement_id, body, coordinator_id=coordinator_id, session=session
    )


def _into(event: EventRequest, status: EventRequestStatus, session: Session) -> None:
    """Move the event straight to ``status``, as later steps of its life would."""
    event.status = status
    session.commit()


def _status_of(session: Session, arrangement_id: int) -> BookingRequestStatus:
    return reload_request(session, arrangement_id).status


def _history_kinds(session: Session, event: EventRequest) -> list[EventHistoryKind]:
    return [entry.kind for entry in history_entries(session, event.id)]


@pytest.fixture()
def event(saved_event: SavedEvent) -> EventRequest:
    """An approved event of coordinator 3's."""
    return saved_event()


@pytest.fixture()
def second_venue(make_venue: Callable[..., Venue], save: Callable[..., None]) -> Venue:
    """Another venue, for the event's second booking."""
    saved = make_venue(name="Breakout room")
    save(saved)
    return saved


@pytest.fixture()
def booked(db_session: Session, event: EventRequest, venue: Venue) -> int:
    """The id of the event's approved arrangement at ``venue``, 09:00-12:00 on 1 Nov."""
    return approved_arrangement(venue, event, db_session)


@pytest.fixture()
def also_booked(db_session: Session, event: EventRequest, second_venue: Venue) -> int:
    """The id of a second approved arrangement of the event's, 13:00-16:00."""
    return approved_arrangement(second_venue, event, db_session, **SECOND_PERIOD)


# --------------------------------------------------------------------------
# AC1 — only that booking is released, and the venue is free again
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", CANCELLABLE_EVENT_STATUSES, ids=lambda status: status.value)
def test_the_arrangement_becomes_cancelled_and_its_booking_is_released(
    db_session: Session,
    event: EventRequest,
    booked: int,
    also_booked: int,
    status: EventRequestStatus,
) -> None:
    _into(event, status, db_session)

    shown = _cancel(event, booked, db_session)

    assert shown.request.id == booked
    assert shown.request.status is BookingRequestStatus.CANCELLED
    assert _status_of(db_session, booked) is BookingRequestStatus.CANCELLED
    # The first booking made is the cancelled one's; the other still holds its venue.
    assert [status for _, status in bookings(db_session)] == [
        BookingStatus.CANCELLED,
        BookingStatus.CONFIRMED,
    ]


def test_the_venue_can_be_booked_for_that_period_again(
    db_session: Session, event: EventRequest, venue: Venue, booked: int, saved_event: SavedEvent
) -> None:
    other_event = saved_event()
    waiting = raise_booking(venue, other_event, db_session)
    with pytest.raises(ConflictError):
        decide(waiting.id, "approved", db_session)

    _cancel(event, booked, db_session)

    assert decide(waiting.id, "approved", db_session).status is BookingRequestStatus.APPROVED


# --------------------------------------------------------------------------
# AC2 — the event's other bookings are untouched
# --------------------------------------------------------------------------


def test_the_events_other_arrangements_are_untouched(
    db_session: Session, event: EventRequest, booked: int, also_booked: int, venue: Venue
) -> None:
    pending = raise_booking(venue, event, db_session, **period(at(9, day=2), at(12, day=2)))
    pending_id = pending.id

    _cancel(event, booked, db_session)

    assert _status_of(db_session, also_booked) is BookingRequestStatus.APPROVED
    assert _status_of(db_session, pending_id) is BookingRequestStatus.PENDING


# --------------------------------------------------------------------------
# AC2 — what happens to the event's status
# --------------------------------------------------------------------------


def test_an_approved_event_stays_approved_even_without_a_venue_left(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _cancel(event, booked, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED


def test_in_safety_review_with_another_venue_and_no_pass_the_event_stays(
    db_session: Session, event: EventRequest, booked: int, also_booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    _cancel(event, booked, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.SAFETY_REVIEW
    assert EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN not in _history_kinds(db_session, event)


def test_in_safety_review_a_pass_no_longer_counts_and_the_event_goes_back_to_approved(
    db_session: Session, event: EventRequest, booked: int, also_booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)
    approve_safety(event, db_session)

    _cancel(event, booked, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert has_safety_approval(event.id, session=db_session) is False
    withdrawal = history_entries(db_session, event.id)[-1]
    assert (withdrawal.kind, withdrawal.actor_id, withdrawal.details) == (
        EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN,
        COORDINATOR_ID,
        {"venue_booking_request_id": booked},
    )


def test_in_safety_review_cancelling_the_last_active_venue_sends_the_event_back(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    _cancel(event, booked, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    # No pass was given, so none is withdrawn.
    assert EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN not in _history_kinds(db_session, event)


def test_a_withdrawn_arrangement_does_not_count_as_a_venue_left(
    db_session: Session, event: EventRequest, booked: int, second_venue: Venue
) -> None:
    """Only an active arrangement keeps the event in Safety Review (SCRUM-97 AC3)."""
    withdrawn = raise_booking(second_venue, event, db_session, **SECOND_PERIOD)
    services.withdraw_arrangement(
        event.reference, withdrawn.id, coordinator_id=COORDINATOR_ID, session=db_session
    )
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    _cancel(event, booked, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED


def test_with_a_pass_and_no_venue_left_the_event_goes_back_once(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)
    approve_safety(event, db_session)

    _cancel(event, booked, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    kinds = _history_kinds(db_session, event)
    assert kinds.count(EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN) == 1


# --------------------------------------------------------------------------
# AC5 — the cancellation and its reason are in the event's history
# --------------------------------------------------------------------------


def test_the_cancellation_and_its_reason_are_written_to_the_history(
    db_session: Session, event: EventRequest, booked: int, venue: Venue
) -> None:
    _cancel(event, booked, db_session, payload={"reason": f"  {REASON}  "})

    entry = history_entries(db_session, event.id)[-1]
    assert (entry.kind, entry.actor_id, entry.details) == (
        EventHistoryKind.VENUE_BOOKING_CANCELLED,
        COORDINATOR_ID,
        {
            "venue_booking_request_id": booked,
            "venue_id": venue.id,
            "starts_at": "2026-11-01T01:00:00+00:00",
            "ends_at": "2026-11-01T04:00:00+00:00",
            "reason": REASON,
        },
    )


# --------------------------------------------------------------------------
# AC4 — the refusals, each saying which, and nothing changed
# --------------------------------------------------------------------------


def _assert_nothing_changed(session: Session, event: EventRequest, booked: int) -> None:
    assert _status_of(session, booked) is BookingRequestStatus.APPROVED
    assert [status for _, status in bookings(session)] == [BookingStatus.CONFIRMED]
    assert EventHistoryKind.VENUE_BOOKING_CANCELLED not in _history_kinds(session, event)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "A reason is required to cancel a booking."),
        ({"reason": None}, "A reason is required to cancel a booking."),
        ({"reason": "   "}, "Must not be blank."),
        ({"reason": 5}, "Not a valid string."),
        ({"reason": True}, "Not a valid string."),
        ({"reason": ["Merged"]}, "Not a valid string."),
    ],
    ids=["missing", "null", "blank", "a-number", "a-boolean", "a-list"],
)
def test_a_cancellation_without_a_reason_is_refused(
    db_session: Session, event: EventRequest, booked: int, payload: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError) as refused:
        _cancel(event, booked, db_session, payload=payload)

    assert refused.value.details == {"reason": [message]}
    _assert_nothing_changed(db_session, event, booked)


def test_a_field_the_body_may_not_carry_is_refused(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    with pytest.raises(ValidationError) as refused:
        _cancel(event, booked, db_session, payload={"reason": REASON, "status": "approved"})

    assert refused.value.details == {"status": ["Unknown field."]}
    _assert_nothing_changed(db_session, event, booked)


@pytest.mark.parametrize("status", NOT_APPROVED_STATUSES, ids=lambda status: status.value)
def test_an_arrangement_that_is_not_approved_is_refused_naming_its_status(
    db_session: Session, event: EventRequest, venue: Venue, status: BookingRequestStatus
) -> None:
    arrangement = raise_booking(venue, event, db_session)
    arrangement.status = status
    db_session.commit()

    with pytest.raises(ConflictError) as refused:
        _cancel(event, arrangement.id, db_session)

    assert refused.value.message == (
        f"Only an approved booking can be cancelled; this one is {status.value}."
    )
    assert _status_of(db_session, arrangement.id) is status
    assert EventHistoryKind.VENUE_BOOKING_CANCELLED not in _history_kinds(db_session, event)


@pytest.mark.parametrize("status", REFUSED_EVENT_STATUSES, ids=lambda status: status.value)
def test_an_event_past_or_before_planning_is_refused_naming_its_status(
    db_session: Session, event: EventRequest, booked: int, status: EventRequestStatus
) -> None:
    _into(event, status, db_session)

    with pytest.raises(ConflictError) as refused:
        _cancel(event, booked, db_session)

    assert refused.value.message == (
        "Only an approved event or one in Safety Review can have a venue booking cancelled;"
        f" this one is {status.value}."
    )
    _assert_nothing_changed(db_session, event, booked)


def test_a_coordinator_not_assigned_to_the_event_is_refused_as_not_found(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    with pytest.raises(NotFoundError) as refused:
        _cancel(event, booked, db_session, coordinator_id=42)

    assert refused.value.message == "Event request not found."
    _assert_nothing_changed(db_session, event, booked)


def test_another_events_arrangement_is_not_found(
    db_session: Session, event: EventRequest, venue: Venue, saved_event: SavedEvent
) -> None:
    other_event = saved_event()
    theirs = approved_arrangement(venue, other_event, db_session)

    with pytest.raises(NotFoundError) as refused:
        _cancel(event, theirs, db_session)

    assert refused.value.message == "Venue arrangement not found."
    assert _status_of(db_session, theirs) is BookingRequestStatus.APPROVED
