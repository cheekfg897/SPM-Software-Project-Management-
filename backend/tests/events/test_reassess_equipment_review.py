"""Unit tests for SCRUM-60: what Technical Support see of a marked reservation.

AC2: when availability is rechecked for the event's new period, any shortfall is shown
to Technical Support as they review the reservation. The event's own marked
reservations are left out of the count: they are the units being reassessed, and they
may still sit in an old period that overlaps the new one (ADR-0114).
AC6: until Technical Support act, the line is back on their list of requests awaiting
action (SCRUM-38), as is a line a timing change reopened (AC12).

The services run against ``db_session``; the edit moves ``saved_event_request`` from
15 Oct 2026, 09:00 to 17:00, to start an hour earlier, so the two periods overlap.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any

import pytest

from app.common.errors import NotFoundError
from app.modules.auth.permissions import Role
from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
)
from app.modules.equipment.services import (
    ReservationReassessment,
    list_reassessments_for_event,
    mark_event_reservations_for_reassessment,
    reserve_equipment,
)
from app.modules.events.models import EquipmentLineStatus, EventEquipmentLine, EventRequest
from app.modules.events.services import (
    EquipmentAwaitingAction,
    EventEdit,
    list_equipment_requests_awaiting_action,
)
from tests.conftest import ReserveAndReview

pytestmark = pytest.mark.scrum_60

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
OTHER_REFERENCE = "EVR-BBBBBBBB"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5
#: The day the awaiting-action list is read on: before every event here.
TODAY = date(2026, 10, 1)

#: The reservation's own period: 15 Oct 2026, 09:00 to 17:00 in Singapore.
OLD_STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
OLD_ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
#: The event's period once it starts an hour earlier: 15 Oct, 08:00 to 17:00.
NEW_STARTS_AT = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
NEW_ENDS_AT = OLD_ENDS_AT
EARLIER_START = {"start_time": "08:00"}


def _reassessment_of(viewer_id: int, viewer_role: Role) -> list[ReservationReassessment]:
    return list_reassessments_for_event(viewer_id, REFERENCE, viewer_role=viewer_role)


def _numbers(reassessment: ReservationReassessment) -> tuple[int, int, int]:
    """(reserved, available, shortfall)."""
    return reassessment.reserved_quantity, reassessment.available, reassessment.shortfall


def _listed(awaiting: list[EquipmentAwaitingAction]) -> list[tuple[str, list[int], list[int]]]:
    """Each entry as (reference, its line ids, the equipment types to reassess)."""
    rows = []
    for row in awaiting:
        line_ids = [line.id for line in row.equipment_lines]
        rows.append((row.event_request.reference, line_ids, row.equipment_type_ids_to_reassess))
    return rows


@pytest.fixture()
def other_event(make_event_request: Callable[..., EventRequest], save: Save) -> EventRequest:
    """Another event, on 15 Oct 2026, 09:00 to 17:00, inside the new period."""
    other = make_event_request(reference=OTHER_REFERENCE, coordinator_id=9)
    save(other)
    return other


@pytest.fixture()
def held_for_other_event(
    other_event: EventRequest, equipment_type: EquipmentType, save: Save
) -> Callable[[int], EquipmentReservation]:
    """Hold ``quantity`` projectors for ``other_event``'s period."""

    def _hold(quantity: int) -> EquipmentReservation:
        reservation = EquipmentReservation(
            event_id=other_event.id,
            equipment_type_id=equipment_type.id,
            quantity=quantity,
            starts_at=OLD_STARTS_AT,
            ends_at=OLD_ENDS_AT,
            reserved_by=TECHNICAL_SUPPORT_ID,
        )
        save(reservation)
        return reservation

    return _hold


# --------------------------------------------------------------------------
# AC2 — the recheck for the new period, and any shortfall
# --------------------------------------------------------------------------


def test_a_marked_reservation_is_shown_with_its_old_period_and_the_events_new_one(
    two_projectors: EventEquipmentLine, equipment_type: EquipmentType, edit_event: EditEvent
) -> None:
    edit_event(COORDINATOR_ID, EARLIER_START)

    [reassessment] = _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF)

    assert reassessment.equipment_type_id == equipment_type.id
    assert reassessment.equipment_type_name == "Projector"
    assert [
        (shown.id, shown.quantity, shown.starts_at, shown.ends_at)
        for shown in reassessment.reservations
    ] == [(1, 2, OLD_STARTS_AT, OLD_ENDS_AT)]
    assert (reassessment.starts_at, reassessment.ends_at) == (NEW_STARTS_AT, NEW_ENDS_AT)
    # Its own two units, still held for the overlapping old period, are not counted.
    assert _numbers(reassessment) == (2, 10, 0)


@pytest.mark.parametrize(
    ("held_elsewhere", "numbers"),
    [(8, (2, 2, 0)), (9, (2, 1, 1)), (10, (2, 0, 2))],
    ids=["exactly-enough", "one-short", "none-free"],
)
def test_the_shortfall_is_what_the_new_period_cannot_give_of_what_is_reserved(
    two_projectors: EventEquipmentLine,
    held_for_other_event: Callable[[int], EquipmentReservation],
    edit_event: EditEvent,
    held_elsewhere: int,
    numbers: tuple[int, int, int],
) -> None:
    held_for_other_event(held_elsewhere)
    edit_event(COORDINATOR_ID, EARLIER_START)

    [reassessment] = _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF)

    assert _numbers(reassessment) == numbers


def test_units_out_of_service_are_not_free_for_the_new_period(
    two_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    save: Save,
) -> None:
    save(
        EquipmentOutOfService(
            equipment_type_id=equipment_type.id,
            quantity=9,
            reason=OutOfServiceReason.DAMAGED,
            recorded_by=TECHNICAL_SUPPORT_ID,
            recorded_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
    )
    edit_event(COORDINATOR_ID, EARLIER_START)

    [reassessment] = _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF)

    assert _numbers(reassessment) == (2, 1, 1)


def test_units_reserved_for_the_new_period_since_the_change_are_counted(
    saved_event_request: EventRequest,
    make_equipment_type: Callable[..., EquipmentType],
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    save: Save,
) -> None:
    """Only the marked units are set aside: the new one is held for the new period."""
    screens = make_equipment_type(name="Screen", total_quantity=3)
    save(screens)
    reserve_and_review(screens, quantity=3, reserved=2, provided=3)
    edit_event(COORDINATOR_ID, EARLIER_START)
    units = {"equipment_type_id": screens.id, "quantity": 1}
    reserve_equipment(REFERENCE, units, reserved_by=TECHNICAL_SUPPORT_ID)

    [reassessment] = _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF)

    assert _numbers(reassessment) == (2, 2, 0)


def test_several_marked_reservations_of_a_type_are_reassessed_together_oldest_first(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
) -> None:
    reserve_and_review(equipment_type, quantity=5, reserved=2, provided=5)
    units = {"equipment_type_id": equipment_type.id, "quantity": 3}
    reserve_equipment(REFERENCE, units, reserved_by=TECHNICAL_SUPPORT_ID)
    edit_event(COORDINATOR_ID, EARLIER_START)

    [reassessment] = _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF)

    assert [(shown.id, shown.quantity) for shown in reassessment.reservations] == [(1, 2), (2, 3)]
    assert _numbers(reassessment) == (5, 10, 0)


def test_each_equipment_type_is_reassessed_on_its_own_by_name(
    two_projectors: EventEquipmentLine,
    microphone: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
) -> None:
    reserve_and_review(microphone, quantity=4, reserved=4, provided=4)
    edit_event(COORDINATOR_ID, EARLIER_START)

    reassessments = _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF)

    assert [(row.equipment_type_name, row.reserved_quantity) for row in reassessments] == [
        ("Microphone", 4),
        ("Projector", 2),
    ]


def test_an_event_with_nothing_marked_has_nothing_to_reassess(
    two_projectors: EventEquipmentLine, edit_event: EditEvent
) -> None:
    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF) == []


def test_another_events_marked_reservation_is_left_out(
    two_projectors: EventEquipmentLine,
    other_event: EventRequest,
    held_for_other_event: Callable[[int], EquipmentReservation],
) -> None:
    held_for_other_event(3)
    mark_event_reservations_for_reassessment(other_event.id)

    assert _reassessment_of(TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF) == []


def test_the_assigned_coordinator_sees_what_technical_support_see(
    two_projectors: EventEquipmentLine, edit_event: EditEvent
) -> None:
    edit_event(COORDINATOR_ID, EARLIER_START)

    shown_to_coordinator = _reassessment_of(COORDINATOR_ID, Role.EVENT_COORDINATOR)

    assert shown_to_coordinator == _reassessment_of(
        TECHNICAL_SUPPORT_ID, Role.TECHNICAL_SUPPORT_STAFF
    )


def test_a_coordinator_not_assigned_to_the_event_is_told_it_is_not_found(
    two_projectors: EventEquipmentLine, edit_event: EditEvent
) -> None:
    edit_event(COORDINATOR_ID, EARLIER_START)

    with pytest.raises(NotFoundError) as exc_info:
        _reassessment_of(9, Role.EVENT_COORDINATOR)

    assert exc_info.value.message == "Event request not found."


# --------------------------------------------------------------------------
# AC6, AC12 — back on Technical Support's list of requests awaiting action
# --------------------------------------------------------------------------


def test_a_fulfilled_line_is_listed_again_once_its_reservation_is_marked(
    two_projectors: EventEquipmentLine,
    microphone: EquipmentType,
    reserve_and_review: ReserveAndReview,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
) -> None:
    """The microphones, fulfilled with nothing reserved, have nothing to reassess."""
    reserve_and_review(microphone, quantity=4, reserved=0, provided=4)
    assert list_equipment_requests_awaiting_action(today=TODAY) == []

    edit_event(COORDINATOR_ID, EARLIER_START)

    awaiting = list_equipment_requests_awaiting_action(today=TODAY)
    assert _listed(awaiting) == [(REFERENCE, [two_projectors.id], [equipment_type.id])]


def test_a_line_a_timing_change_reopened_is_listed_with_nothing_to_reassess(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
) -> None:
    line = reserve_and_review(equipment_type, quantity=2, reserved=0, provided=0)

    edit_event(COORDINATOR_ID, EARLIER_START)

    awaiting = list_equipment_requests_awaiting_action(today=TODAY)
    assert _listed(awaiting) == [(REFERENCE, [line.id], [])]


@pytest.fixture()
def other_events_reserved_line(
    other_event: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    held_for_other_event: Callable[[int], EquipmentReservation],
    save: Save,
) -> EventEquipmentLine:
    """``other_event``'s projector line, fulfilled, with its 3 projectors held."""
    other_line = make_equipment_line(other_event, equipment_type, quantity=3)
    other_line.status = EquipmentLineStatus.FULFILLED
    other_line.provided_quantity = 3
    save(other_line)
    held_for_other_event(3)
    return other_line


def test_another_events_marked_reservation_does_not_list_this_events_line(
    two_projectors: EventEquipmentLine,
    other_event: EventRequest,
    other_events_reserved_line: EventEquipmentLine,
    equipment_type: EquipmentType,
) -> None:
    """Both events have a fulfilled projector line; only the other's is marked."""
    mark_event_reservations_for_reassessment(other_event.id)

    awaiting = list_equipment_requests_awaiting_action(today=TODAY)

    assert _listed(awaiting) == [
        (OTHER_REFERENCE, [other_events_reserved_line.id], [equipment_type.id])
    ]


def test_each_listed_event_names_only_its_own_types_to_reassess(
    saved_event_request: EventRequest,
    two_projectors: EventEquipmentLine,
    other_event: EventRequest,
    other_events_reserved_line: EventEquipmentLine,
    equipment_type: EquipmentType,
) -> None:
    """Both events' projector reservations are marked; each names the type once."""
    mark_event_reservations_for_reassessment(saved_event_request.id)
    mark_event_reservations_for_reassessment(other_event.id)

    awaiting = list_equipment_requests_awaiting_action(today=TODAY)

    assert _listed(awaiting) == [
        (REFERENCE, [two_projectors.id], [equipment_type.id]),
        (OTHER_REFERENCE, [other_events_reserved_line.id], [equipment_type.id]),
    ]
