"""Unit tests for SCRUM-45 (is enough equipment free?).

Equipment is only held for an event's own period, so two reservations conflict when
their periods overlap. Availability is the units held, less the overlapping
reservations and the units out of service. They run against ``db_session`` so the rules
are checked through real queries, not by reading the SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.equipment import services
from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
)

pytestmark = pytest.mark.scrum_45

Save = Callable[..., None]


def _at(hour: int, day: int = 3) -> datetime:
    return datetime(2026, 11, day, hour, 0, tzinfo=timezone.utc)


def _reservation(
    equipment_type: EquipmentType, quantity: int, starts_at: datetime, ends_at: datetime
) -> EquipmentReservation:
    return EquipmentReservation(
        event_id=1,
        equipment_type_id=equipment_type.id,
        quantity=quantity,
        starts_at=starts_at,
        ends_at=ends_at,
        reserved_by=3,
    )


def _out_of_service(
    equipment_type: EquipmentType, quantity: int, *, resolved_at: datetime | None = None
) -> EquipmentOutOfService:
    return EquipmentOutOfService(
        equipment_type_id=equipment_type.id,
        quantity=quantity,
        reason=OutOfServiceReason.DAMAGED,
        recorded_by=3,
        recorded_at=_at(8, day=1),
        resolved_at=resolved_at,
    )


def _overlapping_event_ids(
    db_session: Session, equipment_type: EquipmentType, save: Save, *, other: tuple
) -> list[int]:
    """Reserve 10:00-12:00 for event 1, then list the events overlapping ``other``."""
    save(_reservation(equipment_type, 1, _at(10), _at(12)))
    starts_at, ends_at = other
    statement = select(EquipmentReservation.event_id).where(
        services._overlapping(starts_at, ends_at)
    )
    return list(db_session.scalars(statement))


@pytest.mark.parametrize(
    ("other", "description"),
    [
        ((_at(11), _at(13)), "starts inside"),
        ((_at(9), _at(11)), "ends inside"),
        ((_at(10), _at(12)), "same period"),
        ((_at(10), _at(11)), "contained"),
        ((_at(9), _at(13)), "containing"),
    ],
)
def test_overlapping_periods_conflict(
    db_session: Session, equipment_type: EquipmentType, save: Save, other, description
) -> None:
    assert _overlapping_event_ids(db_session, equipment_type, save, other=other) == [1], description


@pytest.mark.parametrize(
    ("other", "description"),
    [
        ((_at(12), _at(14)), "starts exactly when the reservation ends"),
        ((_at(8), _at(10)), "ends exactly when the reservation starts"),
        ((_at(13), _at(15)), "later the same day"),
        ((_at(10, 4), _at(12, 4)), "same hours on another day"),
    ],
)
def test_periods_that_do_not_overlap_do_not_conflict(
    db_session: Session, equipment_type: EquipmentType, save: Save, other, description
) -> None:
    # No setup or turnaround buffer for equipment, so abutting periods are free (AC5).
    assert _overlapping_event_ids(db_session, equipment_type, save, other=other) == [], description


def test_available_quantity_subtracts_reservations_for_an_overlapping_event(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # AC1: ten projectors held, four reserved for an overlapping event -> six available.
    save(_reservation(equipment_type, 4, _at(10), _at(12)))

    assert services.available_quantity(equipment_type.id, _at(11), _at(13)) == 6


def test_available_quantity_adds_up_several_overlapping_reservations(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    save(
        _reservation(equipment_type, 4, _at(10), _at(12)),
        _reservation(equipment_type, 3, _at(9), _at(11)),
    )

    assert services.available_quantity(equipment_type.id, _at(10), _at(11)) == 3


def test_available_quantity_ignores_reservations_that_do_not_overlap(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # AC5: an event that starts as the other ends sees all ten.
    save(_reservation(equipment_type, 4, _at(10), _at(12)))

    assert services.available_quantity(equipment_type.id, _at(12), _at(14)) == 10


def test_available_quantity_ignores_reservations_of_other_equipment_types(
    db_session: Session,
    equipment_type: EquipmentType,
    make_equipment_type: Callable[..., EquipmentType],
    save: Save,
) -> None:
    other_type = make_equipment_type(name="Microphone")
    save(other_type)
    save(_reservation(other_type, 4, _at(10), _at(12)))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 10


def test_available_quantity_subtracts_unresolved_out_of_service_units(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # AC2: two damaged units are two fewer, whatever the period asked about.
    save(_out_of_service(equipment_type, 2))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 8


def test_available_quantity_ignores_resolved_out_of_service_units(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    save(_out_of_service(equipment_type, 2, resolved_at=_at(9, day=2)))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 10


def test_available_quantity_combines_reservations_and_out_of_service_units(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    save(_reservation(equipment_type, 4, _at(10), _at(12)), _out_of_service(equipment_type, 2))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 4


def test_available_quantity_never_goes_below_zero(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # Units can break after they were reserved, leaving more committed than held.
    save(_reservation(equipment_type, 8, _at(10), _at(12)), _out_of_service(equipment_type, 5))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 0


def test_available_quantity_of_an_unknown_equipment_type_is_not_found(
    db_session: Session,
) -> None:
    with pytest.raises(NotFoundError):
        services.available_quantity(999, _at(10), _at(12))
