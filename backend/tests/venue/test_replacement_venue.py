"""Unit tests for SCRUM-92 — replacing a venue that became unavailable.

AC6: the coordinator raises a replacement request linked to the flagged arrangement,
for an approved event or one in Safety Review (ADR-0053). AC7: approving the replacement
releases the flagged arrangement and cancels its booking. AC10: if the event had passed
its safety check, approving the replacement withdraws that approval, and an event in
Safety Review goes back to Approved to be sent again.

The services run against ``db_session``. The flagged arrangement is at the Auditorium,
09:00 to 12:00 on 1 November 2026; the replacement is at the Breakout room.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, ValidationError
from app.modules.events import services as event_services
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    BookingStatus,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    COORDINATOR_ID,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    at,
    block,
    bookings,
    decide,
    history_entries,
    raise_booking,
    reload_event,
    reload_request,
    two_venues,
)

pytestmark = pytest.mark.scrum_92

NOT_FLAGGED_MESSAGE = "This venue arrangement does not need an alternative venue."
#: AC6: the planning stage, and Safety Review, which a flag leaves an event in (AC3).
MAY_REPLACE = {EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW}
#: A draft is left out: a coordinator gets a 404 for it, not a 409 (ADR-0024).
MAY_NOT_REPLACE = [
    status
    for status in EventRequestStatus
    if status not in MAY_REPLACE and status is not EventRequestStatus.DRAFT
]


class Flagged:
    """An event whose Approved arrangement at the Auditorium a block has flagged."""

    def __init__(self, event: EventRequest, original: VenueBookingRequest, other: Venue) -> None:
        self.event = event
        self.original = original
        self.other = other


@pytest.fixture()
def flagged(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> Flagged:
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    original = decide(raise_booking(auditorium, event, db_session).id, "approved", db_session)
    block(auditorium, at(10), at(11), db_session)
    return Flagged(event, original, breakout)


def _replace(flagged: Flagged, session: Session, **overrides: Any) -> VenueBookingRequest:
    """Raise a request at the other venue replacing the flagged arrangement (AC6)."""
    return raise_booking(
        flagged.other,
        flagged.event,
        session,
        replaces_request_id=flagged.original.id,
        **overrides,
    )


def _set_event_status(session: Session, event: EventRequest, status: EventRequestStatus) -> None:
    event.status = status
    session.commit()


# --------------------------------------------------------------------------
# AC6 — a replacement request linked to the flagged arrangement
# --------------------------------------------------------------------------


def test_a_replacement_is_raised_linked_to_the_flagged_arrangement(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    saved = reload_request(db_session, replacement.id)
    assert saved.replaces_request_id == flagged.original.id
    assert saved.venue_id == flagged.other.id
    assert saved.status is BookingRequestStatus.PENDING


def test_raising_the_replacement_leaves_the_flagged_arrangement_as_it_was(
    db_session: Session, flagged: Flagged
) -> None:
    """The original stands until the replacement is approved (AC4, AC7)."""
    _replace(flagged, db_session)

    original = reload_request(db_session, flagged.original.id)
    assert original.status is BookingRequestStatus.APPROVED
    assert original.needs_alternative_venue is True


@pytest.mark.parametrize("status", sorted(MAY_REPLACE, key=lambda status: status.value))
def test_an_approved_event_or_one_in_safety_review_may_raise_a_replacement(
    db_session: Session, flagged: Flagged, status: EventRequestStatus
) -> None:
    _set_event_status(db_session, flagged.event, status)

    replacement = _replace(flagged, db_session)

    assert replacement.replaces_request_id == flagged.original.id


@pytest.mark.parametrize("status", MAY_NOT_REPLACE)
def test_an_event_at_any_other_status_may_not_raise_a_replacement(
    db_session: Session, flagged: Flagged, status: EventRequestStatus
) -> None:
    _set_event_status(db_session, flagged.event, status)

    with pytest.raises(ConflictError) as refusal:
        _replace(flagged, db_session)

    assert refusal.value.message == (
        "Only an approved event or one in Safety Review can replace a venue;"
        f" this one is {status.value}."
    )


def test_an_event_in_safety_review_still_may_not_raise_an_ordinary_request(
    db_session: Session, flagged: Flagged
) -> None:
    """Only a replacement gets past SCRUM-42's approved-only rule."""
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)

    with pytest.raises(ConflictError):
        raise_booking(flagged.other, flagged.event, db_session)


def test_a_replacement_for_an_arrangement_that_is_not_flagged_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent, make_venue: Callable[..., Venue]
) -> None:
    event = saved_event()
    unflagged = raise_booking(venue, event, db_session)
    other = make_venue(name="Annex")
    db_session.add(other)
    db_session.commit()

    with pytest.raises(ValidationError) as refusal:
        raise_booking(other, event, db_session, replaces_request_id=unflagged.id)

    assert refusal.value.details == {"replaces_request_id": [NOT_FLAGGED_MESSAGE]}


def test_a_replacement_for_a_released_arrangement_is_refused(
    db_session: Session, flagged: Flagged
) -> None:
    """Released, it no longer needs anything, though its flags stay as the record."""
    flagged.original.status = BookingRequestStatus.RELEASED
    db_session.commit()

    with pytest.raises(ValidationError) as refusal:
        _replace(flagged, db_session)

    assert refusal.value.details == {"replaces_request_id": [NOT_FLAGGED_MESSAGE]}


def test_a_replacement_for_another_events_arrangement_is_refused_as_not_found(
    db_session: Session, flagged: Flagged, saved_event: SavedEvent
) -> None:
    """Another event's flagged arrangement, so only the event check can refuse it."""
    another_event = saved_event()

    with pytest.raises(ValidationError) as refusal:
        raise_booking(
            flagged.other, another_event, db_session, replaces_request_id=flagged.original.id
        )

    assert refusal.value.details == {"replaces_request_id": ["Venue arrangement not found."]}


def test_a_replacement_for_an_unknown_arrangement_is_refused_as_not_found(
    db_session: Session, flagged: Flagged
) -> None:
    with pytest.raises(ValidationError) as refusal:
        raise_booking(flagged.other, flagged.event, db_session, replaces_request_id=999)

    assert refusal.value.details == {"replaces_request_id": ["Venue arrangement not found."]}


def test_a_refused_replacement_saves_nothing(db_session: Session, flagged: Flagged) -> None:
    before = db_session.scalars(select(VenueBookingRequest.id)).all()

    with pytest.raises(ValidationError):
        raise_booking(flagged.other, flagged.event, db_session, replaces_request_id=999)

    assert db_session.scalars(select(VenueBookingRequest.id)).all() == before


# --------------------------------------------------------------------------
# AC7 — approving the replacement releases the flagged arrangement
# --------------------------------------------------------------------------


def test_approving_the_replacement_releases_the_flagged_arrangement_and_its_booking(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    released = reload_request(db_session, flagged.original.id)
    assert released.status is BookingRequestStatus.RELEASED
    assert released.needs_alternative_venue is False
    assert len(released.flags) == 1
    assert bookings(db_session) == [
        (flagged.original.venue_id, BookingStatus.CANCELLED),
        (flagged.other.id, BookingStatus.CONFIRMED),
    ]


def test_the_decisions_history_entry_names_the_arrangement_it_replaced(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    approved_entry = [
        entry
        for entry in db_session.scalars(select(EventHistoryEntry))
        if entry.kind is EventHistoryKind.VENUE_BOOKING_APPROVED
        and entry.details["venue_booking_request_id"] == replacement.id
    ]
    assert approved_entry[0].details["replaces_request_id"] == flagged.original.id


def test_rejecting_the_replacement_leaves_the_flagged_arrangement_standing(
    db_session: Session, flagged: Flagged
) -> None:
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "rejected", db_session, reason="Booked out.")

    original = reload_request(db_session, flagged.original.id)
    assert original.status is BookingRequestStatus.APPROVED
    assert original.needs_alternative_venue is True
    assert bookings(db_session) == [(flagged.original.venue_id, BookingStatus.CONFIRMED)]


def test_approving_an_ordinary_request_releases_nothing(
    db_session: Session, flagged: Flagged
) -> None:
    """A second venue for the event, not a replacement: the flagged one stays."""
    ordinary = raise_booking(flagged.other, flagged.event, db_session)

    decide(ordinary.id, "approved", db_session)

    assert reload_request(db_session, flagged.original.id).status is BookingRequestStatus.APPROVED
    assert bookings(db_session) == [
        (flagged.original.venue_id, BookingStatus.CONFIRMED),
        (flagged.other.id, BookingStatus.CONFIRMED),
    ]


def test_a_flagged_pending_request_is_released_with_no_booking_to_cancel(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    pending = raise_booking(auditorium, event, db_session)
    block(auditorium, at(10), at(11), db_session)
    replacement = raise_booking(breakout, event, db_session, replaces_request_id=pending.id)

    decide(replacement.id, "approved", db_session)

    assert reload_request(db_session, pending.id).status is BookingRequestStatus.RELEASED
    assert bookings(db_session) == [(breakout.id, BookingStatus.CONFIRMED)]


def test_only_the_replaced_arrangements_booking_is_cancelled(
    db_session: Session, flagged: Flagged
) -> None:
    """A later booking at the same venue for the same event is another arrangement."""
    auditorium = db_session.get(Venue, flagged.original.venue_id)
    assert auditorium is not None
    later = raise_booking(
        auditorium,
        flagged.event,
        db_session,
        starts_at=at(13).isoformat(),
        ends_at=at(16).isoformat(),
    )
    decide(later.id, "approved", db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert bookings(db_session) == [
        (flagged.original.venue_id, BookingStatus.CANCELLED),
        (flagged.original.venue_id, BookingStatus.CONFIRMED),
        (flagged.other.id, BookingStatus.CONFIRMED),
    ]


def test_a_replacement_approved_after_the_flag_cleared_still_releases_the_original(
    db_session: Session, flagged: Flagged
) -> None:
    """ADR-0053 default, pending the customer: the coordinator asked to replace it.

    To keep the original once its venue is free again, they withdraw the replacement.
    """
    replacement = _replace(flagged, db_session)
    [venue_block] = services.list_venue_blocks(flagged.original.venue_id, session=db_session)
    services.remove_venue_block(flagged.original.venue_id, venue_block.id, session=db_session)
    assert reload_request(db_session, flagged.original.id).needs_alternative_venue is False

    decide(replacement.id, "approved", db_session)

    assert reload_request(db_session, flagged.original.id).status is BookingRequestStatus.RELEASED


def test_a_second_replacement_leaves_an_already_released_arrangement_released(
    db_session: Session, flagged: Flagged, make_venue: Callable[..., Venue]
) -> None:
    first = _replace(flagged, db_session)
    annex = make_venue(name="Annex")
    db_session.add(annex)
    db_session.commit()
    second = raise_booking(
        annex, flagged.event, db_session, replaces_request_id=flagged.original.id
    )
    decide(first.id, "approved", db_session)

    decide(second.id, "approved", db_session)

    assert reload_request(db_session, flagged.original.id).status is BookingRequestStatus.RELEASED
    assert [status for _, status in bookings(db_session)] == [
        BookingStatus.CANCELLED,
        BookingStatus.CONFIRMED,
        BookingStatus.CONFIRMED,
    ]


def _withdraw(event: EventRequest, request_id: int, session: Session) -> None:
    services.withdraw_arrangement(
        event.reference, request_id, coordinator_id=COORDINATOR_ID, session=session
    )


def _reject(event: EventRequest, request_id: int, session: Session) -> None:
    decide(request_id, "rejected", session, reason="Venue closed.")


@pytest.mark.parametrize(
    ("stop_holding", "left_as"),
    [
        pytest.param(_withdraw, BookingRequestStatus.WITHDRAWN, id="withdrawn"),
        pytest.param(_reject, BookingRequestStatus.REJECTED, id="rejected"),
    ],
)
def test_an_original_that_stopped_holding_its_venue_is_left_as_it_is(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    stop_holding: Callable[[EventRequest, int, Session], None],
    left_as: BookingRequestStatus,
) -> None:
    """ADR-0053 §11: an original already retired or decided against isn't released.

    The flagged Pending original is withdrawn or rejected after its replacement was
    raised; approving the replacement leaves that status as it is.
    """
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    pending = raise_booking(auditorium, event, db_session)
    block(auditorium, at(10), at(11), db_session)
    replacement = raise_booking(breakout, event, db_session, replaces_request_id=pending.id)
    stop_holding(event, pending.id, db_session)

    decide(replacement.id, "approved", db_session)

    assert reload_request(db_session, pending.id).status is left_as


# --------------------------------------------------------------------------
# AC10 — a replacement withdraws the safety approval
# --------------------------------------------------------------------------


def test_a_replacement_withdraws_the_safety_approval_and_sends_the_event_back_to_approved(
    db_session: Session, flagged: Flagged
) -> None:
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)
    approve_safety(flagged.event, db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is False
    assert reload_event(db_session, flagged.event.id).status is EventRequestStatus.APPROVED
    withdrawn = [
        entry
        for entry in db_session.scalars(select(EventHistoryEntry))
        if entry.kind is EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN
    ]
    assert [(entry.actor_id, entry.details) for entry in withdrawn] == [
        (
            VENUE_STAFF_ID,
            {
                "venue_booking_request_id": replacement.id,
                "replaces_request_id": flagged.original.id,
            },
        )
    ]


def test_a_returned_event_with_a_safety_approval_loses_it_and_stays_approved(
    db_session: Session, flagged: Flagged
) -> None:
    """Flagged while Confirmed, it went back to Approved (AC3) with its approval."""
    approve_safety(flagged.event, db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is False
    assert reload_event(db_session, flagged.event.id).status is EventRequestStatus.APPROVED


def test_an_event_without_a_safety_approval_has_nothing_withdrawn(
    db_session: Session, flagged: Flagged
) -> None:
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "approved", db_session)

    kinds = [entry.kind for entry in history_entries(db_session, flagged.event.id)]
    assert EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN not in kinds
    db_session.expire_all()
    assert db_session.get(EventRequest, flagged.event.id).status is EventRequestStatus.SAFETY_REVIEW


def test_approving_an_ordinary_request_keeps_the_safety_approval(
    db_session: Session, flagged: Flagged
) -> None:
    approve_safety(flagged.event, db_session)
    ordinary = raise_booking(flagged.other, flagged.event, db_session)

    decide(ordinary.id, "approved", db_session)

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is True


def test_a_rejected_replacement_keeps_the_safety_approval(
    db_session: Session, flagged: Flagged
) -> None:
    approve_safety(flagged.event, db_session)
    replacement = _replace(flagged, db_session)

    decide(replacement.id, "rejected", db_session, reason="Booked out.")

    assert event_services.has_safety_approval(flagged.event.id, session=db_session) is True


def test_the_event_can_pass_a_new_safety_check_after_the_withdrawal(
    db_session: Session, flagged: Flagged
) -> None:
    _set_event_status(db_session, flagged.event, EventRequestStatus.SAFETY_REVIEW)
    approve_safety(flagged.event, db_session)
    decide(_replace(flagged, db_session).id, "approved", db_session)

    sent = event_services.submit_for_safety_review(
        COORDINATOR_ID, flagged.event.reference, session=db_session
    )

    assert sent.status is EventRequestStatus.SAFETY_REVIEW
    latest = history_entries(db_session, flagged.event.id)[-1]
    assert latest.kind is EventHistoryKind.SAFETY_REVIEW_REQUESTED
