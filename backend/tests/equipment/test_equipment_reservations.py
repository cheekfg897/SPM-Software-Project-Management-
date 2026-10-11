"""Unit tests for SCRUM-46 "Reserve equipment" (ADR-0037).

``equipment_reservations`` holds the units reserved for one event's period (AC1, AC4);
``equipment_out_of_service`` holds units recorded as damaged or under maintenance, which
SCRUM-45 AC2 excludes from availability. ``reserve_equipment`` reserves up to what is
free for the event's period (AC1), refuses more and says how many are free (AC3), and
records the reservation in the event's history. They run against ``db_session``, an
in-memory SQLite database, so the check constraints and queries really run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event, insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import ORMExecuteState, Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment import services
from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
)
from app.modules.equipment.schemas import EquipmentReservationSchema
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import RESERVATIONS_CLOSED_MESSAGE, list_event_history

pytestmark = pytest.mark.scrum_46

MakeReservation = Callable[[EquipmentType, int, datetime, datetime], EquipmentReservation]
MakeOutOfService = Callable[..., EquipmentOutOfService]
Save = Callable[..., None]

STARTS_AT = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc)


def test_a_reservation_keeps_its_quantity_and_exact_period(
    db_session: Session,
    equipment_type: EquipmentType,
    make_reservation: MakeReservation,
    save: Save,
) -> None:
    save(make_reservation(equipment_type, 4, STARTS_AT, ENDS_AT))

    db_session.expire_all()
    stored = db_session.scalars(select(EquipmentReservation)).one()
    assert stored.event_id == 1
    assert stored.equipment_type_id == equipment_type.id
    assert stored.quantity == 4
    assert stored.starts_at == STARTS_AT
    assert stored.ends_at == ENDS_AT
    assert stored.reserved_by == 3
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_a_reservation_of_no_units_is_refused(
    db_session: Session,
    equipment_type: EquipmentType,
    make_reservation: MakeReservation,
    save: Save,
) -> None:
    with pytest.raises(IntegrityError):
        save(make_reservation(equipment_type, 0, STARTS_AT, ENDS_AT))

    db_session.rollback()
    assert db_session.scalars(select(EquipmentReservation)).all() == []


def test_an_out_of_service_row_is_unresolved_until_someone_resolves_it(
    db_session: Session,
    equipment_type: EquipmentType,
    make_out_of_service: MakeOutOfService,
    save: Save,
) -> None:
    save(make_out_of_service(equipment_type, 2))

    db_session.expire_all()
    stored = db_session.scalars(select(EquipmentOutOfService)).one()
    assert stored.quantity == 2
    assert stored.reason is OutOfServiceReason.DAMAGED
    assert stored.recorded_by == 3
    assert stored.recorded_at == datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    assert stored.resolved_at is None


def test_an_out_of_service_row_of_no_units_is_refused(
    db_session: Session,
    equipment_type: EquipmentType,
    make_out_of_service: MakeOutOfService,
    save: Save,
) -> None:
    with pytest.raises(IntegrityError):
        save(make_out_of_service(equipment_type, 0))

    db_session.rollback()
    assert db_session.scalars(select(EquipmentOutOfService)).all() == []


# --- reserving equipment for an event (AC1-AC3) -------------------------------------

REFERENCE = "EVR-AAAAAAAA"
#: Same day as ``saved_event_request``, 12:00-17:00 against its 09:00-17:00.
OVERLAPPING_REFERENCE = "EVR-BBBBBBBB"
#: The day after ``saved_event_request``.
LATER_REFERENCE = "EVR-CCCCCCCC"
#: Technical Support Staff 5 in ``saved_users``, who has the factory's default name.
TECHNICAL_SUPPORT_ID = 5
TECHNICAL_SUPPORT_NAME = "Alice Example"
#: ``saved_event_request`` runs 09:00-17:00 in Singapore (UTC+8).
EVENT_STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
EVENT_ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
AT_LEAST_ONE = "Quantity must be at least 1."


def _reserve(
    reference: str,
    equipment_type: EquipmentType,
    quantity: int,
    *,
    reserved_by: int = TECHNICAL_SUPPORT_ID,
) -> services.ReservationAsShown:
    payload = {"equipment_type_id": equipment_type.id, "quantity": quantity}
    return services.reserve_equipment(reference, payload, reserved_by=reserved_by)


def _reserved_quantities(db_session: Session) -> list[int]:
    statement = select(EquipmentReservation.quantity).order_by(EquipmentReservation.id)
    return list(db_session.scalars(statement))


def _available_for(reference: str) -> int:
    """What is free of the only equipment type in the catalogue for the event."""
    (row,) = services.equipment_availability_for_event(
        TECHNICAL_SUPPORT_ID, reference, viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )
    return row.available


def _reservations_of(reference: str) -> list[services.ReservationAsShown]:
    """The event's reservations as Technical Support, who may read any event's."""
    return services.list_reservations_for_event(
        TECHNICAL_SUPPORT_ID, reference, viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )


def _history_of(reference: str) -> list[tuple[EventHistoryKind, str | None, dict[str, Any]]]:
    entries = list_event_history(
        TECHNICAL_SUPPORT_ID, reference, viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )
    return [(entry.kind, entry.actor_name, entry.details) for entry in entries]


@pytest.fixture()
def overlapping_event(make_event_request: Callable[..., EventRequest], save: Save) -> EventRequest:
    event_request = make_event_request(reference=OVERLAPPING_REFERENCE, start_time=time(12, 0))
    save(event_request)
    return event_request


@pytest.fixture()
def later_event(make_event_request: Callable[..., EventRequest], save: Save) -> EventRequest:
    event_request = make_event_request(reference=LATER_REFERENCE, proposed_date=date(2026, 10, 16))
    save(event_request)
    return event_request


def test_reserving_exactly_what_is_free_saves_it_for_the_events_period(
    db_session: Session, saved_event_request: EventRequest, equipment_type: EquipmentType
) -> None:
    # AC1: all ten projectors are free, and all ten are reserved.
    reservation = _reserve(REFERENCE, equipment_type, 10)

    db_session.expire_all()
    stored = db_session.scalars(select(EquipmentReservation)).one()
    assert stored.id == reservation.id
    assert stored.event_id == saved_event_request.id
    assert stored.equipment_type_id == equipment_type.id
    assert stored.quantity == 10
    assert stored.starts_at == EVENT_STARTS_AT
    assert stored.ends_at == EVENT_ENDS_AT
    assert stored.reserved_by == TECHNICAL_SUPPORT_ID


def test_reserving_one_more_than_is_free_is_refused_naming_what_is_free(
    db_session: Session,
    saved_event_request: EventRequest,
    overlapping_event: EventRequest,
    equipment_type: EquipmentType,
) -> None:
    # AC3: four of ten are reserved for an overlapping event, so six are free.
    _reserve(OVERLAPPING_REFERENCE, equipment_type, 4)

    with pytest.raises(ValidationError) as caught:
        _reserve(REFERENCE, equipment_type, 7)

    assert caught.value.message == "Only 6 available for this period."
    assert caught.value.details == {"quantity": ["Only 6 available for this period."]}
    assert _reserved_quantities(db_session) == [4]
    assert _history_of(REFERENCE) == []


def test_a_reservation_leaves_less_for_an_overlapping_event_only(
    saved_event_request: EventRequest,
    overlapping_event: EventRequest,
    later_event: EventRequest,
    equipment_type: EquipmentType,
) -> None:
    # AC2: four reserved is four fewer for an event at the same time, none fewer later.
    assert (_available_for(OVERLAPPING_REFERENCE), _available_for(LATER_REFERENCE)) == (10, 10)

    _reserve(REFERENCE, equipment_type, 4)

    assert (_available_for(OVERLAPPING_REFERENCE), _available_for(LATER_REFERENCE)) == (6, 10)


def test_reservations_of_one_type_for_one_event_add_up(
    db_session: Session, saved_event_request: EventRequest, equipment_type: EquipmentType
) -> None:
    _reserve(REFERENCE, equipment_type, 4)
    _reserve(REFERENCE, equipment_type, 6)

    assert _reserved_quantities(db_session) == [4, 6]
    assert _available_for(REFERENCE) == 0


def test_a_second_request_is_refused_once_the_first_took_everything_free(
    db_session: Session,
    saved_event_request: EventRequest,
    overlapping_event: EventRequest,
    equipment_type: EquipmentType,
) -> None:
    # Review Focus 3: the second request counts what the first one reserved.
    _reserve(REFERENCE, equipment_type, 10)

    with pytest.raises(ValidationError) as caught:
        _reserve(OVERLAPPING_REFERENCE, equipment_type, 1)

    assert caught.value.message == "Only 0 available for this period."
    assert _reserved_quantities(db_session) == [10]


@pytest.fixture()
def competitor_reserves_while_locking(
    db_session: Session, overlapping_event: EventRequest, equipment_type: EquipmentType
) -> Iterator[None]:
    """Save four units for another event at the moment the equipment type is locked.

    Stands in for a competing request that committed while this one waited for the
    lock. SQLite has no row locks, so one request can't be made to wait for another
    here. What the test checks is what Postgres relies on: the equipment type's row is
    selected ``FOR UPDATE`` (as Postgres would receive it), and what is free is counted
    only after that, so the competitor's units are counted.
    """

    def _on_execute(state: ORMExecuteState) -> None:
        sql = str(state.statement.compile(dialect=postgresql.dialect()))
        if "FROM equipment_types" not in sql or "FOR UPDATE" not in sql:
            return
        competitor = insert(EquipmentReservation).values(
            event_id=overlapping_event.id,
            equipment_type_id=equipment_type.id,
            quantity=4,
            starts_at=EVENT_STARTS_AT,
            ends_at=EVENT_ENDS_AT,
            reserved_by=TECHNICAL_SUPPORT_ID,
        )
        state.session.connection().execute(competitor)

    session = db_session()
    event.listen(session, "do_orm_execute", _on_execute)
    yield
    event.remove(session, "do_orm_execute", _on_execute)


def test_what_is_free_is_counted_after_the_equipment_type_is_locked(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    competitor_reserves_while_locking: None,
) -> None:
    # Review Focus 3: ten were free when the request came in, but the competitor took
    # four before the lock was granted, so seven is one too many. A guard that counted
    # before locking, or never locked, would let all seven through.
    with pytest.raises(ValidationError) as caught:
        _reserve(REFERENCE, equipment_type, 7)

    assert caught.value.message == "Only 6 available for this period."


def test_the_reservation_is_recorded_in_the_events_history(
    saved_users: list[User], saved_event_request: EventRequest, equipment_type: EquipmentType
) -> None:
    reservation = _reserve(REFERENCE, equipment_type, 4)

    expected_details = {
        "equipment_type_id": equipment_type.id,
        "equipment_type_name": "Projector",
        "quantity": 4,
        "reservation_id": reservation.id,
    }
    assert _history_of(REFERENCE) == [
        (EventHistoryKind.EQUIPMENT_RESERVED, TECHNICAL_SUPPORT_NAME, expected_details)
    ]


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        ({"equipment_type_id": 1, "quantity": 0}, {"quantity": [AT_LEAST_ONE]}),
        ({"equipment_type_id": 1, "quantity": -3}, {"quantity": [AT_LEAST_ONE]}),
        ({"equipment_type_id": 1}, {"quantity": ["Missing data for required field."]}),
        ({"equipment_type_id": 1, "quantity": "two"}, {"quantity": ["Not a valid integer."]}),
        ({"equipment_type_id": 1, "quantity": True}, {"quantity": ["Not a valid integer."]}),
        ({"equipment_type_id": 1, "quantity": 1.5}, {"quantity": ["Not a valid integer."]}),
        ({"quantity": 1}, {"equipment_type_id": ["Missing data for required field."]}),
        (
            {"equipment_type_id": 0, "quantity": 1},
            {"equipment_type_id": ["equipment_type_id must be a positive number."]},
        ),
        (
            {"equipment_type_id": 1, "quantity": 1, "event_id": 2},
            {"event_id": ["Unknown field."]},
        ),
    ],
    ids=[
        "quantity-zero",
        "quantity-negative",
        "quantity-missing",
        "quantity-text",
        "quantity-boolean",
        "quantity-fraction",
        "type-missing",
        "type-zero",
        "event-sent",
    ],
)
def test_an_invalid_request_is_refused_field_by_field_and_nothing_is_saved(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    payload: dict[str, Any],
    details: dict[str, list[str]],
) -> None:
    # Review Focus 2.
    with pytest.raises(ValidationError) as caught:
        services.reserve_equipment(REFERENCE, payload, reserved_by=TECHNICAL_SUPPORT_ID)

    assert caught.value.details == details
    assert _reserved_quantities(db_session) == []


def test_an_equipment_type_not_in_the_catalogue_is_refused_on_its_field(
    db_session: Session, saved_event_request: EventRequest
) -> None:
    payload = {"equipment_type_id": 999, "quantity": 1}

    with pytest.raises(ValidationError) as caught:
        services.reserve_equipment(REFERENCE, payload, reserved_by=TECHNICAL_SUPPORT_ID)

    assert caught.value.details == {"equipment_type_id": ["Equipment type not found."]}
    assert _reserved_quantities(db_session) == []


def test_a_cancelled_event_takes_no_reservation_and_says_why(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    save: Save,
) -> None:
    # Which statuses close reservations is the events module's rule, tested there.
    saved_event_request.status = EventRequestStatus.CANCELLED
    save(saved_event_request)

    with pytest.raises(services.EquipmentNotReservableError) as caught:
        _reserve(REFERENCE, equipment_type, 1)

    assert caught.value.status_code == 409
    assert caught.value.message == RESERVATIONS_CLOSED_MESSAGE
    assert _reserved_quantities(db_session) == []


def test_a_draft_or_an_unknown_event_is_not_found(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    equipment_type: EquipmentType,
    save: Save,
) -> None:
    save(make_event_request(status=EventRequestStatus.DRAFT))

    with pytest.raises(NotFoundError):
        _reserve(REFERENCE, equipment_type, 1)
    with pytest.raises(NotFoundError):
        _reserve("EVR-ZZZZZZZZ", equipment_type, 1)
    assert _reserved_quantities(db_session) == []


def test_the_reservation_schema_dumps_exactly_the_agreed_fields_in_business_time() -> None:
    reservation = services.ReservationAsShown(
        id=12,
        equipment_type_id=2,
        equipment_type_name="Projector",
        quantity=4,
        starts_at=EVENT_STARTS_AT,
        ends_at=EVENT_ENDS_AT,
        reserved_by=TECHNICAL_SUPPORT_NAME,
        created_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )

    assert EquipmentReservationSchema().dump(reservation) == {
        "id": 12,
        "equipment_type_id": 2,
        "equipment_type_name": "Projector",
        "quantity": 4,
        "starts_at": "2026-10-15T09:00:00+08:00",
        "ends_at": "2026-10-15T17:00:00+08:00",
        "reserved_by": TECHNICAL_SUPPORT_NAME,
        "created_at": "2026-10-01T16:00:00+08:00",
    }


# --- reading an event's reservations (AC4) ------------------------------------------

COORDINATOR_NINE_ID = 9
COORDINATOR_NINE_NAME = "Coordinator Nine"


def _statements_run_listing_reservations(db_session: Session) -> int:
    """How many SQL statements listing the event's reservations takes cold."""
    statements: list[str] = []

    def _on_execute(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    db_session.expire_all()
    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", _on_execute)
    try:
        _reservations_of(REFERENCE)
    finally:
        event.remove(bind, "before_cursor_execute", _on_execute)
    return len(statements)


def test_a_reservation_is_returned_with_the_name_of_who_reserved_it(
    saved_users: list[User], saved_event_request: EventRequest, equipment_type: EquipmentType
) -> None:
    reservation = _reserve(REFERENCE, equipment_type, 4)

    assert reservation.reserved_by == TECHNICAL_SUPPORT_NAME
    assert reservation.equipment_type_name == "Projector"
    assert reservation.quantity == 4


def test_the_callers_user_id_may_arrive_as_the_text_a_token_holds(
    monkeypatch: pytest.MonkeyPatch,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
) -> None:
    # SQLite would store "5" as 5 anyway, so check the id as the history receives it.
    record = MagicMock()
    monkeypatch.setattr(services.events_services, "record_equipment_reserved", record)
    payload = {"equipment_type_id": equipment_type.id, "quantity": 1}

    services.reserve_equipment(REFERENCE, payload, reserved_by=str(TECHNICAL_SUPPORT_ID))

    assert record.call_args.kwargs["actor_id"] == TECHNICAL_SUPPORT_ID


def test_a_reserver_who_no_longer_has_an_account_is_shown_as_nobody(
    saved_event_request: EventRequest, equipment_type: EquipmentType
) -> None:
    reservation = _reserve(REFERENCE, equipment_type, 4)

    assert reservation.reserved_by is None


def test_an_events_reservations_are_listed_oldest_first_with_names(
    saved_users: list[User],
    saved_event_request: EventRequest,
    overlapping_event: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
) -> None:
    _reserve(REFERENCE, equipment_type, 3, reserved_by=TECHNICAL_SUPPORT_ID)
    _reserve(REFERENCE, microphone, 5, reserved_by=COORDINATOR_NINE_ID)
    _reserve(REFERENCE, equipment_type, 2, reserved_by=TECHNICAL_SUPPORT_ID)
    _reserve(OVERLAPPING_REFERENCE, equipment_type, 1)

    listed = _reservations_of(REFERENCE)

    assert [(row.equipment_type_name, row.quantity, row.reserved_by) for row in listed] == [
        ("Projector", 3, TECHNICAL_SUPPORT_NAME),
        ("Microphone", 5, COORDINATOR_NINE_NAME),
        ("Projector", 2, TECHNICAL_SUPPORT_NAME),
    ]


def test_an_event_with_no_reservations_lists_none(saved_event_request: EventRequest) -> None:
    assert _reservations_of(REFERENCE) == []


def test_the_reference_is_matched_ignoring_case_and_spaces(
    saved_event_request: EventRequest, equipment_type: EquipmentType
) -> None:
    _reserve(REFERENCE, equipment_type, 3)

    assert len(_reservations_of(" evr-aaaaaaaa ")) == 1


def test_listing_the_reservations_of_a_draft_or_unknown_event_is_not_found(
    make_event_request: Callable[..., EventRequest], save: Save
) -> None:
    save(make_event_request(status=EventRequestStatus.DRAFT))

    with pytest.raises(NotFoundError):
        _reservations_of(REFERENCE)
    with pytest.raises(NotFoundError):
        _reservations_of("EVR-ZZZZZZZZ")


def test_listing_reservations_does_not_query_per_reservation(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
) -> None:
    _reserve(REFERENCE, equipment_type, 1, reserved_by=TECHNICAL_SUPPORT_ID)
    for_one = _statements_run_listing_reservations(db_session)

    _reserve(REFERENCE, microphone, 1, reserved_by=COORDINATOR_NINE_ID)
    _reserve(REFERENCE, equipment_type, 1, reserved_by=TECHNICAL_SUPPORT_ID)

    assert _statements_run_listing_reservations(db_session) == for_one


def test_the_locked_read_replaces_what_the_session_already_holds(
    db_session: Session, equipment_type: EquipmentType
) -> None:
    # A copy loaded before the lock was taken may be stale: another request can have
    # committed since. The locked read must return the row as it is now.
    assert equipment_type.total_quantity == 10
    # synchronize_session=False keeps the session's copy at 10, as a real stale copy is.
    stale_copy_stays = update(EquipmentType).values(total_quantity=3)
    db_session.execute(stale_copy_stays, execution_options={"synchronize_session": False})
    assert equipment_type.total_quantity == 10

    locked = services._locked_equipment_type(equipment_type.id, db_session)

    assert locked.total_quantity == 3
