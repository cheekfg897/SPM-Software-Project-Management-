"""Unit tests for SCRUM-111 — the coordinator cancels one approved venue booking.

AC1: only that booking is released, its arrangement becomes Cancelled and the venue is
free for that period again. AC2: the event's other bookings are untouched; an Approved
event stays Approved; an event in Safety Review goes back to Approved if the Safety
Officer had passed it (the pass no longer counts) or if the booking was its last active
venue (SCRUM-97 AC3), and otherwise stays, and every Safety Officer is told. AC3: every
Venue Staff user is told. AC4: the refusals, one while a replacement for the booking is
Pending or Conflicting (not On Hold). AC5: the history entry. ADR-0117 records
what the ACs leave open: the Safety Officers are told when the event goes back too, and
the coordinator is told nothing. Runs against ``db_session``, so the queries really
run.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import has_safety_approval
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    BookingStatus,
    Venue,
    VenueBookingRequest,
)
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    approved_arrangement,
    at,
    bookings,
    decide,
    edit_event,
    flags_on,
    history_entries,
    locked_request_reads,
    period,
    place_hold,
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
#: AC4: a replacement in these statuses holds the cancel back until the coordinator
#: withdraws it.
WAITING_REPLACEMENT_STATUSES = [BookingRequestStatus.PENDING, BookingRequestStatus.CONFLICTING]
#: Every other status a replacement can be in, On Hold among them (AC4 as written, see
#: ADR-0118 "Revisit when"). Built from the enum, so a status added later is let through
#: unless it is added above.
NOT_WAITING_REPLACEMENT_STATUSES = [
    status for status in BookingRequestStatus if status not in WAITING_REPLACEMENT_STATUSES
]
REPLACEMENT_WAITING_MESSAGE = (
    "A replacement for this booking is waiting for Venue Staff. Withdraw it first if the"
    " event no longer needs this venue. Approving it will release this booking anyway."
)


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


def _replacement_for(
    replaced_id: int, event: EventRequest, venue: Venue, session: Session
) -> VenueBookingRequest:
    """A Pending replacement at ``venue`` for the arrangement, once a change flags it.

    Flagged by a change to the venue requirements, as SCRUM-92 requires.
    """
    edit_event(session, event, {"venue_requirements": "A stage for the band."})
    return raise_booking(venue, event, session, replaces_request_id=replaced_id)


def _into_status(
    arrangement: VenueBookingRequest, status: BookingRequestStatus, session: Session
) -> None:
    """Write ``status`` straight onto the arrangement, as later steps would leave it."""
    arrangement.status = status
    session.commit()


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
    _into_status(arrangement, status, db_session)

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
        "Only an approved event or one in Safety Review can have its venue arrangements"
        f" withdrawn, changed or cancelled; this one is {status.value}."
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


def test_an_unknown_arrangement_is_not_found(db_session: Session, event: EventRequest) -> None:
    with pytest.raises(NotFoundError) as refused:
        _cancel(event, 9999, db_session)

    assert refused.value.message == "Venue arrangement not found."


def test_the_arrangement_is_read_under_a_row_lock(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    """Read under a row lock, as SCRUM-59's reconfirm and reject read it (ADR-0045).

    A reject and a cancel, or two cancels, take turns rather than both writing their
    history and notices.
    """
    reads = locked_request_reads(db_session, lambda: _cancel(event, booked, db_session))

    assert len(reads) == 1


# --------------------------------------------------------------------------
# AC4 — refused while a replacement for the booking waits for Venue Staff
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", WAITING_REPLACEMENT_STATUSES, ids=lambda status: status.value)
def test_a_replacement_waiting_for_venue_staff_holds_the_cancellation_back(
    db_session: Session,
    event: EventRequest,
    booked: int,
    second_venue: Venue,
    status: BookingRequestStatus,
) -> None:
    """The coordinator withdraws it first; the system doesn't (ADR-0117 decision 6)."""
    replacement = _replacement_for(booked, event, second_venue, db_session)
    _into_status(replacement, status, db_session)

    with pytest.raises(ConflictError) as refused:
        _cancel(event, booked, db_session)

    assert refused.value.message == REPLACEMENT_WAITING_MESSAGE
    _assert_nothing_changed(db_session, event, booked)
    assert _status_of(db_session, replacement.id) is status


def test_a_waiting_replacement_holds_it_back_in_safety_review_too_and_the_event_stays(
    db_session: Session, event: EventRequest, booked: int, second_venue: Venue
) -> None:
    """There it counts as an active venue, so AC2's last-venue rule wouldn't fire."""
    _replacement_for(booked, event, second_venue, db_session)
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    with pytest.raises(ConflictError) as refused:
        _cancel(event, booked, db_session)

    assert refused.value.message == REPLACEMENT_WAITING_MESSAGE
    _assert_nothing_changed(db_session, event, booked)
    assert reload_event(db_session, event.id).status is EventRequestStatus.SAFETY_REVIEW


@pytest.mark.parametrize(
    "status", NOT_WAITING_REPLACEMENT_STATUSES, ids=lambda status: status.value
)
def test_a_replacement_in_any_other_status_does_not_hold_it_back(
    db_session: Session,
    event: EventRequest,
    booked: int,
    second_venue: Venue,
    status: BookingRequestStatus,
) -> None:
    """On Hold included, as AC4 says (ADR-0118 "Revisit when")."""
    replacement = _replacement_for(booked, event, second_venue, db_session)
    _into_status(replacement, status, db_session)

    _cancel(event, booked, db_session)

    assert _status_of(db_session, booked) is BookingRequestStatus.CANCELLED
    assert _status_of(db_session, replacement.id) is status


def test_once_the_replacement_is_withdrawn_the_booking_can_be_cancelled(
    db_session: Session, event: EventRequest, booked: int, second_venue: Venue
) -> None:
    replacement = _replacement_for(booked, event, second_venue, db_session)
    with pytest.raises(ConflictError):
        _cancel(event, booked, db_session)

    services.withdraw_arrangement(
        event.reference, replacement.id, coordinator_id=COORDINATOR_ID, session=db_session
    )
    _cancel(event, booked, db_session)

    assert _status_of(db_session, booked) is BookingRequestStatus.CANCELLED


def test_another_bookings_waiting_replacement_does_not_hold_this_one_back(
    db_session: Session, event: EventRequest, booked: int, also_booked: int, second_venue: Venue
) -> None:
    replacement = _replacement_for(booked, event, second_venue, db_session)

    _cancel(event, also_booked, db_session)

    assert _status_of(db_session, also_booked) is BookingRequestStatus.CANCELLED
    assert _status_of(db_session, replacement.id) is BookingRequestStatus.PENDING


def test_a_booking_that_is_not_approved_is_refused_as_such_before_its_replacement(
    db_session: Session, event: EventRequest, booked: int, second_venue: Venue
) -> None:
    """ADR-0117 decision 5: the booking's own status is checked first."""
    _replacement_for(booked, event, second_venue, db_session)
    _into_status(reload_request(db_session, booked), BookingRequestStatus.REJECTED, db_session)

    with pytest.raises(ConflictError) as refused:
        _cancel(event, booked, db_session)

    assert (
        refused.value.message == "Only an approved booking can be cancelled; this one is rejected."
    )


def test_a_waiting_replacement_is_reported_before_a_missing_reason(
    db_session: Session, event: EventRequest, booked: int, second_venue: Venue
) -> None:
    """ADR-0117 decision 5: no point asking for a reason the cancel can't use yet."""
    _replacement_for(booked, event, second_venue, db_session)

    with pytest.raises(ConflictError) as refused:
        _cancel(event, booked, db_session, payload={})

    assert refused.value.message == REPLACEMENT_WAITING_MESSAGE


# --------------------------------------------------------------------------
# ADR-0117 decision 6 — a flagged booking, and a replacement raised for it
# --------------------------------------------------------------------------


def test_a_flagged_booking_is_cancelled_keeping_its_flags_as_the_record(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    edit_event(db_session, event, {"venue_requirements": "A stage for the band."})
    flags = flags_on(db_session, booked)
    assert flags != []

    _cancel(event, booked, db_session)

    assert _status_of(db_session, booked) is BookingRequestStatus.CANCELLED
    assert flags_on(db_session, booked) == flags
    assert reload_request(db_session, booked).is_flagged_after_change is False


def test_an_on_hold_replacement_approved_after_its_original_was_cancelled_leaves_it_cancelled(
    db_session: Session,
    event: EventRequest,
    venue: Venue,
    booked: int,
    second_venue: Venue,
    pin_now: Callable[[datetime], None],
) -> None:
    """An On Hold replacement doesn't block the cancel (AC4), so it can be approved.

    Its final approval adds its venue back and leaves the original Cancelled, not
    Released (ADR-0117 decision 6).
    """
    replacement = _replacement_for(booked, event, second_venue, db_session)
    pin_now(at(9, day=1) - timedelta(days=7))
    place_hold(replacement.id, at(8, day=1), db_session)
    _cancel(event, booked, db_session)

    decide(replacement.id, "approved", db_session)

    assert _status_of(db_session, booked) is BookingRequestStatus.CANCELLED
    assert _status_of(db_session, replacement.id) is BookingRequestStatus.APPROVED
    assert bookings(db_session) == [
        (venue.id, BookingStatus.CANCELLED),
        (second_venue.id, BookingStatus.CONFIRMED),
    ]


# --------------------------------------------------------------------------
# AC3 — every Venue Staff user is told; AC2 — so is every Safety Officer
# --------------------------------------------------------------------------

#: A second Venue Staff user and two Safety Officers, beside ``saved_users``' own.
OTHER_VENUE_STAFF_ID = 44
SAFETY_OFFICER_IDS = [21, 22]
#: What the notices say about the booking, in business time (ADR-0117).
CANCELLED_DETAIL = (
    "Venue arrangement {id} at Main Hall, 2026-11-01 09:00 to 2026-11-01 12:00, was cancelled."
)
BACK_IN_PLANNING = " It is back in planning until it can be sent to Safety Review again."


def _notices(user_id: int) -> list[tuple[str, str, NotificationKind, str | None]]:
    """The user's notices as (reference, event name, kind, detail), newest first."""
    rows = []
    for notice in list_notifications_for_recipient(user_id):
        rows.append((notice.event_reference, notice.event_name, notice.kind, notice.detail))
    return rows


def _forget_earlier_notices(session: Session) -> None:
    """Delete the notices raising and approving the bookings sent, before the act."""
    session.execute(delete(Notification))
    session.commit()


@pytest.fixture()
def staff(
    db_session: Session, saved_users: list[User], make_user: Callable[..., User]
) -> list[User]:
    """``saved_users``, another Venue Staff user and two Safety Officers."""
    others = [
        make_user(email="staff44@example.com", role=Role.VENUE_STAFF, user_id=44),
        make_user(email="safety21@example.com", role=Role.SAFETY_OFFICER, user_id=21),
        make_user(email="safety22@example.com", role=Role.SAFETY_OFFICER, user_id=22),
    ]
    db_session.add_all(others)
    db_session.commit()
    return [*saved_users, *others]


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        (
            NotificationKind.VENUE_BOOKING_CANCELLED,
            "The event's coordinator cancelled a venue booking, so the venue is free again.",
        ),
        (
            NotificationKind.SAFETY_REVIEW_VENUE_CANCELLED,
            "A venue was dropped from an event in Safety Review.",
        ),
    ],
    ids=["venue-staff", "safety-officers"],
)
def test_each_notice_says_what_happened(kind: NotificationKind, message: str) -> None:
    assert MESSAGE_BY_KIND[kind] == message


@pytest.mark.usefixtures("staff")
def test_every_venue_staff_user_is_told_naming_the_event_venue_and_period(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _forget_earlier_notices(db_session)
    _cancel(event, booked, db_session)

    told = (
        event.reference,
        "Partner Summit",
        NotificationKind.VENUE_BOOKING_CANCELLED,
        CANCELLED_DETAIL.format(id=booked),
    )
    assert _notices(VENUE_STAFF_ID) == [told]
    assert _notices(OTHER_VENUE_STAFF_ID) == [told]


@pytest.mark.usefixtures("staff")
def test_in_safety_review_every_safety_officer_is_told_the_venue_dropped(
    db_session: Session, event: EventRequest, booked: int, also_booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    _forget_earlier_notices(db_session)
    _cancel(event, booked, db_session)

    for officer_id in SAFETY_OFFICER_IDS:
        assert _notices(officer_id) == [
            (
                event.reference,
                "Partner Summit",
                NotificationKind.SAFETY_REVIEW_VENUE_CANCELLED,
                CANCELLED_DETAIL.format(id=booked),
            )
        ]


@pytest.mark.usefixtures("staff")
@pytest.mark.parametrize("passed", [True, False], ids=["passed", "last-venue"])
def test_an_event_sent_back_to_approved_tells_the_safety_officers_so(
    db_session: Session, event: EventRequest, booked: int, passed: bool
) -> None:
    """ADR-0117: the SCRUM-33 AC9 notice's pattern, when the event leaves their list."""
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)
    if passed:
        approve_safety(event, db_session)

    _forget_earlier_notices(db_session)
    _cancel(event, booked, db_session)

    for officer_id in SAFETY_OFFICER_IDS:
        assert [detail for *_, detail in _notices(officer_id)] == [
            CANCELLED_DETAIL.format(id=booked) + BACK_IN_PLANNING
        ]


@pytest.mark.usefixtures("staff")
def test_an_approved_events_cancellation_tells_no_safety_officer(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _forget_earlier_notices(db_session)
    _cancel(event, booked, db_session)

    for officer_id in SAFETY_OFFICER_IDS:
        assert _notices(officer_id) == []


@pytest.mark.usefixtures("staff")
@pytest.mark.parametrize("status", CANCELLABLE_EVENT_STATUSES, ids=lambda status: status.value)
def test_the_coordinator_who_cancelled_is_told_nothing(
    db_session: Session, event: EventRequest, booked: int, status: EventRequestStatus
) -> None:
    """ADR-0117: they did it."""
    _into(event, status, db_session)

    _forget_earlier_notices(db_session)
    _cancel(event, booked, db_session)

    assert _notices(COORDINATOR_ID) == []


@pytest.mark.usefixtures("staff")
def test_a_refused_cancellation_tells_nobody(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    _forget_earlier_notices(db_session)
    with pytest.raises(ValidationError):
        _cancel(event, booked, db_session, payload={})

    assert _notices(VENUE_STAFF_ID) == []
    assert _notices(SAFETY_OFFICER_IDS[0]) == []


@pytest.mark.usefixtures("staff")
def test_a_notice_that_cannot_be_saved_loses_only_itself(
    db_session: Session,
    event: EventRequest,
    booked: int,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The cancellation is committed before anyone is told (ADR-0015)."""

    def _fail(*_: object, **__: object) -> None:
        raise SQLAlchemyError("notifications table is gone")

    monkeypatch.setattr(services, "notify_users", _fail)

    _forget_earlier_notices(db_session)
    shown = _cancel(event, booked, db_session)

    assert shown.request.status is BookingRequestStatus.CANCELLED
    db_session.rollback()
    assert _status_of(db_session, booked) is BookingRequestStatus.CANCELLED
    assert [status for _, status in bookings(db_session)] == [BookingStatus.CANCELLED]
    assert "venue_booking_notification_failed" in caplog.text
