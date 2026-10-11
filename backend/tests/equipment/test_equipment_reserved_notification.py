"""Unit tests for SCRUM-46 AC5: the event's coordinator is told equipment was reserved.

Only the Event Coordinator assigned to the event is notified, once for every
reservation; an event with nobody assigned notifies nobody (ADR-0018). The notice is its
own commit after the reservation's, so losing it never loses the reservation (ADR-0015).
Runs against ``db_session``, an in-memory SQLite database.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.equipment import services
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.events import services as events_services
from app.modules.events.models import EventRequest
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)

pytestmark = pytest.mark.scrum_46

NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5


def _reserve(equipment_type: EquipmentType, quantity: int) -> services.ReservationAsShown:
    payload = {"equipment_type_id": equipment_type.id, "quantity": quantity}
    return services.reserve_equipment(REFERENCE, payload, reserved_by=TECHNICAL_SUPPORT_ID)


@pytest.fixture()
def reserved_notification(saved_event_request: EventRequest) -> tuple[Any, ...]:
    """What a notification about equipment reserved for REFERENCE records.

    In the order ``notifications_of`` lists it: event request id, reference, name,
    kind, read at.
    """
    return (
        saved_event_request.id,
        REFERENCE,
        "Partner Summit",
        NotificationKind.EQUIPMENT_RESERVED,
        None,
    )


def test_reserving_notifies_the_assigned_coordinator_once(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    notifications_of: NotificationsOf,
    reserved_notification: tuple[Any, ...],
) -> None:
    _reserve(equipment_type, 4)

    assert notifications_of(COORDINATOR_ID) == [reserved_notification]


@pytest.mark.parametrize("user_id", [2, 4, 5, 7], ids=["admin", "venue", "tech", "organiser"])
def test_nobody_but_the_assigned_coordinator_is_notified(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    notifications_of: NotificationsOf,
    user_id: int,
) -> None:
    _reserve(equipment_type, 4)

    assert notifications_of(user_id) == []


def test_each_reservation_raises_its_own_notification(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    notifications_of: NotificationsOf,
) -> None:
    _reserve(equipment_type, 4)
    _reserve(equipment_type, 2)

    kinds = [notification[3] for notification in notifications_of(COORDINATOR_ID)]
    assert kinds == [NotificationKind.EQUIPMENT_RESERVED, NotificationKind.EQUIPMENT_RESERVED]


def test_a_refused_reservation_notifies_nobody(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
) -> None:
    with pytest.raises(ValidationError):
        _reserve(equipment_type, equipment_type.total_quantity + 1)

    assert db_session.scalars(select(Notification)).all() == []


def test_an_event_with_no_coordinator_notifies_nobody_and_keeps_the_reservation(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    save: Save,
    equipment_type: EquipmentType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    save(make_event_request(coordinator_id=None))

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _reserve(equipment_type, 4)

    assert db_session.scalars(select(Notification)).all() == []
    assert db_session.scalars(select(EquipmentReservation.quantity)).all() == [4]
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_unassigned reference={REFERENCE}"
    ]


def test_a_lost_notification_does_not_lose_the_committed_reservation(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0015: failing the reply would invite the caller to reserve again."""
    lost_connection = OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))

    def _fail(*_: Any, **__: Any) -> None:
        raise lost_connection

    monkeypatch.setattr(events_services, "notify_users", _fail)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        shown = _reserve(equipment_type, 4)

    db_session.expire_all()
    stored = db_session.scalars(select(EquipmentReservation)).one()
    assert (shown.id, shown.quantity) == (stored.id, 4)
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference={REFERENCE} kind=equipment_reserved"
    ]


def test_the_notification_says_equipment_was_reserved_and_links_to_the_event(
    saved_event_request: EventRequest, equipment_type: EquipmentType
) -> None:
    _reserve(equipment_type, 4)

    shown = NotificationSchema().dump(list_notifications_for_recipient(COORDINATOR_ID)[0])

    assert shown["kind"] == "equipment_reserved"
    assert shown["message"] == "Equipment was reserved for an event."
    assert shown["link"] == "/events/EVR-AAAAAAAA"
    assert shown["event_name"] == "Partner Summit"
