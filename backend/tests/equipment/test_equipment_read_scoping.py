"""Unit tests for who may read an event's equipment (SCRUM-45; SCRUM-46 AC4).

What is free for an event and what is reserved for it are scoped like the event's
equipment lines (ADR-0019, ADR-0037): Technical Support Staff read any event's, an
Event Coordinator only an event assigned to them. Another coordinator's event, or one
with no coordinator, is the same 404 as a reference that doesn't exist (ADR-0012,
ADR-0034). Which roles reach these services at all is the routes' job
(``test_equipment_reservation_permissions.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from app.common.errors import NotFoundError
from app.modules.auth.permissions import Role
from app.modules.equipment import services
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.events.models import EventRequest

pytestmark = [pytest.mark.scrum_45, pytest.mark.scrum_46]

Save = Callable[..., None]
MakeReservation = Callable[[EquipmentType, int, datetime, datetime], EquipmentReservation]
#: A read of the event's equipment as a viewer, summarised as (type name, units).
Read = Callable[[int, Role], list[tuple[str, int]]]

REFERENCE = "EVR-AAAAAAAA"
#: ``make_event_request`` runs 09:00-17:00 in Singapore on 15 October 2026.
EVENT_STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
EVENT_ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
ASSIGNED_COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
TECHNICAL_SUPPORT_ID = 5


def _units_available(viewer_id: int, viewer_role: Role) -> list[tuple[str, int]]:
    rows = services.equipment_availability_for_event(viewer_id, REFERENCE, viewer_role=viewer_role)
    return [(row.equipment_type_name, row.available) for row in rows]


def _units_reserved(viewer_id: int, viewer_role: Role) -> list[tuple[str, int]]:
    rows = services.list_reservations_for_event(viewer_id, REFERENCE, viewer_role=viewer_role)
    return [(row.equipment_type_name, row.quantity) for row in rows]


# Ten projectors held and four reserved for the event: six free, four reserved.
READS_AND_WHAT_THEY_SHOW = [
    pytest.param(_units_available, [("Projector", 6)], id="availability"),
    pytest.param(_units_reserved, [("Projector", 4)], id="reservations"),
]
READS = [
    pytest.param(_units_available, id="availability"),
    pytest.param(_units_reserved, id="reservations"),
]


@pytest.fixture()
def event_with_four_reserved(
    make_event_request: Callable[..., EventRequest],
    equipment_type: EquipmentType,
    make_reservation: MakeReservation,
    save: Save,
) -> Callable[[int | None], None]:
    """Save the event for the coordinator given, with four projectors reserved."""

    def _save(coordinator_id: int | None) -> None:
        event_request = make_event_request(coordinator_id=coordinator_id)
        save(event_request)
        reservation = make_reservation(equipment_type, 4, EVENT_STARTS_AT, EVENT_ENDS_AT)
        reservation.event_id = event_request.id
        save(reservation)

    return _save


@pytest.mark.parametrize(("read", "shown"), READS_AND_WHAT_THEY_SHOW)
def test_the_assigned_coordinator_reads_their_events_equipment(
    event_with_four_reserved: Callable[[int | None], None],
    read: Read,
    shown: list[tuple[str, int]],
) -> None:
    event_with_four_reserved(ASSIGNED_COORDINATOR_ID)

    assert read(ASSIGNED_COORDINATOR_ID, Role.EVENT_COORDINATOR) == shown


@pytest.mark.parametrize(("read", "shown"), READS_AND_WHAT_THEY_SHOW)
def test_technical_support_read_an_event_nobody_is_assigned_to(
    event_with_four_reserved: Callable[[int | None], None],
    read: Read,
    shown: list[tuple[str, int]],
) -> None:
    event_with_four_reserved(None)

    assert read(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF) == shown


@pytest.mark.parametrize("read", READS)
@pytest.mark.parametrize(
    ("coordinator_id", "assigned_to"),
    [
        pytest.param(OTHER_COORDINATOR_ID, ASSIGNED_COORDINATOR_ID, id="another-coordinators"),
        pytest.param(ASSIGNED_COORDINATOR_ID, None, id="unassigned"),
    ],
)
def test_a_coordinator_is_told_an_event_not_assigned_to_them_does_not_exist(
    event_with_four_reserved: Callable[[int | None], None],
    read: Read,
    coordinator_id: int,
    assigned_to: int | None,
) -> None:
    event_with_four_reserved(assigned_to)

    with pytest.raises(NotFoundError) as exc_info:
        read(coordinator_id, Role.EVENT_COORDINATOR)

    assert exc_info.value.message == "Event request not found."
