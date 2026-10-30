"""Unit tests for SCRUM-49 AC10 — returning a rejected event's equipment.

When the assigned coordinator rejects an event during planning, its reserved equipment
returns to the available quantity, as a cancelled event's does (SCRUM-61 AC3, ADR-0093).
``release_event_reservations`` does the equipment module's part without committing.
Runs against ``db_session``, so availability is really counted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.equipment import services
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from tests.equipment.conftest import MakeReservation

pytestmark = pytest.mark.scrum_49

STARTS_AT = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc)
#: ``make_reservation`` reserves for event 1.
REJECTED_EVENT_ID = 1
OTHER_EVENT_ID = 2


def _available(equipment_type: EquipmentType, session: Session) -> int:
    return services.available_quantity(equipment_type.id, STARTS_AT, ENDS_AT, session=session)


def _reserved_event_ids(session: Session) -> list[int]:
    session.expire_all()
    reservations = session.scalars(select(EquipmentReservation).order_by(EquipmentReservation.id))
    return [reservation.event_id for reservation in reservations]


@pytest.fixture()
def reserve(
    equipment_type: EquipmentType, make_reservation: MakeReservation, save: Callable[..., None]
) -> Callable[[int, int], None]:
    """Reserve ``quantity`` units of ``equipment_type`` for an event's period."""

    def _reserve(event_id: int, quantity: int) -> None:
        reservation = make_reservation(equipment_type, quantity, STARTS_AT, ENDS_AT)
        reservation.event_id = event_id
        save(reservation)

    return _reserve


def test_the_reserved_units_return_to_the_available_quantity(
    db_session: Session, equipment_type: EquipmentType, reserve: Callable[[int, int], None]
) -> None:
    reserve(REJECTED_EVENT_ID, 3)
    reserve(REJECTED_EVENT_ID, 2)
    assert _available(equipment_type, db_session) == equipment_type.total_quantity - 5

    services.release_event_reservations(REJECTED_EVENT_ID, session=db_session)
    db_session.commit()

    assert _available(equipment_type, db_session) == equipment_type.total_quantity
    assert _reserved_event_ids(db_session) == []


def test_another_events_reservations_stay(
    db_session: Session, equipment_type: EquipmentType, reserve: Callable[[int, int], None]
) -> None:
    reserve(REJECTED_EVENT_ID, 3)
    reserve(OTHER_EVENT_ID, 4)

    services.release_event_reservations(REJECTED_EVENT_ID, session=db_session)
    db_session.commit()

    assert _reserved_event_ids(db_session) == [OTHER_EVENT_ID]
    assert _available(equipment_type, db_session) == equipment_type.total_quantity - 4


def test_nothing_is_saved_until_the_caller_commits(
    db_session: Session, reserve: Callable[[int, int], None]
) -> None:
    """The rejection commits the release with its own status change (ADR-0093)."""
    reserve(REJECTED_EVENT_ID, 3)

    services.release_event_reservations(REJECTED_EVENT_ID, session=db_session)
    db_session.rollback()

    assert _reserved_event_ids(db_session) == [REJECTED_EVENT_ID]
