"""Unit tests for SCRUM-84 — Venue Staff record a venue booking's preparation details.

Any Venue Staff member records a preparation status and notes against an approved
booking (AC1, ADR-0049). The details are saved on the booking request, which the
coordinator reads (AC2), and nothing else of the event changes (AC3). Each update
writes a history entry naming the user and the time (AC4). Nothing is recorded until
the Safety Officer has approved the event (AC5).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.permissions import Role
from app.modules.events import services as event_services
from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    PreparationStatus,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    COORDINATOR_ID,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    decide,
    raise_booking,
)

pytestmark = pytest.mark.scrum_84

IN_PROGRESS = {"status": "in_progress", "notes": "Chairs set out, stage to do."}
#: Every status but approved, built from the enum so a status added later is tested.
NOT_APPROVED_STATUSES = [
    status for status in BookingRequestStatus if status is not BookingRequestStatus.APPROVED
]


def _approved_booking(
    venue: Venue, event: EventRequest, session: Session, *, safety_approved: bool = True
) -> VenueBookingRequest:
    """An approved booking for an event the Safety Officer has (by default) approved."""
    booking = raise_booking(venue, event, session)
    decide(booking.id, "approved", session)
    if safety_approved:
        approve_safety(event, session)
    return booking


def _record(booking: VenueBookingRequest, payload: dict[str, str], session: Session) -> None:
    services.update_preparation_details(
        booking.id, payload, updated_by=VENUE_STAFF_ID, session=session
    )


def _preparation_entries(session: Session) -> list[EventHistoryEntry]:
    kind = EventHistoryKind.VENUE_PREPARATION_UPDATED
    return list(session.scalars(select(EventHistoryEntry).where(EventHistoryEntry.kind == kind)))


def test_venue_staff_record_a_status_and_notes_on_an_approved_booking(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC1."""
    booking = _approved_booking(venue, saved_event(), db_session)

    shown = services.update_preparation_details(
        booking.id, IN_PROGRESS, updated_by=VENUE_STAFF_ID, session=db_session
    )

    assert shown.request.preparation_status is PreparationStatus.IN_PROGRESS
    assert shown.request.preparation_notes == "Chairs set out, stage to do."


def test_a_booking_starts_as_not_started_with_no_notes(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    booking = _approved_booking(venue, saved_event(), db_session)

    assert booking.preparation_status is PreparationStatus.NOT_STARTED
    assert booking.preparation_notes is None


def test_the_next_update_replaces_the_details_and_notes_may_be_left_out(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    booking = _approved_booking(venue, saved_event(), db_session)
    _record(booking, IN_PROGRESS, db_session)

    _record(booking, {"status": "ready"}, db_session)

    assert booking.preparation_status is PreparationStatus.READY
    assert booking.preparation_notes is None


def test_the_coordinator_reads_the_details_on_their_events_bookings(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC2: through the coordinator's list of the event's booking requests."""
    event = saved_event()
    booking = _approved_booking(venue, event, db_session)
    _record(booking, IN_PROGRESS, db_session)

    [listed] = services.list_booking_requests_for_event(
        event.reference, coordinator_id=COORDINATOR_ID, session=db_session
    )

    assert listed.request.preparation_status is PreparationStatus.IN_PROGRESS
    assert listed.request.preparation_notes == "Chairs set out, stage to do."


def test_other_internal_users_read_the_details_in_the_events_history(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC2: the history entry carries the status and notes for every internal role."""
    event = saved_event()
    booking = _approved_booking(venue, event, db_session)
    _record(booking, IN_PROGRESS, db_session)

    history = event_services.list_event_history(
        99, event.reference, viewer_role=Role.TECHNICAL_SUPPORT_STAFF, session=db_session
    )

    [entry] = [
        shown for shown in history if shown.kind is EventHistoryKind.VENUE_PREPARATION_UPDATED
    ]
    assert entry.details["status"] == "in_progress"
    assert entry.details["notes"] == "Chairs set out, stage to do."


@pytest.mark.parametrize("field", ["purpose", "venue_id", "event_id", "decision_reason"])
def test_any_other_field_of_the_booking_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent, field: str
) -> None:
    """AC3: the payload carries the preparation details and nothing else."""
    booking = _approved_booking(venue, saved_event(), db_session)

    with pytest.raises(ValidationError) as caught:
        _record(booking, {**IN_PROGRESS, field: "x"}, db_session)

    assert set(caught.value.details) == {field}
    assert booking.purpose == "Main hall"


def test_each_update_records_who_and_when(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC4: one history entry per update, with the user, the time and the details."""
    booking = _approved_booking(venue, saved_event(), db_session)
    before = datetime.now(UTC)

    _record(booking, IN_PROGRESS, db_session)
    _record(booking, {"status": "ready"}, db_session)

    first, second = _preparation_entries(db_session)
    assert first.actor_id == VENUE_STAFF_ID
    assert first.occurred_at.replace(tzinfo=UTC) >= before
    assert first.details == {
        "venue_booking_request_id": booking.id,
        "venue_id": venue.id,
        "status": "in_progress",
        "notes": "Chairs set out, stage to do.",
    }
    assert second.details["status"] == "ready"


def test_nothing_is_recorded_before_the_safety_officer_approves(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC5."""
    booking = _approved_booking(venue, saved_event(), db_session, safety_approved=False)

    with pytest.raises(ConflictError) as caught:
        _record(booking, IN_PROGRESS, db_session)

    assert caught.value.message == services.PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE
    assert booking.preparation_status is PreparationStatus.NOT_STARTED
    assert _preparation_entries(db_session) == []


@pytest.mark.parametrize("status", NOT_APPROVED_STATUSES, ids=lambda status: status.value)
def test_only_an_approved_booking_takes_preparation_details(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    status: BookingRequestStatus,
) -> None:
    # The status is written straight into the row, so a withdrawn booking (one the
    # coordinator retracted after its approval) is tested as well.
    event = saved_event()
    booking = raise_booking(venue, event, db_session)
    booking.status = status
    db_session.commit()
    approve_safety(event, db_session)

    with pytest.raises(ConflictError) as caught:
        _record(booking, IN_PROGRESS, db_session)

    expected = services.PREPARATION_NOT_APPROVED_MESSAGE.format(status=status.value)
    assert caught.value.message == expected
    assert _preparation_entries(db_session) == []


def test_notes_of_the_maximum_length_are_kept_and_one_more_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    booking = _approved_booking(venue, saved_event(), db_session)

    _record(booking, {"status": "ready", "notes": f" {'x' * 1000} "}, db_session)
    with pytest.raises(ValidationError) as caught:
        _record(booking, {"status": "ready", "notes": "x" * 1001}, db_session)

    assert booking.preparation_notes == "x" * 1000
    assert caught.value.details == {"notes": ["Notes must be at most 1000 characters."]}


def test_an_unknown_booking_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        services.update_preparation_details(
            404, IN_PROGRESS, updated_by=VENUE_STAFF_ID, session=db_session
        )


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"notes": "Chairs set out."}, "status"),
        ({"status": "finished"}, "status"),
        ({"status": "ready", "notes": "   "}, "notes"),
    ],
    ids=["no status", "unknown status", "blank notes"],
)
def test_an_invalid_payload_is_a_400_naming_the_field(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    payload: dict[str, str],
    field: str,
) -> None:
    booking = _approved_booking(venue, saved_event(), db_session)

    with pytest.raises(ValidationError) as caught:
        _record(booking, payload, db_session)

    assert set(caught.value.details) == {field}
    assert _preparation_entries(db_session) == []
