"""Unit tests for an event's equipment reservations as its read-only record shows them.

SCRUM-85 AC2: equipment preparation details are visible to other internal users, not
only to the assigned coordinator. SCRUM-24 AC9: Venue Staff, Technical Support, the
Safety Officer and the Event Coordinator Lead open any submitted event's record, which
holds its equipment (ADR-0095). The events module reads the reservations by the event's
id through ``list_reservations_of_event``, never the equipment models.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.equipment import services
from app.modules.equipment.models import EquipmentType, PreparationStatus
from tests.equipment.conftest import MakeReservation

pytestmark = pytest.mark.scrum_85

STARTS_AT = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc)


def test_each_reservation_shows_its_equipment_units_and_preparation(
    db_session: Session,
    saved_users: list[User],
    equipment_type: EquipmentType,
    make_reservation: MakeReservation,
    save: Callable[..., None],
) -> None:
    reservation = make_reservation(equipment_type, 4, STARTS_AT, ENDS_AT)
    reservation.preparation_status = PreparationStatus.READY
    reservation.preparation_notes = "Tested and packed."
    save(reservation)

    [shown] = services.list_reservations_of_event(1, session=db_session)

    assert (
        shown.equipment_type_name,
        shown.quantity,
        shown.starts_at,
        shown.ends_at,
        shown.reserved_by,
        shown.preparation_status,
        shown.preparation_notes,
    ) == (
        "Projector",
        4,
        STARTS_AT,
        ENDS_AT,
        "Coordinator Three",
        PreparationStatus.READY,
        "Tested and packed.",
    )


def test_reservations_are_listed_oldest_first_and_another_events_are_left_out(
    db_session: Session,
    equipment_type: EquipmentType,
    make_reservation: MakeReservation,
    save: Callable[..., None],
) -> None:
    first = make_reservation(equipment_type, 1, STARTS_AT, ENDS_AT)
    second = make_reservation(equipment_type, 2, STARTS_AT, ENDS_AT)
    other_events = make_reservation(equipment_type, 3, STARTS_AT, ENDS_AT)
    other_events.event_id = 2
    save(first, second, other_events)

    shown = services.list_reservations_of_event(1, session=db_session)

    assert [reservation.quantity for reservation in shown] == [1, 2]
