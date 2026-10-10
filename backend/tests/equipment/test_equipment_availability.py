"""Unit tests for the overlap rule behind SCRUM-45 (is enough equipment free?).

Equipment is only held for an event's own period, so two reservations conflict when
their periods overlap. They run against ``db_session`` so the rule is checked through a
real query, not by reading the SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.equipment import services
from app.modules.equipment.models import EquipmentReservation, EquipmentType

pytestmark = pytest.mark.scrum_45

MakeEquipmentType = Callable[..., EquipmentType]
Save = Callable[..., None]


def _at(hour: int, day: int = 3) -> datetime:
    return datetime(2026, 11, day, hour, 0, tzinfo=timezone.utc)


def _overlapping_event_ids(
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save, *, other: tuple
) -> list[int]:
    """Reserve 10:00-12:00 for event 1, then list the events overlapping ``other``."""
    equipment_type = make_equipment_type()
    save(equipment_type)
    save(
        EquipmentReservation(
            event_id=1,
            equipment_type_id=equipment_type.id,
            quantity=1,
            starts_at=_at(10),
            ends_at=_at(12),
            reserved_by=3,
        )
    )
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
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save, other, description
) -> None:
    assert _overlapping_event_ids(db_session, make_equipment_type, save, other=other) == [1], (
        description
    )


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
    db_session: Session, make_equipment_type: MakeEquipmentType, save: Save, other, description
) -> None:
    # No setup or turnaround buffer for equipment, so abutting periods are free (AC5).
    assert _overlapping_event_ids(db_session, make_equipment_type, save, other=other) == [], (
        description
    )
