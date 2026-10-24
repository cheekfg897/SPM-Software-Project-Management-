"""Unit tests for SCRUM-46 AC5: reserving equipment notifies nobody by itself.

The coordinator is told once, when Technical Support records the outcome of the
equipment request (SCRUM-48), so a fulfilled request doesn't bring two notices
(ADR-0102). A reservation still saves and records its history entry (AC4). Runs
against ``db_session``, an in-memory SQLite database.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.equipment import services
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.events.models import EventHistoryEntry, EventHistoryKind, EventRequest
from app.modules.notifications.models import Notification

pytestmark = pytest.mark.scrum_46

Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
TECHNICAL_SUPPORT_ID = 5


def _reserve(equipment_type: EquipmentType, quantity: int) -> services.ReservationAsShown:
    payload = {"equipment_type_id": equipment_type.id, "quantity": quantity}
    return services.reserve_equipment(REFERENCE, payload, reserved_by=TECHNICAL_SUPPORT_ID)


def test_reserving_notifies_nobody_and_keeps_each_reservation_and_its_history(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
) -> None:
    """The event's coordinator (user 3) included: they hear of the outcome instead."""
    _reserve(equipment_type, 4)
    _reserve(equipment_type, 2)

    assert db_session.scalars(select(Notification)).all() == []
    assert db_session.scalars(select(EquipmentReservation.quantity)).all() == [4, 2]
    kinds = db_session.scalars(select(EventHistoryEntry.kind)).all()
    assert kinds == [EventHistoryKind.EQUIPMENT_RESERVED, EventHistoryKind.EQUIPMENT_RESERVED]


def test_reserving_for_an_event_with_no_coordinator_warns_of_nothing(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    save: Save,
    equipment_type: EquipmentType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With no notice to send, there is nobody missing to warn about (ADR-0102)."""
    save(make_event_request(coordinator_id=None))

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _reserve(equipment_type, 4)

    assert db_session.scalars(select(EquipmentReservation.quantity)).all() == [4]
    assert caplog.records == []
