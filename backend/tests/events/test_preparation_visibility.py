"""Unit tests for who sees an event's preparation details (SCRUM-84 AC2, SCRUM-85 AC2).

AC2 of both stories, as changed on 25 Oct: venue and equipment preparation details are
visible to the assigned Event Coordinator, the Lead, Venue Staff, Technical Support, the
Safety Officer and the Event Organiser; Event Coordinators not assigned to the event
cannot see them. Every read that carries preparation (the coordinator's venue requests
and reservations, their record, the history) answers an unassigned coordinator as if the
event did not exist (SCRUM-24 AC12, ADR-0034); the staff record refuses every
coordinator by role (``test_staff_event_record_routes.py``). Decisions in ADR-0105.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment import services as equipment_services
from app.modules.equipment.models import EquipmentReservation, EquipmentType, PreparationStatus
from app.modules.events.models import EventRequest
from app.modules.events.services import get_event_record_for_coordinator, list_event_history
from app.modules.venue import services as venue_services
from app.modules.venue.models import BookingRequestStatus, PreparationStatus as VenuePrep
from tests.events.cases import Arrange

pytestmark = [pytest.mark.scrum_84, pytest.mark.scrum_85]

REFERENCE = "EVR-AAAAAAAA"
#: The coordinator ``saved_event_request`` is assigned to, and one it isn't.
ASSIGNED_COORDINATOR_ID = 3
UNASSIGNED_COORDINATOR_ID = 9

#: Every read a coordinator can make that carries the event's preparation details.
PREPARATION_READS: list[tuple[str, Callable[[int], Any]]] = [
    (
        "venue-requests",
        lambda viewer_id: venue_services.list_booking_requests_for_event(
            REFERENCE, coordinator_id=viewer_id
        ),
    ),
    (
        "reservations",
        lambda viewer_id: equipment_services.list_reservations_for_event(
            viewer_id, REFERENCE, viewer_role=Role.EVENT_COORDINATOR
        ),
    ),
    (
        "history",
        lambda viewer_id: list_event_history(
            viewer_id, REFERENCE, viewer_role=Role.EVENT_COORDINATOR
        ),
    ),
    ("record", lambda viewer_id: get_event_record_for_coordinator(viewer_id, REFERENCE)),
]


@pytest.fixture()
def prepared_event(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    arrange: Arrange,
    equipment_type: EquipmentType,
    save: Callable[..., None],
) -> None:
    """``saved_event_request`` with a prepared booking and a prepared reservation."""
    booking = arrange(BookingRequestStatus.APPROVED)
    booking.preparation_status = VenuePrep.READY
    booking.preparation_notes = "Stage built."
    reservation = EquipmentReservation(
        event_id=saved_event_request.id,
        equipment_type_id=equipment_type.id,
        quantity=2,
        starts_at=datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
        ends_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
        reserved_by=5,
    )
    reservation.preparation_status = PreparationStatus.READY
    reservation.preparation_notes = "Projectors tested."
    save(booking, reservation)


@pytest.mark.parametrize(
    "read", [read for _, read in PREPARATION_READS], ids=[name for name, _ in PREPARATION_READS]
)
def test_a_coordinator_not_assigned_to_the_event_sees_no_preparation(
    prepared_event: None, read: Callable[[int], Any]
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        read(UNASSIGNED_COORDINATOR_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."


def test_the_assigned_coordinator_sees_the_venue_and_equipment_preparation(
    prepared_event: None,
) -> None:
    """The positive control: the same reads answer the event's own coordinator."""
    [booking] = venue_services.list_booking_requests_for_event(
        REFERENCE, coordinator_id=ASSIGNED_COORDINATOR_ID
    )
    [reservation] = equipment_services.list_reservations_for_event(
        ASSIGNED_COORDINATOR_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR
    )

    assert booking.request.preparation_notes == "Stage built."
    assert reservation.preparation_notes == "Projectors tested."
