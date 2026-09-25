"""Fixtures shared by the equipment tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentType


@pytest.fixture()
def reload_equipment_type(db_session: Session) -> Callable[[int], EquipmentType]:
    """Read an equipment type back from the database rather than the session's cache."""

    def _reload(equipment_type_id: int) -> EquipmentType:
        db_session.expire_all()
        equipment_type = db_session.get(EquipmentType, equipment_type_id)
        assert equipment_type is not None
        return equipment_type

    return _reload
