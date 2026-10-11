"""Fixtures shared by the equipment tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
)

MakeReservation = Callable[[EquipmentType, int, datetime, datetime], EquipmentReservation]
MakeOutOfService = Callable[..., EquipmentOutOfService]


@pytest.fixture()
def reload_equipment_type(db_session: Session) -> Callable[[int], EquipmentType]:
    """Read an equipment type back from the database rather than the session's cache."""

    def _reload(equipment_type_id: int) -> EquipmentType:
        db_session.expire_all()
        equipment_type = db_session.get(EquipmentType, equipment_type_id)
        assert equipment_type is not None
        return equipment_type

    return _reload


@pytest.fixture()
def make_reservation() -> MakeReservation:
    """Factory for unsaved reservations of a type for a period, by event 1 and user 3.

    Plain foreign keys: SQLite doesn't enforce them, and the tables they point at
    belong to other modules.
    """

    def _make(
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

    return _make


@pytest.fixture()
def make_out_of_service() -> MakeOutOfService:
    """Factory for unsaved damaged units of a type, recorded by user 3 on 1 Oct 2026.

    Nothing in SCRUM-45/46 writes these rows (SCRUM-47 will), so tests build them here.
    """

    def _make(
        equipment_type: EquipmentType, quantity: int, *, resolved_at: datetime | None = None
    ) -> EquipmentOutOfService:
        return EquipmentOutOfService(
            equipment_type_id=equipment_type.id,
            quantity=quantity,
            reason=OutOfServiceReason.DAMAGED,
            recorded_by=3,
            recorded_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
            resolved_at=resolved_at,
        )

    return _make
