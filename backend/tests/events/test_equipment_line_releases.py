"""Unit tests for SCRUM-37 "Record what equipment an event needs": releasing equipment.

AC4: a removed line releases its reservation and its request is closed. The event's
reservations of the line's equipment type are released, so those units are free again
for the period; other types' and other events' reservations stay. A line moved to
another equipment type releases the old type's reservations the same way, since the
event no longer asks for it; a new quantity keeps them for Technical Support to
review (ADR-0092). The release is saved with the line change, so a refused change
releases nothing.

The services run against ``db_session``, so the reservations are real rows.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.equipment.services import available_quantity
from app.modules.events import services
from app.modules.events.models import EventEquipmentLine, EventRequest
from app.modules.events.services import remove_equipment_line, update_equipment_line

#: Each test starts on an approved event, the first status its equipment lines change
#: in (SCRUM-110); a test that needs another status sets it.
pytestmark = [pytest.mark.scrum_37, pytest.mark.usefixtures("approved_event_request")]

Save = Callable[..., None]
#: A reservation as ``(event id, equipment type id, quantity)``.
HeldUnits = tuple[int, int, int]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
#: ``saved_event_request``'s period, 9:00 to 17:00 on 15 Oct 2026 in Singapore.
STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def _reservation(
    event_id: int, equipment_type: EquipmentType, quantity: int
) -> EquipmentReservation:
    """Units of ``equipment_type`` held for the event's period, reserved by user 5."""
    return EquipmentReservation(
        event_id=event_id,
        equipment_type_id=equipment_type.id,
        quantity=quantity,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        reserved_by=5,
    )


def _notice_fails(*_: object, **__: object) -> None:
    """Stands in for the notice when the notification service is down."""
    raise RuntimeError("notification service down")


def _held(session: Session) -> list[HeldUnits]:
    """Every saved reservation, read back from the database, oldest first."""
    session.expire_all()
    stmt = select(EquipmentReservation).order_by(EquipmentReservation.id)
    held = []
    for reservation in session.scalars(stmt):
        held.append((reservation.event_id, reservation.equipment_type_id, reservation.quantity))
    return held


@pytest.fixture()
def projector_line(
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Save,
) -> EventEquipmentLine:
    """Three projectors on REFERENCE."""
    line = make_equipment_line(saved_event_request, equipment_type, quantity=3)
    save(line)
    return line


@pytest.fixture()
def reservations(
    saved_event_request: EventRequest,
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    save: Save,
) -> list[HeldUnits]:
    """Saved reservations, returned as ``_held`` reads them back.

    Two projectors then one more, and a microphone, for REFERENCE; four projectors for
    event 99.
    """
    event_id = saved_event_request.id
    save(
        _reservation(event_id, equipment_type, 2),
        _reservation(event_id, equipment_type, 1),
        _reservation(event_id, microphone, 1),
        _reservation(99, equipment_type, 4),
    )
    return [
        (event_id, equipment_type.id, 2),
        (event_id, equipment_type.id, 1),
        (event_id, microphone.id, 1),
        (99, equipment_type.id, 4),
    ]


def test_removing_a_line_releases_the_events_reservations_of_its_type(
    db_session: Session,
    saved_event_request: EventRequest,
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    reservations: list[HeldUnits],
) -> None:
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    assert _held(db_session) == [
        (saved_event_request.id, microphone.id, 1),
        (99, equipment_type.id, 4),
    ]


def test_a_removed_lines_units_are_free_again_for_the_period(
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    reservations: list[HeldUnits],
) -> None:
    """Ten projectors: four stay with event 99."""
    remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    assert available_quantity(equipment_type.id, STARTS_AT, ENDS_AT) == 6


def test_moving_a_line_to_another_type_releases_the_old_types_reservations(
    db_session: Session,
    saved_event_request: EventRequest,
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    make_equipment_type: Callable[..., EquipmentType],
    reservations: list[HeldUnits],
    save: Save,
) -> None:
    lectern = make_equipment_type(name="Lectern")
    save(lectern)

    update_equipment_line(
        COORDINATOR_ID, REFERENCE, projector_line.id, {"equipment_type_id": lectern.id}
    )

    assert _held(db_session) == [
        (saved_event_request.id, microphone.id, 1),
        (99, equipment_type.id, 4),
    ]


@pytest.mark.parametrize("payload", [{"quantity": 1}, {"notes": "Bring a spare bulb"}])
def test_a_line_that_keeps_its_type_keeps_its_reservations(
    db_session: Session,
    projector_line: EventEquipmentLine,
    reservations: list[HeldUnits],
    payload: dict[str, object],
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, payload)

    assert _held(db_session) == reservations


def test_a_line_sent_its_own_type_with_a_new_quantity_keeps_its_reservations(
    db_session: Session,
    projector_line: EventEquipmentLine,
    equipment_type: EquipmentType,
    reservations: list[HeldUnits],
) -> None:
    """An edit may send the type the line already has: that is no move."""
    payload = {"equipment_type_id": equipment_type.id, "quantity": 1}

    update_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id, payload)

    assert _held(db_session) == reservations


@pytest.fixture()
def held_once_released(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    reservations: list[HeldUnits],
) -> list[HeldUnits]:
    """What ``reservations`` leaves once REFERENCE's projectors are released."""
    return [(saved_event_request.id, microphone.id, 1), (99, equipment_type.id, 4)]


def test_a_removed_lines_release_is_saved_with_the_removal_even_if_the_notice_fails(
    db_session: Session,
    projector_line: EventEquipmentLine,
    held_once_released: list[HeldUnits],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The release rides in the removal's own commit; the notice comes after it."""
    monkeypatch.setattr(services, "_notify_technical_support", _notice_fails)

    with pytest.raises(RuntimeError):
        remove_equipment_line(COORDINATOR_ID, REFERENCE, projector_line.id)

    db_session.rollback()
    assert db_session.get(EventEquipmentLine, projector_line.id) is None
    assert _held(db_session) == held_once_released


def test_a_moved_lines_release_is_saved_with_the_move_even_if_the_notice_fails(
    db_session: Session,
    projector_line: EventEquipmentLine,
    make_equipment_type: Callable[..., EquipmentType],
    held_once_released: list[HeldUnits],
    save: Save,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The release rides in the type change's own commit; the notice comes after it."""
    lectern = make_equipment_type(name="Lectern")
    save(lectern)
    monkeypatch.setattr(services, "_notify_technical_support", _notice_fails)

    with pytest.raises(RuntimeError):
        update_equipment_line(
            COORDINATOR_ID, REFERENCE, projector_line.id, {"equipment_type_id": lectern.id}
        )

    db_session.rollback()
    assert db_session.get(EventEquipmentLine, projector_line.id).equipment_type_id == lectern.id
    assert _held(db_session) == held_once_released


def test_a_refused_type_change_releases_nothing(
    db_session: Session,
    saved_event_request: EventRequest,
    projector_line: EventEquipmentLine,
    microphone: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    reservations: list[HeldUnits],
    save: Save,
) -> None:
    """The event already has a microphone line, so the change is a 409."""
    save(make_equipment_line(saved_event_request, microphone))

    with pytest.raises(ConflictError):
        update_equipment_line(
            COORDINATOR_ID, REFERENCE, projector_line.id, {"equipment_type_id": microphone.id}
        )

    assert _held(db_session) == reservations
