"""Unit tests for SCRUM-45 (is enough equipment free?).

Equipment is only held for an event's own period, so two reservations conflict when
their periods overlap. Availability is the units held, less the overlapping
reservations and the units out of service. They run against ``db_session`` so the rules
are checked through real queries, not by reading the SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.equipment import services
from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
)
from app.modules.equipment.schemas import EquipmentAvailabilitySchema
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_45

Save = Callable[..., None]


def _at(hour: int, day: int = 3) -> datetime:
    return datetime(2026, 11, day, hour, 0, tzinfo=timezone.utc)


def _reservation(
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


def _out_of_service(
    equipment_type: EquipmentType, quantity: int, *, resolved_at: datetime | None = None
) -> EquipmentOutOfService:
    return EquipmentOutOfService(
        equipment_type_id=equipment_type.id,
        quantity=quantity,
        reason=OutOfServiceReason.DAMAGED,
        recorded_by=3,
        recorded_at=_at(8, day=1),
        resolved_at=resolved_at,
    )


def _overlapping_event_ids(
    db_session: Session, equipment_type: EquipmentType, save: Save, *, other: tuple
) -> list[int]:
    """Reserve 10:00-12:00 for event 1, then list the events overlapping ``other``."""
    save(_reservation(equipment_type, 1, _at(10), _at(12)))
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
    db_session: Session, equipment_type: EquipmentType, save: Save, other, description
) -> None:
    assert _overlapping_event_ids(db_session, equipment_type, save, other=other) == [1], description


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
    db_session: Session, equipment_type: EquipmentType, save: Save, other, description
) -> None:
    # No setup or turnaround buffer for equipment, so abutting periods are free (AC5).
    assert _overlapping_event_ids(db_session, equipment_type, save, other=other) == [], description


def test_available_quantity_subtracts_reservations_for_an_overlapping_event(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # AC1: ten projectors held, four reserved for an overlapping event -> six available.
    save(_reservation(equipment_type, 4, _at(10), _at(12)))

    assert services.available_quantity(equipment_type.id, _at(11), _at(13)) == 6


def test_available_quantity_adds_up_several_overlapping_reservations(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    save(
        _reservation(equipment_type, 4, _at(10), _at(12)),
        _reservation(equipment_type, 3, _at(9), _at(11)),
    )

    assert services.available_quantity(equipment_type.id, _at(10), _at(11)) == 3


def test_available_quantity_ignores_reservations_that_do_not_overlap(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # AC5: an event that starts as the other ends sees all ten.
    save(_reservation(equipment_type, 4, _at(10), _at(12)))

    assert services.available_quantity(equipment_type.id, _at(12), _at(14)) == 10


def test_available_quantity_ignores_reservations_of_other_equipment_types(
    db_session: Session,
    equipment_type: EquipmentType,
    make_equipment_type: Callable[..., EquipmentType],
    save: Save,
) -> None:
    other_type = make_equipment_type(name="Microphone")
    save(other_type)
    save(_reservation(other_type, 4, _at(10), _at(12)))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 10


def test_available_quantity_subtracts_unresolved_out_of_service_units(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # AC2: two damaged units are two fewer, whatever the period asked about.
    save(_out_of_service(equipment_type, 2))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 8


def test_available_quantity_ignores_resolved_out_of_service_units(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    save(_out_of_service(equipment_type, 2, resolved_at=_at(9, day=2)))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 10


def test_available_quantity_combines_reservations_and_out_of_service_units(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    save(_reservation(equipment_type, 4, _at(10), _at(12)), _out_of_service(equipment_type, 2))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 4


def test_available_quantity_never_goes_below_zero(
    db_session: Session, equipment_type: EquipmentType, save: Save
) -> None:
    # Units can break after they were reserved, leaving more committed than held.
    save(_reservation(equipment_type, 8, _at(10), _at(12)), _out_of_service(equipment_type, 5))

    assert services.available_quantity(equipment_type.id, _at(10), _at(12)) == 0


def test_available_quantity_of_an_unknown_equipment_type_is_not_found(
    db_session: Session,
) -> None:
    with pytest.raises(NotFoundError):
        services.available_quantity(999, _at(10), _at(12))


# --- availability for an event, with the shortfall (SCRUM-45 AC3, AC4) ---------------

EVENT_REFERENCE = "EVR-AAAAAAAA"


def _on_event_day(hour: int) -> datetime:
    """A UTC instant on 15 October 2026, the day ``saved_event_request`` runs."""
    return datetime(2026, 10, 15, hour, 0, tzinfo=timezone.utc)


def _rows_by_name(rows: list[services.EquipmentAvailability]) -> dict[str, tuple[int, int, int]]:
    return {row.equipment_type_name: (row.available, row.requested, row.shortfall) for row in rows}


def test_a_request_for_ten_against_six_available_reports_a_shortfall_of_four(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Save,
) -> None:
    # Ten projectors held, four reserved for an overlapping event, ten requested.
    save(make_equipment_line(saved_event_request, equipment_type, quantity=10))
    save(_reservation(equipment_type, 4, _on_event_day(0), _on_event_day(23)))

    rows = services.equipment_availability_for_event(EVENT_REFERENCE, session=db_session)

    assert _rows_by_name(rows) == {"Projector": (6, 10, 4)}


def test_a_request_that_is_met_reports_no_shortfall(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Save,
) -> None:
    save(make_equipment_line(saved_event_request, equipment_type, quantity=6))
    save(_reservation(equipment_type, 4, _on_event_day(0), _on_event_day(23)))

    rows = services.equipment_availability_for_event(EVENT_REFERENCE, session=db_session)

    assert _rows_by_name(rows) == {"Projector": (6, 6, 0)}


def test_an_event_with_no_lines_gets_every_type_with_nothing_requested(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
) -> None:
    rows = services.equipment_availability_for_event(EVENT_REFERENCE, session=db_session)

    assert _rows_by_name(rows) == {"Microphone": (20, 0, 0), "Projector": (10, 0, 0)}


def test_availability_is_listed_by_type_name_with_its_id(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
) -> None:
    rows = services.equipment_availability_for_event(EVENT_REFERENCE, session=db_session)

    assert [(row.equipment_type_id, row.equipment_type_name) for row in rows] == [
        (microphone.id, "Microphone"),
        (equipment_type.id, "Projector"),
    ]


def test_an_out_of_service_unit_shows_in_the_shortfall(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Save,
) -> None:
    save(make_equipment_line(saved_event_request, equipment_type, quantity=10))
    save(_out_of_service(equipment_type, 2))

    rows = services.equipment_availability_for_event(EVENT_REFERENCE, session=db_session)

    assert _rows_by_name(rows) == {"Projector": (8, 10, 2)}


@pytest.mark.parametrize(
    ("other_start", "other_end", "available"),
    [
        # The event runs 09:00-17:00 in Singapore, which is 01:00-09:00 UTC.
        (_on_event_day(9), _on_event_day(12), 10),  # starts exactly as the event ends
        (_on_event_day(0), _on_event_day(1), 10),  # ends exactly as the event starts
        (_on_event_day(8), _on_event_day(12), 6),  # last hour overlaps
        (_on_event_day(0), _on_event_day(2), 6),  # first hour overlaps
    ],
)
def test_availability_uses_the_events_own_hours_not_the_whole_day(
    db_session: Session,
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    save: Save,
    other_start: datetime,
    other_end: datetime,
    available: int,
) -> None:
    # AC4, AC5: the same-day reservation only counts when its hours overlap the event's.
    save(_reservation(equipment_type, 4, other_start, other_end))

    rows = services.equipment_availability_for_event(EVENT_REFERENCE, session=db_session)

    assert rows[0].available == available


def test_availability_of_a_draft_is_not_found(
    db_session: Session,
    make_event_request: Callable[..., EventRequest],
    save: Save,
) -> None:
    save(make_event_request(status=EventRequestStatus.DRAFT))

    with pytest.raises(NotFoundError):
        services.equipment_availability_for_event(EVENT_REFERENCE, session=db_session)


def test_availability_of_an_unknown_event_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        services.equipment_availability_for_event("EVR-ZZZZZZZZ", session=db_session)


def test_the_availability_schema_dumps_exactly_the_agreed_fields() -> None:
    row = services.EquipmentAvailability(
        equipment_type_id=3,
        equipment_type_name="Projector",
        available=6,
        requested=10,
        shortfall=4,
    )

    assert EquipmentAvailabilitySchema().dump(row) == {
        "equipment_type_id": 3,
        "equipment_type_name": "Projector",
        "available": 6,
        "requested": 10,
        "shortfall": 4,
    }
