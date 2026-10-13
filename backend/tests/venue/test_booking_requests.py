"""Unit tests for SCRUM-42 — Request a venue booking for an approved event.

This file covers the stored request: a new one is Pending (AC5) and keeps the purpose,
occupancy, layout and period it was raised with (AC3). It also covers the payload that
raises one, raising it from an approved event (AC1, AC3, AC7) with an audit entry on
the event, and the shape Venue Staff see it in, with the event's timing and
accessibility requirements alongside (AC4).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.events import services as event_services
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from app.modules.venue.schemas import (
    BookingRequestAsShown,
    RaiseBookingRequestSchema,
    VenueBookingRequestSchema,
)
from tests.venue.conftest import (
    COORDINATOR_ID,
    SavedEvent,
    booking_payload,
    raise_booking,
    saved_requests,
)

pytestmark = pytest.mark.scrum_42

STARTS_AT = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
ENDS_AT = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
UNSUITABLE_MESSAGE = "A justification is required because the venue is not suitable."
DUPLICATE_MESSAGE = "A pending request for this event, venue and period already exists."
LATER_PERIOD = {
    "starts_at": "2026-11-02T09:00:00+08:00",
    "ends_at": "2026-11-02T12:00:00+08:00",
}


def _load(**overrides: Any) -> dict[str, Any]:
    return load_or_raise(RaiseBookingRequestSchema(), booking_payload(**overrides))


def _request() -> VenueBookingRequest:
    return VenueBookingRequest(
        id=9,
        event_id=1,
        venue_id=3,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        purpose="Main hall",
        expected_occupancy=150,
        required_layout="theatre",
        justification=None,
        status=BookingRequestStatus.PENDING,
        requested_by=7,
    )


def _history(session: Session) -> list[EventHistoryEntry]:
    return session.query(EventHistoryEntry).all()


def _list(event: EventRequest, session: Session, coordinator_id: int = COORDINATOR_ID) -> Any:
    return services.list_booking_requests_for_event(
        event.reference, coordinator_id=coordinator_id, session=session
    )


def test_a_new_request_is_pending(db_session: Session) -> None:
    request = VenueBookingRequest(
        event_id=1,
        venue_id=1,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        purpose="Main hall",
        expected_occupancy=150,
        required_layout="theatre",
        requested_by=1,
    )
    db_session.add(request)
    db_session.flush()

    assert request.status is BookingRequestStatus.PENDING


def test_a_saved_request_keeps_its_details_and_has_no_justification_yet(
    db_session: Session,
) -> None:
    db_session.add(
        VenueBookingRequest(
            event_id=1,
            venue_id=1,
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
            purpose="Main hall",
            expected_occupancy=150,
            required_layout=None,
            requested_by=7,
        )
    )
    db_session.commit()
    db_session.expire_all()

    saved = db_session.query(VenueBookingRequest).one()

    assert saved.starts_at == STARTS_AT
    assert saved.ends_at == ENDS_AT
    assert (saved.purpose, saved.expected_occupancy, saved.requested_by) == ("Main hall", 150, 7)
    assert saved.required_layout is None
    assert saved.justification is None


def test_a_valid_payload_loads_with_utc_instants_and_optional_fields_left_out() -> None:
    loaded = _load()

    assert loaded == {
        "venue_id": 3,
        "starts_at": datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
        "ends_at": datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        "purpose": "Main hall",
    }


def test_optional_occupancy_layout_and_justification_load_when_sent() -> None:
    loaded = _load(expected_occupancy=80, required_layout="theatre", justification="Only hall free")

    assert (loaded["expected_occupancy"], loaded["required_layout"], loaded["justification"]) == (
        80,
        "theatre",
        "Only hall free",
    )


@pytest.mark.parametrize("ends_at", ["2026-11-01T09:00:00+08:00", "2026-11-01T08:00:00+08:00"])
def test_a_request_ending_at_or_before_it_starts_is_rejected_on_ends_at(ends_at: str) -> None:
    with pytest.raises(ValidationError) as caught:
        _load(ends_at=ends_at)

    assert caught.value.details == {"ends_at": ["ends_at must be after starts_at."]}


def test_a_purpose_of_only_whitespace_is_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        _load(purpose="   ")

    assert caught.value.details == {"purpose": ["Must not be blank."]}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("justification", "  ", "Must not be blank."),
        ("expected_occupancy", 0, "expected_occupancy must be a positive number."),
    ],
    ids=["blank-justification", "zero-occupancy"],
)
def test_a_blank_justification_or_an_occupancy_below_one_is_rejected(
    field: str, value: Any, message: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        _load(**{field: value})

    assert caught.value.details == {field: [message]}


def test_a_layout_the_venues_do_not_offer_is_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        _load(required_layout="amphitheatre")

    assert list(caught.value.details) == ["required_layout"]


def test_a_request_is_shown_with_the_events_timing_and_accessibility_needs() -> None:
    shown = BookingRequestAsShown(
        request=_request(),
        proposed_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
        start_time=time(9, 0),
        end_time=time(17, 30),
        accessibility_needs="Step-free entrance",
    )

    assert VenueBookingRequestSchema().dump(shown) == {
        "id": 9,
        "event_id": 1,
        "venue_id": 3,
        "starts_at": "2026-11-01T17:00:00+08:00",
        "ends_at": "2026-11-01T20:00:00+08:00",
        "purpose": "Main hall",
        "expected_occupancy": 150,
        "required_layout": "theatre",
        "justification": None,
        "status": "pending",
        "event_proposed_date": "2026-11-01",
        "event_end_date": "2026-11-02",
        "event_start_time": "09:00:00",
        "event_end_time": "17:30:00",
        "accessibility_needs": "Step-free entrance",
    }


# --------------------------------------------------------------------------
# AC1, AC3, AC7 — raising a request from an approved event
# --------------------------------------------------------------------------


def test_occupancy_and_layout_default_to_the_events(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()

    request = raise_booking(venue, event, db_session)

    assert (request.expected_occupancy, request.required_layout) == (80, None)
    assert request.status is BookingRequestStatus.PENDING
    assert (request.event_id, request.venue_id, request.requested_by) == (
        event.id,
        venue.id,
        COORDINATOR_ID,
    )
    assert (request.purpose, request.starts_at, request.ends_at, request.justification) == (
        "Main hall",
        datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
        datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        None,
    )
    assert saved_requests(db_session) == [request]


def test_occupancy_and_layout_sent_override_the_events(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(
        venue, saved_event(), db_session, expected_occupancy=60, required_layout="theatre"
    )

    assert (request.expected_occupancy, request.required_layout) == (60, "theatre")


def test_an_unsuitable_venue_needs_a_justification_on_that_field(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The event's 80 fit the venue's 100; the request's own 150 do not."""
    with pytest.raises(ValidationError) as caught:
        raise_booking(venue, saved_event(), db_session, expected_occupancy=150)

    assert caught.value.details == {"justification": [UNSUITABLE_MESSAGE]}


def test_a_layout_the_venue_lacks_needs_a_justification(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    with pytest.raises(ValidationError) as caught:
        raise_booking(venue, saved_event(), db_session, required_layout="boardroom")

    assert caught.value.details == {"justification": [UNSUITABLE_MESSAGE]}


def test_an_unsuitable_venue_is_accepted_with_a_justification(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(
        venue, saved_event(), db_session, expected_occupancy=150, justification="Only hall free"
    )

    assert request.justification == "Only hall free"
    assert saved_requests(db_session) == [request]


def test_suitability_uses_the_requests_occupancy_not_the_events(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """The event's 80 would not fit this venue's 60; the request's own 50 does."""
    small_venue = make_venue(capacity=60)
    save(small_venue)

    request = raise_booking(small_venue, saved_event(), db_session, expected_occupancy=50)

    assert request.justification is None


def test_an_unknown_venue_is_a_validation_error_on_venue_id(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    with pytest.raises(ValidationError) as caught:
        raise_booking(venue, saved_event(), db_session, venue_id=999)

    assert caught.value.details == {"venue_id": ["Venue not found."]}


def test_an_event_that_is_not_approved_is_refused_naming_its_status(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event(EventRequestStatus.SUBMITTED)

    with pytest.raises(ConflictError) as caught:
        raise_booking(venue, event, db_session)

    assert caught.value.message == (
        "Only an approved event can have a venue booking request; this one is submitted."
    )
    assert saved_requests(db_session) == []


@pytest.mark.parametrize("coordinator_id", [9, None], ids=["other-coordinator", "unassigned"])
def test_a_coordinator_who_is_not_assigned_to_the_event_gets_not_found(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    coordinator_id: int | None,
) -> None:
    event = saved_event()
    event.coordinator_id = coordinator_id
    db_session.commit()

    with pytest.raises(NotFoundError):
        services.raise_booking_request(
            event.reference,
            booking_payload(venue_id=venue.id),
            requested_by=COORDINATOR_ID,
            session=db_session,
        )


def test_an_unknown_event_gets_not_found(db_session: Session, venue: Venue) -> None:
    with pytest.raises(NotFoundError):
        services.raise_booking_request(
            "EVR-NOSUCH00",
            booking_payload(venue_id=venue.id),
            requested_by=COORDINATOR_ID,
            session=db_session,
        )


def test_a_request_is_stored_against_the_events_internal_id(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()

    request = raise_booking(venue, event, db_session)

    assert request.event_id == event.id


def test_the_event_reference_is_matched_ignoring_case_and_spaces(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    typed = f"  {event.reference.lower()} "

    shown = services.raise_booking_request(
        typed, booking_payload(venue_id=venue.id), requested_by=COORDINATOR_ID, session=db_session
    )

    assert shown.request.event_id == event.id


# --------------------------------------------------------------------------
# Audit trail — the event's history records each request, in the same commit
# --------------------------------------------------------------------------


def test_raising_a_request_records_it_in_the_events_history(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()

    request = raise_booking(venue, event, db_session)
    db_session.rollback()  # throws away anything that was not committed

    [entry] = _history(db_session)
    assert entry.event_request_id == event.id
    assert entry.kind is EventHistoryKind.VENUE_BOOKING_REQUESTED
    assert entry.actor_id == COORDINATOR_ID
    assert entry.details == {
        "venue_booking_request_id": request.id,
        "venue_id": venue.id,
        "starts_at": "2026-11-01T01:00:00+00:00",
        "ends_at": "2026-11-01T04:00:00+00:00",
    }


@pytest.mark.parametrize(
    "overrides",
    [{"expected_occupancy": 150}, {"venue_id": 999}],
    ids=["unsuitable-without-justification", "unknown-venue"],
)
def test_a_refused_request_records_nothing(
    db_session: Session, venue: Venue, saved_event: SavedEvent, overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        raise_booking(venue, saved_event(), db_session, **overrides)

    assert saved_requests(db_session) == []
    assert _history(db_session) == []


def test_a_request_for_an_event_that_is_not_approved_records_nothing(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    with pytest.raises(ConflictError):
        raise_booking(venue, saved_event(EventRequestStatus.SUBMITTED), db_session)

    assert _history(db_session) == []


# --------------------------------------------------------------------------
# AC6, AC2 — no second Pending request for the same event, venue and period
# --------------------------------------------------------------------------


def test_a_second_pending_request_for_the_same_event_venue_and_period_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    first = raise_booking(venue, event, db_session)

    with pytest.raises(ConflictError) as raised:
        raise_booking(venue, event, db_session)

    assert raised.value.message == DUPLICATE_MESSAGE
    # The refused attempt was rolled back, so only the first is kept.
    assert saved_requests(db_session) == [first]
    assert len(_history(db_session)) == 1


def test_the_same_event_and_venue_at_a_different_period_is_saved(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    raise_booking(venue, event, db_session)

    raise_booking(venue, event, db_session, ends_at="2026-11-01T13:00:00+08:00")

    assert len(saved_requests(db_session)) == 2


def test_the_same_event_at_a_different_venue_and_overlapping_time_is_saved(
    db_session: Session,
    venue: Venue,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    other_venue = make_venue(name="Annex")
    save(other_venue)
    event = saved_event()
    raise_booking(venue, event, db_session)

    raise_booking(other_venue, event, db_session)

    assert len(saved_requests(db_session)) == 2


def test_an_integrity_error_that_is_not_the_duplicate_is_not_turned_into_a_conflict(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    other_violation = IntegrityError("INSERT", {}, Exception("CHECK constraint failed: other"))

    with patch.object(db_session, "commit", side_effect=other_violation):
        with pytest.raises(IntegrityError):
            raise_booking(venue, event, db_session)

    assert saved_requests(db_session) == []


# --------------------------------------------------------------------------
# AC4 — showing a request with its event's details
# --------------------------------------------------------------------------


def test_a_request_is_shown_with_the_event_it_was_raised_from(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    request = raise_booking(venue, event, db_session)
    event_details = event_services.get_approved_event_for_coordinator(
        event.reference, COORDINATOR_ID, session=db_session
    )

    shown = services.show_booking_request(request, event_details)

    assert shown == BookingRequestAsShown(
        request=request,
        proposed_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
        start_time=time(9, 0),
        end_time=time(17, 30),
        accessibility_needs="Step-free entrance",
    )


def test_a_raised_request_comes_back_with_the_events_details(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()

    shown = services.raise_booking_request(
        event.reference,
        booking_payload(venue_id=venue.id),
        requested_by=COORDINATOR_ID,
        session=db_session,
    )

    assert shown.request in saved_requests(db_session)
    assert shown.start_time == time(9, 0)
    assert shown.accessibility_needs == "Step-free entrance"


# --------------------------------------------------------------------------
# Listing the requests raised for an event
# --------------------------------------------------------------------------


def test_only_this_events_requests_are_listed_in_period_order(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    other_event = saved_event()
    later = raise_booking(venue, event, db_session, **LATER_PERIOD)
    earlier = raise_booking(venue, event, db_session)
    raise_booking(venue, other_event, db_session)

    listed = _list(event, db_session)

    assert [shown.request for shown in listed] == [earlier, later]


def test_listed_requests_show_the_events_timing_and_accessibility_needs(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    request = raise_booking(venue, event, db_session)

    assert _list(event, db_session) == [
        BookingRequestAsShown(
            request=request,
            proposed_date=date(2026, 11, 1),
            end_date=date(2026, 11, 2),
            start_time=time(9, 0),
            end_time=time(17, 30),
            accessibility_needs="Step-free entrance",
        )
    ]


def test_an_event_that_has_moved_on_from_approved_still_lists_its_requests(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    request = raise_booking(venue, event, db_session)
    event.status = EventRequestStatus.CONFIRMED
    db_session.commit()

    assert [shown.request for shown in _list(event, db_session)] == [request]


def test_another_coordinator_cannot_list_the_events_requests(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    raise_booking(venue, event, db_session)

    with pytest.raises(NotFoundError):
        _list(event, db_session, coordinator_id=9)


def test_the_same_venue_and_period_can_be_requested_again_after_a_withdrawal(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """Withdrawing frees the slot: the pending index covers pending rows only."""
    event = saved_event()
    first = raise_booking(venue, event, db_session)
    services.withdraw_arrangement(
        event.reference, first.id, coordinator_id=COORDINATOR_ID, session=db_session
    )

    second = raise_booking(venue, event, db_session)

    assert second.id != first.id
    assert len(saved_requests(db_session)) == 2
