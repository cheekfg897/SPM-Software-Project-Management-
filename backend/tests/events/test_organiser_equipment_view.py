"""Unit tests for what an Event Organiser sees of their event's equipment.

SCRUM-37 AC5 and SCRUM-48 AC5 (ADR-0098): the organiser's own record shows each
equipment line's type by name, the quantity requested, the status and, once Technical
Support have recorded an outcome, the quantity provided. The line's technical notes,
the outcome note and the reviewer stay internal, so the organiser's record leaves them
out; the coordinator's record still shows the notes (SCRUM-37 AC5's internal staff).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import EquipmentLineStatus, EventEquipmentLine, EventRequest
from app.modules.events.schemas import EventRequestDetailSchema, OrganiserEquipmentLineSchema
from app.modules.events.services import (
    EquipmentLineForOrganiser,
    OrganiserEventRecord,
    get_event_record_for_coordinator,
    get_event_record_for_organiser,
)

pytestmark = [pytest.mark.scrum_37, pytest.mark.scrum_48]

ORGANISER_ID = 7
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5
REFERENCE = "EVR-AAAAAAAA"
SIX_OF_TEN = EquipmentLineForOrganiser(
    id=7,
    equipment_type_name="Projector",
    quantity=10,
    status=EquipmentLineStatus.PARTIALLY_FULFILLED,
    provided_quantity=6,
)


def _record_outcome(
    line: EventEquipmentLine, status: EquipmentLineStatus, provided_quantity: int, note: str
) -> None:
    """Give ``line`` an outcome from Technical Support, with its note and reviewer."""
    line.status = status
    line.provided_quantity = provided_quantity
    line.outcome_note = note
    line.reviewed_by = TECHNICAL_SUPPORT_ID
    line.reviewed_at = datetime(2026, 10, 13, 9, 30, tzinfo=UTC)


@pytest.fixture()
def six_of_ten_provided(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> EventEquipmentLine:
    """Ten projectors noted "Needs HDMI", six to be provided, noted and reviewed."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    _record_outcome(line, EquipmentLineStatus.PARTIALLY_FULFILLED, 6, "Only six in stock")
    save(line)
    return line


@pytest.fixture()
def microphones_requested(
    saved_event_request: EventRequest,
    make_equipment_type: Callable[..., EquipmentType],
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> EventEquipmentLine:
    """Two microphones on the same event, not reviewed yet."""
    microphone = make_equipment_type(name="Microphone")
    save(microphone)
    line = make_equipment_line(saved_event_request, microphone, notes="Lapel, not handheld")
    save(line)
    return line


@pytest.fixture()
def another_events_line(
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
) -> EventEquipmentLine:
    """A line on another of the organiser's events, which must not show on this one."""
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(other_event)
    line = make_equipment_line(other_event, equipment_type, quantity=1)
    save(line)
    return line


# --------------------------------------------------------------------------
# The organiser's record (SCRUM-37 AC5, SCRUM-48 AC5)
# --------------------------------------------------------------------------


def test_the_organisers_record_shows_each_line_by_name_with_what_will_be_provided(
    saved_users: list[User],
    six_of_ten_provided: EventEquipmentLine,
    microphones_requested: EventEquipmentLine,
    another_events_line: EventEquipmentLine,
) -> None:
    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)

    assert record.equipment_lines == (
        EquipmentLineForOrganiser(
            id=six_of_ten_provided.id,
            equipment_type_name="Projector",
            quantity=10,
            status=EquipmentLineStatus.PARTIALLY_FULFILLED,
            provided_quantity=6,
        ),
        EquipmentLineForOrganiser(
            id=microphones_requested.id,
            equipment_type_name="Microphone",
            quantity=2,
            status=EquipmentLineStatus.REQUESTED,
            provided_quantity=None,
        ),
    )


@pytest.mark.parametrize(
    ("status", "provided_quantity", "note"),
    [
        (EquipmentLineStatus.FULFILLED, 10, "Spare bulbs packed too."),
        (EquipmentLineStatus.PARTIALLY_FULFILLED, 6, "Only six in stock"),
        (EquipmentLineStatus.UNAVAILABLE, 0, "All ten are out for repair."),
    ],
    ids=["fulfilled", "partially_fulfilled", "unavailable"],
)
def test_the_organiser_is_sent_the_quantity_provided_for_every_outcome_but_never_the_note(
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
    status: EquipmentLineStatus,
    provided_quantity: int,
    note: str,
) -> None:
    """ADR-0098 decision 4. A fulfilled line can carry a note too (SCRUM-48 AC2)."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=10)
    _record_outcome(line, status, provided_quantity, note)
    save(line)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)
    shown = OrganiserEquipmentLineSchema().dump(record.equipment_lines, many=True)

    assert shown == [
        {
            "id": line.id,
            "equipment_type_name": "Projector",
            "quantity": 10,
            "status": status.value,
            "provided_quantity": provided_quantity,
        }
    ]


def test_the_organisers_record_of_an_event_with_no_equipment_has_no_lines(
    saved_users: list[User],
    saved_event_request: EventRequest,
    another_events_line: EventEquipmentLine,
) -> None:
    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)

    assert record.equipment_lines == ()


def test_the_organisers_record_keeps_the_sections_every_record_shows(
    saved_users: list[User], six_of_ten_provided: EventEquipmentLine
) -> None:
    """The request and its coordinator come through as on the coordinator's record."""
    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)
    coordinators = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE)

    assert record.event_request is coordinators.event_request
    assert (record.coordinator, record.decision, record.clarifications) == (
        coordinators.coordinator,
        coordinators.decision,
        coordinators.clarifications,
    )


# --------------------------------------------------------------------------
# How the record route shows the lines to each role
# --------------------------------------------------------------------------


def test_the_organisers_record_route_shows_no_notes_outcome_note_or_reviewer(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
    shown_line: EventEquipmentLine,
) -> None:
    """The event has a line noted "Needs HDMI"; the organiser gets their view of it."""
    event_request = make_event_request()
    event_request.equipment_lines = [shown_line]
    record = OrganiserEventRecord(
        event_request=event_request, coordinator=None, equipment_lines=(SIX_OF_TEN,)
    )

    body = open_record_route(record)

    assert body["equipment_lines"] == [
        {
            "id": 7,
            "equipment_type_name": "Projector",
            "quantity": 10,
            "status": "partially_fulfilled",
            "provided_quantity": 6,
        }
    ]


def test_the_coordinators_record_still_shows_each_lines_notes(
    saved_users: list[User], six_of_ten_provided: EventEquipmentLine, equipment_type: EquipmentType
) -> None:
    """The coordinator is internal staff, so their record keeps the technical notes."""
    record = get_event_record_for_coordinator(COORDINATOR_ID, REFERENCE)

    shown = EventRequestDetailSchema().dump(record.event_request)

    assert shown["equipment_lines"] == [
        {
            "id": six_of_ten_provided.id,
            "equipment_type_id": equipment_type.id,
            "quantity": 10,
            "notes": "Needs HDMI",
            "status": "partially_fulfilled",
        }
    ]
