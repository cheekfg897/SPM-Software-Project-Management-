"""Unit tests for the tables behind SCRUM-46 "Reserve equipment" (ADR-0037).

``equipment_reservations`` holds the units reserved for one event's period (AC1, AC4);
``equipment_out_of_service`` holds units recorded as damaged or under maintenance, which
SCRUM-45 AC2 excludes from availability. They run against ``db_session``, an in-memory
SQLite database, so the check constraints really run.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
)

pytestmark = pytest.mark.scrum_46

MakeEquipmentType = Callable[..., EquipmentType]
Save = Callable[..., None]

STARTS_AT = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc)
RECORDED_AT = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
#: Plain foreign keys: SQLite doesn't enforce them, and the tables they point at belong
#: to other modules.
EVENT_ID = 7
USER_ID = 3


def _saved_equipment_type(make_equipment_type: MakeEquipmentType, save: Save) -> EquipmentType:
    equipment_type = make_equipment_type()
    save(equipment_type)
    return equipment_type


def _reservation(equipment_type: EquipmentType, quantity: int) -> EquipmentReservation:
    return EquipmentReservation(
        event_id=EVENT_ID,
        equipment_type_id=equipment_type.id,
        quantity=quantity,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        reserved_by=USER_ID,
    )


def _out_of_service(equipment_type: EquipmentType, quantity: int) -> EquipmentOutOfService:
    return EquipmentOutOfService(
        equipment_type_id=equipment_type.id,
        quantity=quantity,
        reason=OutOfServiceReason.DAMAGED,
        recorded_by=USER_ID,
        recorded_at=RECORDED_AT,
    )


def test_a_reservation_keeps_its_quantity_and_exact_period(
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save
) -> None:
    equipment_type = _saved_equipment_type(make_equipment_type, save)

    save(_reservation(equipment_type, quantity=4))

    db_session.expire_all()
    stored = db_session.scalars(select(EquipmentReservation)).one()
    assert stored.event_id == EVENT_ID
    assert stored.equipment_type_id == equipment_type.id
    assert stored.quantity == 4
    assert stored.starts_at == STARTS_AT
    assert stored.ends_at == ENDS_AT
    assert stored.reserved_by == USER_ID
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_a_reservation_of_no_units_is_refused(
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save
) -> None:
    equipment_type = _saved_equipment_type(make_equipment_type, save)

    with pytest.raises(IntegrityError):
        save(_reservation(equipment_type, quantity=0))

    db_session.rollback()
    assert db_session.scalars(select(EquipmentReservation)).all() == []


def test_an_out_of_service_row_is_unresolved_until_someone_resolves_it(
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save
) -> None:
    equipment_type = _saved_equipment_type(make_equipment_type, save)

    save(_out_of_service(equipment_type, quantity=2))

    db_session.expire_all()
    stored = db_session.scalars(select(EquipmentOutOfService)).one()
    assert stored.quantity == 2
    assert stored.reason is OutOfServiceReason.DAMAGED
    assert stored.recorded_by == USER_ID
    assert stored.recorded_at == RECORDED_AT
    assert stored.resolved_at is None


def test_an_out_of_service_row_of_no_units_is_refused(
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save
) -> None:
    equipment_type = _saved_equipment_type(make_equipment_type, save)

    with pytest.raises(IntegrityError):
        save(_out_of_service(equipment_type, quantity=0))

    db_session.rollback()
    assert db_session.scalars(select(EquipmentOutOfService)).all() == []


def test_the_out_of_service_reasons_are_stored_by_value() -> None:
    assert {reason.value for reason in OutOfServiceReason} == {"damaged", "under_maintenance"}
