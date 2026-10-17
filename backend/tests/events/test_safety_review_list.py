"""Unit tests for SCRUM-97 "Submit an event for operational safety check" (B): the list.

AC5: the Safety Officer sees the events awaiting review, ordered by event date. AC6: for
each one, the information the system already holds: expected attendance; each booked
venue's capacity, room layouts, facilities and accessibility features; the event's
accessibility requirements; and the equipment requested with its quantities, technical
notes and outcomes (ADR-0047). The route is in ``test_safety_review_list_routes.py``.

The service runs against ``db_session``, so the status filter, the ordering and the
reads of the venue and equipment modules are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventRequest,
    EventRequestStatus as Status,
)
from app.modules.events.services import (
    SafetyReviewEquipment,
    list_events_awaiting_safety_review,
)
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from app.modules.venue.services import ArrangedVenue

pytestmark = pytest.mark.scrum_97

MakeEventRequest = Callable[..., EventRequest]
Save = Callable[..., None]
MakeEquipmentLine = Callable[..., EventEquipmentLine]
MakeEquipmentType = Callable[..., EquipmentType]
MakeVenue = Callable[..., Venue]
Arrange = Callable[..., VenueBookingRequest]

#: The order the references are handed out in; each event needs its own.
REFERENCES = ["EVR-AAAAAAAA", "EVR-BBBBBBBB", "EVR-CCCCCCCC", "EVR-DDDDDDDD", "EVR-EEEEEEEE"]
#: Every status but Safety Review, built from the enum so a status added later is
#: checked too.
OTHER_STATUSES = [status for status in Status if status is not Status.SAFETY_REVIEW]


@pytest.fixture()
def event_in(
    saved_users: list[object], make_event_request: MakeEventRequest, save: Save
) -> Callable[..., EventRequest]:
    """Save an event with the given status, date and start time."""
    saved: list[EventRequest] = []

    def _event_in(
        status: Status, proposed_date: date = date(2026, 11, 1), start_time: time = time(9, 0)
    ) -> EventRequest:
        event_request = make_event_request(
            reference=REFERENCES[len(saved)],
            status=status,
            coordinator_id=3,
            proposed_date=proposed_date,
            start_time=start_time,
        )
        save(event_request)
        saved.append(event_request)
        return event_request

    return _event_in


@pytest.fixture()
def arrange(save: Save) -> Arrange:
    """Save a venue arrangement, 09:00-10:00 UTC on 1 Nov 2026, approved unless told."""

    def _arrange(
        event_request: EventRequest,
        venue: Venue,
        status: BookingRequestStatus = BookingRequestStatus.APPROVED,
    ) -> VenueBookingRequest:
        arrangement = VenueBookingRequest(
            event_id=event_request.id,
            venue_id=venue.id,
            starts_at=datetime(2026, 11, 1, 9, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 1, 10, tzinfo=timezone.utc),
            purpose="Main session",
            expected_occupancy=80,
            status=status,
            requested_by=3,
        )
        save(arrangement)
        return arrangement

    return _arrange


def _references(db_session: Session) -> list[str]:
    listed = list_events_awaiting_safety_review(session=db_session)
    return [item.event_request.reference for item in listed]


# --------------------------------------------------------------------------
# AC5 — only the events in Safety Review, soonest first
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", OTHER_STATUSES, ids=lambda status: status.value)
def test_only_events_in_safety_review_are_listed(
    db_session: Session, event_in: Callable[..., EventRequest], status: Status
) -> None:
    event_in(status)
    in_review = event_in(Status.SAFETY_REVIEW)

    assert _references(db_session) == [in_review.reference]


def test_events_are_ordered_by_date_then_start_time(
    db_session: Session, event_in: Callable[..., EventRequest]
) -> None:
    later_date = event_in(Status.SAFETY_REVIEW, date(2026, 11, 20), time(9, 0))
    same_day_afternoon = event_in(Status.SAFETY_REVIEW, date(2026, 11, 5), time(14, 0))
    same_day_morning = event_in(Status.SAFETY_REVIEW, date(2026, 11, 5), time(9, 0))

    assert _references(db_session) == [
        same_day_morning.reference,
        same_day_afternoon.reference,
        later_date.reference,
    ]


# --------------------------------------------------------------------------
# AC6 — what the Safety Officer sees for each event
# --------------------------------------------------------------------------


def test_a_multi_venue_event_shows_each_venue_its_accessibility_needs_and_equipment(
    db_session: Session,
    event_in: Callable[..., EventRequest],
    make_venue: MakeVenue,
    arrange: Arrange,
    make_equipment_type: MakeEquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    event_request = event_in(Status.SAFETY_REVIEW)
    event_request.accessibility_needs = "Step-free entrance and a hearing loop"
    save(event_request)
    main_hall = make_venue()
    annex = make_venue(
        name="Annex",
        capacity=40,
        facilities="whiteboard",
        accessibility_features="hearing_loop,lift",
        supported_layouts="boardroom",
    )
    retired = make_venue(name="Old Hall")
    save(main_hall, annex, retired)
    arrange(event_request, main_hall)
    arrange(event_request, annex)
    arrange(event_request, retired, BookingRequestStatus.WITHDRAWN)
    projector = make_equipment_type(name="Projector")
    microphone = make_equipment_type(name="Microphone")
    save(projector, microphone)
    fulfilled = make_equipment_line(event_request, projector, quantity=2, notes="Needs HDMI")
    fulfilled.status = EquipmentLineStatus.FULFILLED
    fulfilled.provided_quantity = 2
    partial = make_equipment_line(event_request, microphone, quantity=4, notes=None)
    partial.status = EquipmentLineStatus.PARTIALLY_FULFILLED
    partial.provided_quantity = 3
    partial.outcome_note = "One is faulty"
    save(fulfilled, partial)

    [shown] = list_events_awaiting_safety_review(session=db_session)

    assert shown.event_request.expected_attendance == 250
    assert shown.event_request.accessibility_needs == "Step-free entrance and a hearing loop"
    assert shown.venues == [
        ArrangedVenue(
            name="Main Hall",
            capacity=100,
            layouts=["theatre", "classroom"],
            facilities=["projector", "wifi"],
            accessibility_features=["wheelchair_access"],
            starts_at=datetime(2026, 11, 1, 9, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 1, 10, tzinfo=timezone.utc),
        ),
        ArrangedVenue(
            name="Annex",
            capacity=40,
            layouts=["boardroom"],
            facilities=["whiteboard"],
            accessibility_features=["hearing_loop", "lift"],
            starts_at=datetime(2026, 11, 1, 9, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 1, 10, tzinfo=timezone.utc),
        ),
    ]
    assert shown.equipment == [
        SafetyReviewEquipment(
            equipment_type_name="Projector",
            quantity=2,
            notes="Needs HDMI",
            status=EquipmentLineStatus.FULFILLED,
            provided_quantity=2,
            outcome_note=None,
        ),
        SafetyReviewEquipment(
            equipment_type_name="Microphone",
            quantity=4,
            notes=None,
            status=EquipmentLineStatus.PARTIALLY_FULFILLED,
            provided_quantity=3,
            outcome_note="One is faulty",
        ),
    ]


def test_an_event_with_no_equipment_requests_shows_an_empty_equipment_list(
    db_session: Session,
    event_in: Callable[..., EventRequest],
    venue: Venue,
    arrange: Arrange,
) -> None:
    event_request = event_in(Status.SAFETY_REVIEW)
    arrange(event_request, venue)

    [shown] = list_events_awaiting_safety_review(session=db_session)

    assert [arranged.name for arranged in shown.venues] == ["Main Hall"]
    assert shown.equipment == []
