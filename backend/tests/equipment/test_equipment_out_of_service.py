"""Unit tests for SCRUM-47 (take damaged equipment out of circulation).

Technical Support take units of an equipment type out of service as damaged or under
maintenance, and put them back (AC1). Units out of service no longer count as free
(AC2). Reservations the change leaves short are flagged and their coordinator is told
(AC3). Who changed the status, and when, is recorded (AC4). AC5 (a new safety check)
waits for the Operational Safety Check itself (ADR-0046). They run against
``db_session``, an in-memory SQLite database.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import event, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import ORMExecuteState, Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment import services
from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
)
from app.modules.events.models import EventRequest
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import list_notifications_for_recipient

pytestmark = pytest.mark.scrum_47

Save = Callable[..., None]
MakeReservation = Callable[[EquipmentType, int, datetime, datetime], EquipmentReservation]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

NOW = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)
#: ``saved_event_request`` runs 09:00-17:00 in Singapore (UTC+8).
EVENT_STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
EVENT_ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
OTHER_DAY_STARTS_AT = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)
OTHER_DAY_ENDS_AT = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
ALREADY_OVER_STARTS_AT = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
ALREADY_OVER_ENDS_AT = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
#: Technical Support Staff 5 and 2 in ``saved_users``, with the factory's default name.
TECHNICAL_SUPPORT_ID = 5
OTHER_TECHNICAL_SUPPORT_ID = 2
TECHNICIAN_NAME = "Alice Example"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
#: ``equipment_type`` holds ten projectors.
HELD = 10


def _mark(
    equipment_type: EquipmentType, quantity: int, reason: str = "damaged"
) -> services.OutOfServiceAsShown:
    payload = {"quantity": quantity, "reason": reason}
    return services.mark_out_of_service(
        equipment_type.id, payload, recorded_by=TECHNICAL_SUPPORT_ID, now=NOW
    )


def _free(equipment_type: EquipmentType) -> int:
    return services.available_quantity(equipment_type.id, EVENT_STARTS_AT, EVENT_ENDS_AT)


def _flagged_quantities(db_session: Session) -> list[int]:
    statement = (
        select(EquipmentReservation.quantity)
        .where(EquipmentReservation.needs_attention.is_(True))
        .order_by(EquipmentReservation.quantity)
    )
    return list(db_session.scalars(statement))


@pytest.fixture()
def eight_reserved(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    save: Save,
    make_reservation: MakeReservation,
) -> EquipmentReservation:
    """Eight of ten projectors reserved; taking out three leaves the event short."""
    reservation = make_reservation(equipment_type, 8, EVENT_STARTS_AT, EVENT_ENDS_AT)
    save(reservation)
    return reservation


# --- AC1: set the status ------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("damaged", OutOfServiceReason.DAMAGED),
        ("under_maintenance", OutOfServiceReason.UNDER_MAINTENANCE),
    ],
)
def test_units_can_be_marked_damaged_or_under_maintenance(
    db_session: Session, equipment_type: EquipmentType, reason: str, expected: OutOfServiceReason
) -> None:
    shown = _mark(equipment_type, 3, reason)

    stored = db_session.scalars(select(EquipmentOutOfService)).one()
    assert (stored.id, stored.quantity, stored.reason, stored.resolved_at) == (
        shown.id,
        3,
        expected,
        None,
    )
    assert (shown.equipment_type_id, shown.quantity, shown.reason) == (
        equipment_type.id,
        3,
        expected,
    )


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"quantity": 0, "reason": "damaged"}, "quantity"),
        ({"reason": "damaged"}, "quantity"),
        ({"quantity": 2, "reason": "lost"}, "reason"),
        ({"quantity": 2}, "reason"),
    ],
    ids=["zero-units", "no-quantity", "unknown-reason", "no-reason"],
)
def test_an_invalid_body_is_a_400_on_its_field(
    db_session: Session, equipment_type: EquipmentType, payload: dict[str, Any], field: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        services.mark_out_of_service(
            equipment_type.id, payload, recorded_by=TECHNICAL_SUPPORT_ID, now=NOW
        )

    assert field in caught.value.details
    assert db_session.scalars(select(EquipmentOutOfService)).all() == []


def test_all_the_units_in_service_can_be_taken_out(equipment_type: EquipmentType) -> None:
    _mark(equipment_type, 4)

    _mark(equipment_type, 6)

    assert _free(equipment_type) == 0


def test_more_units_than_are_in_service_are_refused(
    db_session: Session, equipment_type: EquipmentType
) -> None:
    _mark(equipment_type, 4)

    with pytest.raises(ValidationError) as caught:
        _mark(equipment_type, 7)

    assert caught.value.message == "Only 6 units are in service."
    assert caught.value.details == {"quantity": ["Only 6 units are in service."]}
    assert len(db_session.scalars(select(EquipmentOutOfService)).all()) == 1


@pytest.mark.usefixtures("db_session")
def test_an_unknown_equipment_type_is_a_404() -> None:
    with pytest.raises(NotFoundError):
        services.mark_out_of_service(
            999, {"quantity": 1, "reason": "damaged"}, recorded_by=TECHNICAL_SUPPORT_ID
        )


def test_units_can_be_returned_to_service(
    db_session: Session, equipment_type: EquipmentType
) -> None:
    entry = _mark(equipment_type, 3)

    shown = services.return_to_service(entry.id, resolved_by=OTHER_TECHNICAL_SUPPORT_ID, now=LATER)

    stored = db_session.scalars(select(EquipmentOutOfService)).one()
    assert stored.resolved_at == LATER
    assert shown.resolved_at == LATER


def test_units_already_back_in_service_cannot_be_returned_again(
    equipment_type: EquipmentType,
) -> None:
    entry = _mark(equipment_type, 3)
    services.return_to_service(entry.id, resolved_by=TECHNICAL_SUPPORT_ID, now=LATER)

    with pytest.raises(ConflictError):
        services.return_to_service(entry.id, resolved_by=TECHNICAL_SUPPORT_ID, now=LATER)


@pytest.mark.usefixtures("db_session")
def test_returning_an_unknown_entry_is_a_404() -> None:
    with pytest.raises(NotFoundError):
        services.return_to_service(999, resolved_by=TECHNICAL_SUPPORT_ID)


def test_the_list_shows_only_this_types_units_still_out_of_service_oldest_first(
    equipment_type: EquipmentType, microphone: EquipmentType
) -> None:
    first = _mark(equipment_type, 1)
    back = _mark(equipment_type, 2)
    services.return_to_service(back.id, resolved_by=TECHNICAL_SUPPORT_ID, now=LATER)
    second = _mark(equipment_type, 3, "under_maintenance")
    _mark(microphone, 4)

    listed = services.list_out_of_service(equipment_type.id)

    assert [entry.id for entry in listed] == [first.id, second.id]


# --- AC2: out-of-service units are not available ------------------------------------


def test_availability_drops_by_exactly_the_units_taken_out_and_returns_with_them(
    equipment_type: EquipmentType,
) -> None:
    assert _free(equipment_type) == 10

    damaged = _mark(equipment_type, 3)
    assert _free(equipment_type) == 7

    _mark(equipment_type, 2, "under_maintenance")
    assert _free(equipment_type) == 5

    services.return_to_service(damaged.id, resolved_by=TECHNICAL_SUPPORT_ID, now=LATER)
    assert _free(equipment_type) == 8


def test_other_equipment_keeps_its_availability(
    equipment_type: EquipmentType, microphone: EquipmentType
) -> None:
    _mark(equipment_type, 3)

    free = services.available_quantity(microphone.id, EVENT_STARTS_AT, EVENT_ENDS_AT)
    assert free == 20


# --- AC3: reservations left short are flagged, never deleted ------------------------


def test_a_reservation_the_change_leaves_short_is_flagged_and_kept(
    db_session: Session,
    saved_users: list[User],
    eight_reserved: EquipmentReservation,
    equipment_type: EquipmentType,
) -> None:
    _mark(equipment_type, 3)

    shown = services.list_reservations_for_event(
        TECHNICAL_SUPPORT_ID, "EVR-AAAAAAAA", viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )
    assert [(reservation.quantity, reservation.needs_attention) for reservation in shown] == [
        (8, True)
    ]
    assert _flagged_quantities(db_session) == [8]


def test_a_reservation_the_change_still_covers_is_not_flagged(
    db_session: Session, eight_reserved: EquipmentReservation, equipment_type: EquipmentType
) -> None:
    # Ten held, two out: eight left for the eight reserved. One more out would be short.
    _mark(equipment_type, 2)

    assert _flagged_quantities(db_session) == []


def test_only_the_reservations_the_change_leaves_short_are_flagged(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    save: Save,
    make_reservation: MakeReservation,
) -> None:
    save(make_reservation(equipment_type, 8, EVENT_STARTS_AT, EVENT_ENDS_AT))
    # Decoys: another type, another day with room to spare, and a day already over.
    save(make_reservation(microphone, 9, EVENT_STARTS_AT, EVENT_ENDS_AT))
    save(make_reservation(equipment_type, 2, OTHER_DAY_STARTS_AT, OTHER_DAY_ENDS_AT))
    save(make_reservation(equipment_type, 9, ALREADY_OVER_STARTS_AT, ALREADY_OVER_ENDS_AT))

    _mark(equipment_type, 3)

    assert _flagged_quantities(db_session) == [8]
    assert len(db_session.scalars(select(EquipmentReservation)).all()) == 4


def test_returning_the_units_clears_the_flag(
    db_session: Session, eight_reserved: EquipmentReservation, equipment_type: EquipmentType
) -> None:
    entry = _mark(equipment_type, 3)
    assert _flagged_quantities(db_session) == [8]

    services.return_to_service(entry.id, resolved_by=TECHNICAL_SUPPORT_ID, now=LATER)

    assert _flagged_quantities(db_session) == []


@pytest.fixture()
def competitor_reserves_while_locking(
    db_session: Session, saved_event_request: EventRequest, equipment_type: EquipmentType
) -> Iterator[None]:
    """Save eight units for the event at the moment the equipment type is locked.

    Stands in for a reservation that committed while this request waited for the lock
    (ADR-0037 section 3). SQLite has no row locks, so what the test checks is what
    Postgres relies on: the type's row is selected ``FOR UPDATE``, and the reservations
    are flagged only after that.
    """

    def _on_execute(state: ORMExecuteState) -> None:
        sql = str(state.statement.compile(dialect=postgresql.dialect()))
        if "FROM equipment_types" not in sql or "FOR UPDATE" not in sql:
            return
        competitor = insert(EquipmentReservation).values(
            event_id=saved_event_request.id,
            equipment_type_id=equipment_type.id,
            quantity=8,
            starts_at=EVENT_STARTS_AT,
            ends_at=EVENT_ENDS_AT,
            reserved_by=TECHNICAL_SUPPORT_ID,
        )
        state.session.connection().execute(competitor)

    event.listen(db_session, "do_orm_execute", _on_execute)
    yield
    event.remove(db_session, "do_orm_execute", _on_execute)


def test_a_reservation_committed_while_the_type_was_locked_is_checked_too(
    db_session: Session, equipment_type: EquipmentType, competitor_reserves_while_locking: None
) -> None:
    _mark(equipment_type, 3)

    assert _flagged_quantities(db_session) == [8]


# --- AC3: the responsible coordinator is notified -----------------------------------


def test_the_coordinator_is_told_once_per_event_and_nobody_else(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    save: Save,
    make_reservation: MakeReservation,
    notifications_of: NotificationsOf,
) -> None:
    save(make_reservation(equipment_type, 4, EVENT_STARTS_AT, EVENT_ENDS_AT))
    save(make_reservation(equipment_type, 4, EVENT_STARTS_AT, EVENT_ENDS_AT))

    _mark(equipment_type, 3)

    assert notifications_of(COORDINATOR_ID) == [
        (
            saved_event_request.id,
            "EVR-AAAAAAAA",
            "Partner Summit",
            NotificationKind.SIGNIFICANT_CHANGE,
            None,
        )
    ]
    assert notifications_of(TECHNICAL_SUPPORT_ID) == []


def test_the_notification_says_what_happened_to_the_equipment(
    eight_reserved: EquipmentReservation, equipment_type: EquipmentType
) -> None:
    _mark(equipment_type, 3)

    shown = NotificationSchema().dump(list_notifications_for_recipient(COORDINATOR_ID)[0])

    assert shown["link"] == "/events/EVR-AAAAAAAA"
    assert shown["detail"] == (
        "Equipment reserved for this event is no longer all available: "
        "some units were taken out of service."
    )


def test_nobody_is_told_when_no_reservation_is_left_short(
    eight_reserved: EquipmentReservation,
    equipment_type: EquipmentType,
    notifications_of: NotificationsOf,
) -> None:
    _mark(equipment_type, 2)

    assert notifications_of(COORDINATOR_ID) == []


def test_a_reservation_already_flagged_does_not_tell_the_coordinator_again(
    eight_reserved: EquipmentReservation,
    equipment_type: EquipmentType,
    notifications_of: NotificationsOf,
) -> None:
    _mark(equipment_type, 3)

    _mark(equipment_type, 1)

    assert len(notifications_of(COORDINATOR_ID)) == 1


def test_returning_units_tells_nobody(
    eight_reserved: EquipmentReservation,
    equipment_type: EquipmentType,
    notifications_of: NotificationsOf,
) -> None:
    entry = _mark(equipment_type, 3)

    services.return_to_service(entry.id, resolved_by=TECHNICAL_SUPPORT_ID, now=LATER)

    assert len(notifications_of(COORDINATOR_ID)) == 1


def test_an_event_with_no_coordinator_is_flagged_and_the_gap_is_logged(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    equipment_type: EquipmentType,
    save: Save,
    make_reservation: MakeReservation,
    caplog: pytest.LogCaptureFixture,
) -> None:
    save(make_event_request(coordinator_id=None))
    save(make_reservation(equipment_type, 8, EVENT_STARTS_AT, EVENT_ENDS_AT))

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _mark(equipment_type, 3)

    assert _flagged_quantities(db_session) == [8]
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_unassigned reference=EVR-AAAAAAAA"
    ]


# --- AC4: who changed the status, and when ------------------------------------------


def test_marking_records_who_and_when(
    db_session: Session, saved_users: list[User], equipment_type: EquipmentType
) -> None:
    shown = _mark(equipment_type, 3)

    stored = db_session.scalars(select(EquipmentOutOfService)).one()
    assert (stored.recorded_by, stored.recorded_at) == (TECHNICAL_SUPPORT_ID, NOW)
    assert (shown.recorded_by, shown.recorded_at) == (TECHNICIAN_NAME, NOW)
    assert (shown.resolved_by, shown.resolved_at) == (None, None)


def test_returning_records_who_and_when(
    db_session: Session, saved_users: list[User], equipment_type: EquipmentType
) -> None:
    entry = _mark(equipment_type, 3)

    shown = services.return_to_service(
        entry.id, resolved_by=str(OTHER_TECHNICAL_SUPPORT_ID), now=LATER
    )

    stored = db_session.scalars(select(EquipmentOutOfService)).one()
    assert (stored.resolved_by, stored.resolved_at) == (OTHER_TECHNICAL_SUPPORT_ID, LATER)
    assert (shown.resolved_by, shown.resolved_at) == (TECHNICIAN_NAME, LATER)
    # Who first took them out is kept.
    assert (stored.recorded_by, stored.recorded_at) == (TECHNICAL_SUPPORT_ID, NOW)
