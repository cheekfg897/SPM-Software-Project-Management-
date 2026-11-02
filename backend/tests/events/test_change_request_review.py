"""Unit tests for SCRUM-57 AC1 and AC6: what the coordinator reviews, and who sees it.

AC1: the coordinator sees the requested change beside the event's current values,
every venue booking for the event, and its equipment reservations. The record they open
holds the change request, with each field's value when it was raised and the value
asked for, beside the event's own (current) values and every venue arrangement in any
status; the reservations come from the equipment module's list for the event, which the
assigned coordinator may read (ADR-0037, ADR-0127). AC6: the staff record shows the
change requests too, so whoever opens the event sees one Approved or Rejected.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7's, assigned to Event Coordinator 3).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentReservation
from app.modules.equipment.services import list_reservations_for_event
from app.modules.events import routes
from app.modules.events.models import ChangeRequestStatus, EventChangeRequest, EventRequest
from app.modules.events.services import (
    ChangeRequestAsShown,
    EventRecord,
    RequestedChange,
    StaffEventRecord,
    get_event_record_for_coordinator,
    get_staff_event_record,
)
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.events.cases import SaveArrangement

pytestmark = pytest.mark.scrum_57

RaiseChange = Callable[[int, Any], ChangeRequestAsShown]
CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
COORDINATOR_ID = 3
RAISED_AT = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
DECIDED_AT = datetime(2026, 9, 16, 2, 30, tzinfo=timezone.utc)
REJECTED_AS_SHOWN = ChangeRequestAsShown(
    id=4,
    status=ChangeRequestStatus.REJECTED,
    changes=(RequestedChange("expected_attendance", 250, 300),),
    reason="More partners are coming.",
    raised_by="Alice Example",
    raised_at=RAISED_AT,
    withdrawn_at=None,
    withdrawal_note=None,
    decided_by="Coordinator Three",
    decided_at=DECIDED_AT,
    decision_reason="The hall can't hold more.",
)
REJECTED_BODY = {
    "id": 4,
    "status": "rejected",
    "changes": [{"field": "expected_attendance", "previous_value": 250, "requested_value": 300}],
    "reason": "More partners are coming.",
    "raised_by": "Alice Example",
    "raised_at": "2026-09-15T09:00:00+08:00",
    "withdrawn_at": None,
    "withdrawal_note": None,
    "decided_by": "Coordinator Three",
    "decided_at": "2026-09-16T10:30:00+08:00",
    "decision_reason": "The hall can't hold more.",
}


@pytest.fixture()
def other_event(
    make_event_request: Callable[..., EventRequest], save: Callable[..., None]
) -> EventRequest:
    """Organiser 7's second event, ``EVR-BBBBBBBB``, with the same coordinator."""
    event_request = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(event_request)
    return event_request


# --------------------------------------------------------------------------
# AC1 — the change beside the current values, every venue booking and reservation
# --------------------------------------------------------------------------


def test_the_coordinator_sees_the_change_beside_the_current_values_and_every_venue(
    raise_change: RaiseChange,
    saved_event_request: EventRequest,
    other_event: EventRequest,
    venue: Venue,
    save_arrangement: SaveArrangement,
) -> None:
    approved = save_arrangement(saved_event_request, venue, BookingRequestStatus.APPROVED)
    pending = save_arrangement(saved_event_request, venue, BookingRequestStatus.PENDING)
    save_arrangement(other_event, venue, BookingRequestStatus.APPROVED)
    raised = raise_change(
        ORGANISER_ID,
        {"expected_attendance": 300, "start_time": "10:00", "reason": "Later start."},
    )

    record = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE)

    [change_request] = record.change_requests
    assert change_request.id == raised.id
    assert change_request.changes == (
        RequestedChange("start_time", "09:00:00", "10:00:00"),
        RequestedChange("expected_attendance", 250, 300),
    )
    # The event's current values sit beside them, unchanged by the request.
    current = record.event_request
    assert (current.start_time.isoformat(), current.expected_attendance) == ("09:00:00", 250)
    shown_periods = [arrangement.starts_at for arrangement in record.venue_arrangements]
    assert shown_periods == [approved.starts_at, pending.starts_at]


def test_the_coordinator_reads_every_equipment_reservation_of_the_event(
    saved_users: list[User],
    saved_event_request: EventRequest,
    other_event: EventRequest,
    reserve: Callable[[EventRequest], EquipmentReservation],
) -> None:
    first = reserve(saved_event_request)
    second = reserve(saved_event_request)
    reserve(other_event)

    reservations = list_reservations_for_event(
        COORDINATOR_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR
    )

    assert [reservation.id for reservation in reservations] == [first.id, second.id]


# --------------------------------------------------------------------------
# AC6 — the staff record shows the change requests too
# --------------------------------------------------------------------------


def test_the_staff_record_shows_the_change_requests(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: Callable[..., EventChangeRequest],
) -> None:
    rejected = save_change_request(saved_event_request, ChangeRequestStatus.REJECTED)

    staff_record = get_staff_event_record(REFERENCE)

    [shown] = staff_record.record.change_requests
    assert (shown.id, shown.status, shown.decided_by, shown.decision_reason) == (
        rejected.id,
        ChangeRequestStatus.REJECTED,
        "Coordinator Three",
        "The venue can't hold more.",
    )


def test_the_staff_record_route_shows_them_with_their_decision(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: Callable[..., str],
    make_event_request: Callable[..., EventRequest],
) -> None:
    record = EventRecord(
        event_request=make_event_request(), coordinator=None, change_requests=(REJECTED_AS_SHOWN,)
    )
    staff_record = StaffEventRecord(
        record=record,
        venue_arrangements=[],
        equipment_lines=[],
        equipment_reservations=[],
        safety_outcome=None,
    )
    replace_services(routes, {"get_staff_event_record": staff_record})

    response, status = call_route(
        "events.get_staff_record",
        "GET",
        f"/api/events/requests/{REFERENCE}/staff-record",
        {"reference": REFERENCE},
        token_for(role=Role.EVENT_COORDINATOR_LEAD),
    )

    assert status == 200
    assert response.get_json()["change_requests"] == [REJECTED_BODY]
