"""Unit tests for SCRUM-60 AC9: a new reservation never exceeds its line's quantity.

The event's reservations of a type are its line's reservation (ADR-0092), so a new one
is refused when, with those already held, it would hold more units than the line asks
for. Until Technical Support act, a reservation already held may be larger than a
lowered line, but nothing more can be added to it. A type the event has no line for is
reserved as before, up to what is free (ADR-0114, default to review).

They run against ``db_session``, so the counts are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.equipment.services import reserve_equipment
from app.modules.events.models import EventEquipmentLine, EventRequest
from app.modules.events.services import update_equipment_line

pytestmark = pytest.mark.scrum_60

Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5


def _reserve(equipment_type: EquipmentType, quantity: int) -> None:
    units = {"equipment_type_id": equipment_type.id, "quantity": quantity}
    reserve_equipment(REFERENCE, units, reserved_by=TECHNICAL_SUPPORT_ID)


def _reserved(db_session: Session) -> list[int]:
    db_session.expire_all()
    statement = select(EquipmentReservation.quantity).order_by(EquipmentReservation.id)
    return list(db_session.scalars(statement))


@pytest.fixture()
def line_of_three(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Save,
) -> EventEquipmentLine:
    """The event asks for three of the ten projectors."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=3)
    save(line)
    return line


@pytest.mark.parametrize("quantities", [[3], [2, 1]], ids=["at-once", "in-two"])
def test_the_whole_line_can_be_reserved(
    line_of_three: EventEquipmentLine,
    equipment_type: EquipmentType,
    db_session: Session,
    quantities: list[int],
) -> None:
    for quantity in quantities:
        _reserve(equipment_type, quantity)

    assert _reserved(db_session) == quantities


@pytest.mark.parametrize(
    ("held", "asked", "message"),
    [
        ([], 4, "The event asks for 3 of these, and 0 are already reserved."),
        ([2], 2, "The event asks for 3 of these, and 2 are already reserved."),
    ],
    ids=["one-more-at-once", "one-more-in-two"],
)
def test_one_unit_more_than_the_line_asks_for_is_refused_on_quantity(
    line_of_three: EventEquipmentLine,
    equipment_type: EquipmentType,
    db_session: Session,
    held: list[int],
    asked: int,
    message: str,
) -> None:
    for quantity in held:
        _reserve(equipment_type, quantity)

    with pytest.raises(ValidationError) as exc_info:
        _reserve(equipment_type, asked)

    assert exc_info.value.message == message
    assert exc_info.value.details == {"quantity": [message]}
    assert _reserved(db_session) == held


def test_nothing_more_can_be_added_to_a_reservation_above_a_lowered_line(
    line_of_three: EventEquipmentLine,
    equipment_type: EquipmentType,
    db_session: Session,
) -> None:
    _reserve(equipment_type, 3)
    update_equipment_line(COORDINATOR_ID, REFERENCE, line_of_three.id, {"quantity": 2})

    with pytest.raises(ValidationError) as exc_info:
        _reserve(equipment_type, 1)

    assert exc_info.value.message == "The event asks for 2 of these, and 3 are already reserved."
    assert _reserved(db_session) == [3]


def test_a_type_the_event_has_no_line_for_is_reserved_up_to_what_is_free(
    saved_event_request: EventRequest, equipment_type: EquipmentType, db_session: Session
) -> None:
    _reserve(equipment_type, 10)

    assert _reserved(db_session) == [10]
