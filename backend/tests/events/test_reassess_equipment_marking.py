"""Unit tests for SCRUM-60 "Reassess equipment reservations after a timing change".

What a change marks (ADR-0114):

* AC1: a saved change to the event's date or time marks every reservation for
  reassessment, and Technical Support Staff are told.
* AC6: a marked reservation stays held for its old period until Technical Support act.
* AC7: a change to none of date, time or quantity marks nothing.
* AC8: a new quantity on a line marks that line's reservation.
* AC12: a date or time change reopens every line recorded unavailable or partially
  fulfilled; a reopened line keeps its reservation (decision 2).
* SCRUM-33 AC9: an event in Safety Review that this leaves unsettled goes back to
  Approved (ADR-0107).

The services run against ``db_session``, so every row is read back as saved.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentReservation, EquipmentType
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EventEdit,
    reassess_equipment_after_timing_change,
    update_equipment_line,
)
from app.modules.notifications.services import NotificationKind
from tests.conftest import ReservationRow, ReserveAndReview

pytestmark = pytest.mark.scrum_60

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
ReservationRows = Callable[[], list[ReservationRow]]
ReloadEquipmentLine = Callable[[int], EventEquipmentLine]
ReloadEventRequest = Callable[[int], EventRequest]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
#: ``saved_event_request``'s period: 15 Oct 2026, 09:00 to 17:00 in Singapore.
STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)

#: Each field of the event's date or time, changed on its own (AC1).
TIMING_CHANGES = [
    {"proposed_date": "2026-10-14"},
    {"end_date": "2026-10-16"},
    {"start_time": "10:00"},
    {"end_time": "18:00"},
]
TIMING_IDS = ["proposed-date", "end-date", "start-time", "end-time"]


def _status_and_provided(line: EventEquipmentLine) -> tuple[EquipmentLineStatus, int | None]:
    return line.status, line.provided_quantity


@pytest.fixture()
def microphones(
    microphone: EquipmentType, reserve_and_review: ReserveAndReview
) -> EventEquipmentLine:
    """Four microphones asked for, reserved and recorded fulfilled."""
    return reserve_and_review(microphone, quantity=4, reserved=4, provided=4)


@pytest.fixture()
def another_events_projectors(
    make_event_request: Callable[..., EventRequest],
    equipment_type: EquipmentType,
    save: Save,
) -> EquipmentReservation:
    """Three projectors held for another event on the same day."""
    other = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=3)
    save(other)
    reservation = EquipmentReservation(
        event_id=other.id,
        equipment_type_id=equipment_type.id,
        quantity=3,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        reserved_by=5,
    )
    save(reservation)
    return reservation


# --------------------------------------------------------------------------
# AC1, AC6 — a date or time change marks every reservation, held where it was
# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload", TIMING_CHANGES, ids=TIMING_IDS)
def test_a_date_or_time_change_marks_every_reservation_still_held_for_its_old_period(
    two_projectors: EventEquipmentLine,
    microphones: EventEquipmentLine,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
    payload: dict[str, Any],
) -> None:
    edit_event(COORDINATOR_ID, payload)

    assert reservation_rows() == [
        (equipment_type.id, 2, STARTS_AT, ENDS_AT, True),
        (microphone.id, 4, STARTS_AT, ENDS_AT, True),
    ]


def test_another_events_reservation_is_not_marked(
    two_projectors: EventEquipmentLine,
    another_events_projectors: EquipmentReservation,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    assert reservation_rows() == [
        (equipment_type.id, 2, STARTS_AT, ENDS_AT, True),
        (equipment_type.id, 3, STARTS_AT, ENDS_AT, False),
    ]


@pytest.mark.parametrize("technical_support_id", [2, 5])
def test_technical_support_are_told_once_of_a_timing_change(
    two_projectors: EventEquipmentLine,
    microphones: EventEquipmentLine,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
    technical_support_id: int,
) -> None:
    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    kinds = [notification[3] for notification in notifications_of(technical_support_id)]
    assert kinds == [NotificationKind.SIGNIFICANT_CHANGE]


@pytest.mark.parametrize("technical_support_id", [2, 5])
def test_technical_support_are_told_of_a_timing_change_to_a_reservation_without_a_line(
    projectors_without_a_line: None,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
    technical_support_id: int,
) -> None:
    """The event has no equipment line, but the change marked its reservation."""
    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    kinds = [notification[3] for notification in notifications_of(technical_support_id)]
    assert kinds == [NotificationKind.SIGNIFICANT_CHANGE]


def test_an_attendance_change_marks_nothing_so_tells_nobody_of_a_reservation_without_a_line(
    projectors_without_a_line: None,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
) -> None:
    """AC7: attendance marks no reservation, so with no line there is nothing to see."""
    edit_event(COORDINATOR_ID, {"expected_attendance": 80})

    assert notifications_of(5) == []


def test_a_fulfilled_line_keeps_its_outcome_while_its_reservation_is_marked(
    two_projectors: EventEquipmentLine,
    edit_event: EditEvent,
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    """Its reservation, not its outcome, is what Technical Support reassess (AC1)."""
    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    line = reload_equipment_line(two_projectors.id)
    assert _status_and_provided(line) == (EquipmentLineStatus.FULFILLED, 2)


def test_marking_is_saved_only_with_the_callers_commit(
    two_projectors: EventEquipmentLine,
    saved_event_request: EventRequest,
    db_session: Session,
    reservation_rows: ReservationRows,
) -> None:
    """SCRUM-57 calls it while approving a change request, in that change's commit."""
    reassess_equipment_after_timing_change(saved_event_request.id)
    db_session.rollback()

    assert [row[4] for row in reservation_rows()] == [False]


# --------------------------------------------------------------------------
# AC7 — a change to none of date, time or quantity marks nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_attendance": 300},
        {"equipment_requirements": "Four wireless microphones"},
        {"description": "A new description."},
        {"proposed_date": "2026-10-15", "start_time": "09:00", "end_time": "17:00"},
    ],
    ids=["attendance", "equipment-requirements", "description", "the-same-date-and-times"],
)
def test_a_change_to_neither_date_nor_time_marks_nothing(
    two_projectors: EventEquipmentLine,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
    payload: dict[str, Any],
) -> None:
    edit_event(COORDINATOR_ID, payload)

    assert [row[4] for row in reservation_rows()] == [False]


# --------------------------------------------------------------------------
# AC8 — a new quantity marks that line's reservation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("quantity", [1, 3], ids=["lower", "higher"])
def test_a_new_quantity_marks_only_that_lines_reservation(
    two_projectors: EventEquipmentLine,
    microphones: EventEquipmentLine,
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    reservation_rows: ReservationRows,
    quantity: int,
) -> None:
    """Held as it was until Technical Support act, even above a lower quantity (AC9)."""
    update_equipment_line(COORDINATOR_ID, REFERENCE, two_projectors.id, {"quantity": quantity})

    assert reservation_rows() == [
        (equipment_type.id, 2, STARTS_AT, ENDS_AT, True),
        (microphone.id, 4, STARTS_AT, ENDS_AT, False),
    ]


@pytest.mark.parametrize(
    "payload",
    [{"notes": "Bring a spare bulb"}, {"quantity": 2}],
    ids=["only-the-notes", "the-same-quantity"],
)
def test_a_line_change_that_asks_for_nothing_new_marks_nothing(
    two_projectors: EventEquipmentLine,
    reservation_rows: ReservationRows,
    payload: dict[str, Any],
) -> None:
    update_equipment_line(COORDINATOR_ID, REFERENCE, two_projectors.id, payload)

    assert [row[4] for row in reservation_rows()] == [False]


# --------------------------------------------------------------------------
# AC12 — a date or time change reopens lines decided for the old period
# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload", TIMING_CHANGES, ids=TIMING_IDS)
@pytest.mark.parametrize("provided", [0, 1], ids=["unavailable", "partially-fulfilled"])
def test_a_date_or_time_change_reopens_a_line_short_of_its_request(
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    reload_equipment_line: ReloadEquipmentLine,
    payload: dict[str, Any],
    provided: int,
) -> None:
    line = reserve_and_review(equipment_type, quantity=2, reserved=0, provided=provided)

    edit_event(COORDINATOR_ID, payload)

    reopened = reload_equipment_line(line.id)
    assert (
        reopened.status,
        reopened.provided_quantity,
        reopened.outcome_note,
        reopened.reviewed_by,
        reopened.reviewed_at,
    ) == (EquipmentLineStatus.REQUESTED, None, None, None, None)


def test_a_reopened_line_keeps_its_reservation_held_for_the_old_period(
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    """Decision 2: the fresh outcome moves, trims or releases it (AC4)."""
    reserve_and_review(equipment_type, quantity=3, reserved=1, provided=1)

    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    assert reservation_rows() == [(equipment_type.id, 1, STARTS_AT, ENDS_AT, True)]


@pytest.mark.parametrize(
    "payload",
    [{"expected_attendance": 300}, {"equipment_requirements": "Four wireless microphones"}],
    ids=["attendance", "equipment-requirements"],
)
def test_a_change_to_neither_date_nor_time_reopens_no_line(
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    reload_equipment_line: ReloadEquipmentLine,
    payload: dict[str, Any],
) -> None:
    line = reserve_and_review(equipment_type, quantity=2, reserved=0, provided=0)

    edit_event(COORDINATOR_ID, payload)

    reopened = reload_equipment_line(line.id)
    assert _status_and_provided(reopened) == (EquipmentLineStatus.UNAVAILABLE, 0)


# --------------------------------------------------------------------------
# SCRUM-33 AC9 — in Safety Review, an unsettled reservation or line sends it back
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reserved", "provided"),
    [(2, 2), (0, 0)],
    ids=["a-marked-reservation", "a-reopened-line"],
)
def test_a_timing_change_in_safety_review_that_unsettles_equipment_goes_back_to_approved(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    save: Save,
    reserved: int,
    provided: int,
) -> None:
    """No venue arrangement or safety approval here sends it back instead."""
    reserve_and_review(equipment_type, quantity=2, reserved=reserved, provided=provided)
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(saved_event_request)

    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.APPROVED


def test_a_timing_change_in_safety_review_that_unsettles_nothing_stays_there(
    saved_users: list[User],
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    reload_event_request: ReloadEventRequest,
    save: Save,
) -> None:
    """A line fulfilled without a reservation has nothing to reassess."""
    reserve_and_review(equipment_type, quantity=2, reserved=0, provided=2)
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(saved_event_request)

    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    status = reload_event_request(saved_event_request.id).status
    assert status is EventRequestStatus.SAFETY_REVIEW
