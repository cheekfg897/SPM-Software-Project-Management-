"""Fixtures shared by the equipment tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentType


@pytest.fixture()
def make_equipment_type() -> Callable[..., EquipmentType]:
    """Factory for ``EquipmentType`` objects; add one to ``db_session`` to persist it.

    By default the equipment is kept in a store, not at a venue.
    """

    def _make(
        *,
        name: str = "Projector",
        description: str | None = None,
        total_quantity: int = 10,
        venue_id: int | None = None,
        store_name: str | None = "Central AV store",
    ) -> EquipmentType:
        return EquipmentType(
            name=name,
            description=description,
            total_quantity=total_quantity,
            venue_id=venue_id,
            store_name=store_name,
        )

    return _make


@pytest.fixture()
def equipment_type(
    make_equipment_type: Callable[..., EquipmentType], save: Callable[..., None]
) -> EquipmentType:
    """One saved equipment type with default details, kept in a store."""
    saved = make_equipment_type()
    save(saved)
    return saved


@pytest.fixture()
def reload_equipment_type(db_session: Session) -> Callable[[int], EquipmentType]:
    """Read an equipment type back from the database rather than the session's cache."""

    def _reload(equipment_type_id: int) -> EquipmentType:
        db_session.expire_all()
        equipment_type = db_session.get(EquipmentType, equipment_type_id)
        assert equipment_type is not None
        return equipment_type

    return _reload
