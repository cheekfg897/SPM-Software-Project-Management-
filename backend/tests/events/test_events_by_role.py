"""Service tests for SCRUM-24 "see the events my role is involved in".

AC2: an Event Coordinator sees only the events assigned to them; a request no
coordinator has doesn't appear in their list (Week 7, ADR-0034). AC4: Venue Staff see
every event that has a venue booking request or a booking, whatever its status, the
same list for all of them; a withdrawn or released request no longer counts
(ADR-0085). AC5: Technical Support see every event that has an equipment request,
whatever its status or date.
AC9: a coordinator can open a request assigned to them in full; any other request,
assigned to someone else or to no one, is not found to them.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import (
    CoordinatorContact,
    get_event_record_for_coordinator,
    list_event_requests_for_coordinator,
    list_event_requests_with_equipment,
    list_event_requests_with_venue_bookings,
)
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.events.cases import (
    ACTIVE_ARRANGEMENT_STATUSES,
    RETIRED_ARRANGEMENT_STATUSES,
    SaveArrangement,
)

pytestmark = pytest.mark.scrum_24

MakeEventRequest = Callable[..., EventRequest]
MakeEquipmentLine = Callable[..., EventEquipmentLine]
EventNeeding = Callable[..., EventRequest]
EventWithVenueRequest = Callable[..., EventRequest]
Save = Callable[..., None]


def _references(event_requests: list[EventRequest]) -> list[str]:
    """The listed requests' references, in the order listed."""
    return [event_request.reference for event_request in event_requests]


@pytest.fixture()
def event_with_venue_request(
    make_event_request: MakeEventRequest,
    venue: Venue,
    save: Save,
    save_arrangement: SaveArrangement,
) -> EventWithVenueRequest:
    """Factory: save an approved event with one Pending venue booking request."""

    def _save(
        reference: str = "EVR-AAAAAAAA",
        *,
        request_status: BookingRequestStatus = BookingRequestStatus.PENDING,
        status: EventRequestStatus = EventRequestStatus.APPROVED,
    ) -> EventRequest:
        event_request = make_event_request(reference=reference, status=status, coordinator_id=3)
        save(event_request)
        save_arrangement(event_request, venue, request_status)
        return event_request

    return _save


def _assert_not_found(exc_info: pytest.ExceptionInfo[NotFoundError]) -> None:
    """The request is refused the same way an unknown reference is (ADR-0012)."""
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."


# --------------------------------------------------------------------------
# AC2 — a coordinator's list holds only the events assigned to them
# --------------------------------------------------------------------------


def test_a_coordinators_list_leaves_out_a_request_no_coordinator_has(
    save: Save, make_event_request: MakeEventRequest
) -> None:
    save(
        make_event_request(reference="EVR-AAAAAAAA", coordinator_id=3),
        make_event_request(reference="EVR-BBBBBBBB", coordinator_id=None),
    )

    assert _references(list_event_requests_for_coordinator(3)) == ["EVR-AAAAAAAA"]


# --------------------------------------------------------------------------
# AC4 — the events that have a venue booking request or a booking
# --------------------------------------------------------------------------


def test_events_with_a_venue_booking_request_are_listed_newest_first(
    event_with_venue_request: EventWithVenueRequest,
    save: Save,
    make_event_request: MakeEventRequest,
) -> None:
    event_with_venue_request("EVR-AAAAAAAA")
    save(make_event_request(reference="EVR-BBBBBBBB"))
    event_with_venue_request("EVR-CCCCCCCC")

    listed = list_event_requests_with_venue_bookings()

    assert _references(listed) == ["EVR-CCCCCCCC", "EVR-AAAAAAAA"]


def test_an_event_with_several_venue_requests_is_listed_once(
    event_with_venue_request: EventWithVenueRequest,
    venue: Venue,
    save_arrangement: SaveArrangement,
) -> None:
    event_request = event_with_venue_request()
    save_arrangement(event_request, venue, BookingRequestStatus.APPROVED)

    assert _references(list_event_requests_with_venue_bookings()) == ["EVR-AAAAAAAA"]


@pytest.mark.parametrize(
    "request_status", ACTIVE_ARRANGEMENT_STATUSES, ids=lambda status: status.value
)
def test_an_event_is_listed_whatever_venue_staff_made_of_its_request(
    event_with_venue_request: EventWithVenueRequest, request_status: BookingRequestStatus
) -> None:
    """An approved request is a booking; the others are still booking requests."""
    event_with_venue_request(request_status=request_status)

    assert _references(list_event_requests_with_venue_bookings()) == ["EVR-AAAAAAAA"]


@pytest.mark.parametrize(
    "request_status", RETIRED_ARRANGEMENT_STATUSES, ids=lambda status: status.value
)
def test_an_event_whose_only_request_is_retired_is_not_listed(
    event_with_venue_request: EventWithVenueRequest, request_status: BookingRequestStatus
) -> None:
    event_with_venue_request(request_status=request_status)

    assert list_event_requests_with_venue_bookings() == []


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_an_event_with_a_venue_request_is_listed_whatever_its_status(
    event_with_venue_request: EventWithVenueRequest, status: EventRequestStatus
) -> None:
    event_with_venue_request(status=status)

    assert _references(list_event_requests_with_venue_bookings()) == ["EVR-AAAAAAAA"]


# --------------------------------------------------------------------------
# AC5 — the events that have an equipment request
# --------------------------------------------------------------------------


def test_events_with_an_equipment_request_are_listed_newest_first(
    event_needing: EventNeeding, save: Save, make_event_request: MakeEventRequest
) -> None:
    event_needing("EVR-AAAAAAAA")
    save(make_event_request(reference="EVR-BBBBBBBB"))
    event_needing("EVR-CCCCCCCC")

    assert _references(list_event_requests_with_equipment()) == ["EVR-CCCCCCCC", "EVR-AAAAAAAA"]


def test_an_event_with_several_lines_is_listed_once(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Save,
) -> None:
    save(make_equipment_line(saved_event_request, equipment_type))
    save(make_equipment_line(saved_event_request, microphone))

    assert _references(list_event_requests_with_equipment()) == ["EVR-AAAAAAAA"]


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_an_event_with_equipment_is_listed_whatever_its_status(
    event_needing: EventNeeding, status: EventRequestStatus
) -> None:
    event_needing(status=status)

    assert _references(list_event_requests_with_equipment()) == ["EVR-AAAAAAAA"]


def test_an_event_that_has_taken_place_is_still_listed(event_needing: EventNeeding) -> None:
    event_needing(proposed_date=date(2026, 1, 10))

    assert _references(list_event_requests_with_equipment()) == ["EVR-AAAAAAAA"]


# --------------------------------------------------------------------------
# AC9 — a coordinator opens only a request assigned to them
# --------------------------------------------------------------------------


def test_a_coordinator_opens_a_request_assigned_to_them(
    saved_users: list[User],
    saved_event_request: EventRequest,
    coordinator_three: CoordinatorContact,
) -> None:
    record = get_event_record_for_coordinator(3, "EVR-AAAAAAAA")

    assert record.event_request.reference == "EVR-AAAAAAAA"
    assert record.coordinator == coordinator_three


def test_a_coordinator_cannot_open_another_coordinators_request(
    saved_event_request: EventRequest,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        get_event_record_for_coordinator(9, "EVR-AAAAAAAA")

    _assert_not_found(exc_info)


@pytest.mark.parametrize("status", list(EventRequestStatus), ids=lambda status: status.value)
def test_a_coordinator_cannot_open_a_request_no_coordinator_has(
    save: Save, make_event_request: MakeEventRequest, status: EventRequestStatus
) -> None:
    """Submitted included: the unassigned queue is the Lead's (SCRUM-95), not theirs."""
    save(make_event_request(status=status, coordinator_id=None))

    with pytest.raises(NotFoundError) as exc_info:
        get_event_record_for_coordinator(3, "EVR-AAAAAAAA")

    _assert_not_found(exc_info)
