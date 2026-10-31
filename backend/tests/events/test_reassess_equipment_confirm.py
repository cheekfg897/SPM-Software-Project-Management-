"""Unit tests for SCRUM-60 AC3: Technical Support confirm a marked reservation.

AC3: given the equipment is free for the new period, confirming moves the reservation
there and the coordinator is told once; confirming is the review, so no outcome is
recorded. Decision 1: it moves to the event's period now, so after two changes the
latest wins. AC10: an event that had passed its safety check needs a new one. AC11:
preparation details are kept. A reservation whose line has no current outcome is
settled by recording the outcome instead, and one the new period can't hold is refused
(AC4, ADR-0114).

The service runs against ``db_session``; every row is read back as saved.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.modules.equipment.models import (
    EquipmentReservation,
    EquipmentType,
    PreparationStatus,
)
from app.modules.equipment.services import (
    EquipmentNotReservableError,
    ReservationCannotMoveError,
    confirm_reservation_move,
    mark_event_reservations_for_reassessment,
)
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import EQUIPMENT_NOT_NEEDED_STATUSES, EventEdit
from app.modules.notifications.services import NotificationKind
from tests.conftest import ReservationRow, ReserveAndReview, approve_safety

pytestmark = pytest.mark.scrum_60

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
HistoryEntry = tuple[EventHistoryKind, int | None, dict[str, Any] | None]
HistoryOf = Callable[[int], list[HistoryEntry]]
SafetyWithdrawalsOf = Callable[[int], list[tuple[int | None, dict[str, Any] | None]]]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]
ReservationRows = Callable[[], list[ReservationRow]]
ReloadEquipmentLine = Callable[[int], EventEquipmentLine]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5

OLD_STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
OLD_ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
#: 20 Oct 2026, 09:00 to 17:00 in Singapore.
NEW_STARTS_AT = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)
NEW_ENDS_AT = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
MOVE_TO_THE_20TH = {"proposed_date": "2026-10-20"}

NOTHING_TO_REASSESS = "This event has no reservation of that equipment type awaiting reassessment."
RECORD_THE_OUTCOME = (
    "This equipment's request has no current outcome. Record its outcome instead: that"
    " settles the reservation."
)
RESERVATIONS_CLOSED = (
    "Equipment can't be reserved for an event that is completed, cancelled or rejected."
)
#: Every status in which a marked reservation may be confirmed, built from the enum so a
#: status added later is covered. A draft is hidden from staff (ADR-0024).
CONFIRMABLE_STATUSES = [
    status
    for status in EventRequestStatus
    if status not in EQUIPMENT_NOT_NEEDED_STATUSES and status is not EventRequestStatus.DRAFT
]


def _outcomes(history: list[HistoryEntry]) -> list[HistoryEntry]:
    """The ``equipment_outcome_recorded`` entries of an event's history."""
    outcomes = []
    for entry in history:
        if entry[0] is EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED:
            outcomes.append(entry)
    return outcomes


def _confirm(equipment_type: EquipmentType) -> list[Any]:
    return confirm_reservation_move(
        REFERENCE, equipment_type.id, confirmed_by=str(TECHNICAL_SUPPORT_ID)
    )


# --------------------------------------------------------------------------
# AC3 — confirming moves the reservation, and the coordinator hears once
# --------------------------------------------------------------------------


def test_confirming_moves_the_reservation_to_the_new_period_and_unmarks_it(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    confirmed = _confirm(equipment_type)

    assert reservation_rows() == [(equipment_type.id, 3, NEW_STARTS_AT, NEW_ENDS_AT, False)]
    assert [(shown.id, shown.quantity, shown.starts_at) for shown in confirmed] == [
        (1, 3, NEW_STARTS_AT)
    ]


def test_after_two_changes_the_reservation_moves_to_the_latest_period(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    """Decision 1: confirming reads the event's period now."""
    edit_event(COORDINATOR_ID, {"proposed_date": "2026-10-18"})
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _confirm(equipment_type)

    assert reservation_rows() == [(equipment_type.id, 3, NEW_STARTS_AT, NEW_ENDS_AT, False)]


def test_confirming_one_type_leaves_another_types_marked_reservation_alone(
    three_projectors: EventEquipmentLine,
    microphone: EquipmentType,
    reserve_and_review: ReserveAndReview,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    """The date change marks both types; only the projectors are confirmed."""
    reserve_and_review(microphone, quantity=4, reserved=4, provided=4)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    confirmed = _confirm(equipment_type)

    assert reservation_rows() == [
        (equipment_type.id, 3, NEW_STARTS_AT, NEW_ENDS_AT, False),
        (microphone.id, 4, OLD_STARTS_AT, OLD_ENDS_AT, True),
    ]
    assert [shown.equipment_type_id for shown in confirmed] == [equipment_type.id]


def test_confirming_records_no_outcome(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    saved_event_request: EventRequest,
    edit_event: EditEvent,
    history_of: HistoryOf,
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    outcomes_before = _outcomes(history_of(saved_event_request.id))

    _confirm(equipment_type)

    assert _outcomes(history_of(saved_event_request.id)) == outcomes_before
    line = reload_equipment_line(three_projectors.id)
    assert (line.status, line.provided_quantity) == (EquipmentLineStatus.FULFILLED, 3)


def test_the_coordinator_is_told_once_that_the_reservation_was_confirmed(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    before = detailed_notifications_of(COORDINATOR_ID)

    _confirm(equipment_type)

    assert detailed_notifications_of(COORDINATOR_ID) == [
        (
            REFERENCE,
            NotificationKind.EQUIPMENT_OUTCOME_RECORDED,
            "Projector: 3 reserved, confirmed for the event's new date and time.",
        ),
        *before,
    ]


@pytest.mark.parametrize("user_id", [2, 5, 4, 7, 9])
def test_nobody_else_is_told(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    detailed_notifications_of: DetailedNotificationsOf,
    user_id: int,
) -> None:
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    before = detailed_notifications_of(user_id)

    _confirm(equipment_type)

    assert detailed_notifications_of(user_id) == before


def test_preparation_details_are_kept_when_the_reservation_moves(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
    db_session: Session,
) -> None:
    db_session.execute(
        update(EquipmentReservation).values(
            preparation_status=PreparationStatus.READY, preparation_notes="Packed in van 2"
        )
    )
    db_session.commit()
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    [confirmed] = _confirm(equipment_type)

    assert (confirmed.preparation_status, confirmed.preparation_notes) == (
        PreparationStatus.READY,
        "Packed in van 2",
    )


@pytest.mark.parametrize("status", CONFIRMABLE_STATUSES, ids=lambda status: status.value)
def test_a_reservation_can_be_confirmed_in_every_status_before_the_event_is_over(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    saved_event_request: EventRequest,
    save: Save,
    reservation_rows: ReservationRows,
    status: EventRequestStatus,
) -> None:
    """SCRUM-57 may mark a Confirmed event's reservations through a change request."""
    mark_event_reservations_for_reassessment(saved_event_request.id)
    saved_event_request.status = status
    save(saved_event_request)

    _confirm(equipment_type)

    assert reservation_rows() == [(equipment_type.id, 3, OLD_STARTS_AT, OLD_ENDS_AT, False)]


# --------------------------------------------------------------------------
# AC10 — the event needs a new safety check
# --------------------------------------------------------------------------


def test_confirming_withdraws_a_safety_approval(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    saved_event_request: EventRequest,
    edit_event: EditEvent,
    safety_withdrawals_of: SafetyWithdrawalsOf,
    save: Save,
) -> None:
    """Approved again after the change, as a change request may leave it (SCRUM-57)."""
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    approve_safety(saved_event_request, save)

    _confirm(equipment_type)

    assert safety_withdrawals_of(saved_event_request.id) == [
        (
            TECHNICAL_SUPPORT_ID,
            {"equipment_type_name": "Projector", "reservation_reassessed": True},
        )
    ]


# --------------------------------------------------------------------------
# Refusals: nothing changes, and nobody is told
# --------------------------------------------------------------------------


def test_confirming_when_exactly_enough_is_free_moves_every_reserved_unit(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    """Three free for three reserved; one fewer is refused, below."""
    hold_on_the_20th(7)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _confirm(equipment_type)

    assert reservation_rows()[0] == (equipment_type.id, 3, NEW_STARTS_AT, NEW_ENDS_AT, False)


def test_one_unit_short_is_refused_changing_nothing_and_telling_nobody(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    """A shortfall is settled by recording an outcome instead (AC4)."""
    hold_on_the_20th(8)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    before = detailed_notifications_of(COORDINATOR_ID)

    with pytest.raises(ReservationCannotMoveError) as exc_info:
        _confirm(equipment_type)

    assert exc_info.value.message == (
        "Projector: only 2 free for the event's period, not the 3 to keep."
        " Record an outcome that provides no more than 2."
    )
    assert reservation_rows()[0] == (equipment_type.id, 3, OLD_STARTS_AT, OLD_ENDS_AT, True)
    assert detailed_notifications_of(COORDINATOR_ID) == before


def test_a_reservation_whose_line_has_no_outcome_is_settled_by_recording_one(
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    """The line was partially fulfilled, so the date change reopened it (AC12)."""
    reserve_and_review(equipment_type, quantity=3, reserved=1, provided=1)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    with pytest.raises(ConflictError) as exc_info:
        _confirm(equipment_type)

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == RECORD_THE_OUTCOME
    assert reservation_rows() == [(equipment_type.id, 1, OLD_STARTS_AT, OLD_ENDS_AT, True)]


@pytest.mark.parametrize(
    ("held_elsewhere", "kept"),
    [(8, [2]), (9, [1]), (10, [])],
    ids=["all-free", "one-short", "none-free"],
)
def test_confirming_a_type_with_no_line_keeps_what_is_free_and_releases_the_rest(
    projectors_without_a_line: None,
    equipment_type: EquipmentType,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
    held_elsewhere: int,
    kept: list[int],
) -> None:
    """With no line there is no outcome to record, so confirming is the review.

    The event's own reservation is saved first; the other event's hold comes last.
    """
    hold_on_the_20th(held_elsewhere)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _confirm(equipment_type)

    expected = []
    for quantity in kept:
        expected.append((equipment_type.id, quantity, NEW_STARTS_AT, NEW_ENDS_AT, False))
    expected.append((equipment_type.id, held_elsewhere, NEW_STARTS_AT, NEW_ENDS_AT, False))
    assert reservation_rows() == expected


def test_a_type_with_nothing_marked_has_nothing_to_confirm(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    hold_on_the_20th: Callable[[int], EventRequest],
) -> None:
    """Another event's marked reservation of the type is not this event's."""
    other = hold_on_the_20th(3)
    mark_event_reservations_for_reassessment(other.id)

    with pytest.raises(NotFoundError) as exc_info:
        _confirm(equipment_type)

    assert exc_info.value.message == NOTHING_TO_REASSESS


@pytest.mark.parametrize(
    "status",
    [EventRequestStatus.COMPLETED, EventRequestStatus.CANCELLED, EventRequestStatus.REJECTED],
    ids=lambda status: status.value,
)
def test_an_event_that_is_over_or_will_not_happen_takes_no_confirmation(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    saved_event_request: EventRequest,
    save: Save,
    status: EventRequestStatus,
) -> None:
    mark_event_reservations_for_reassessment(saved_event_request.id)
    saved_event_request.status = status
    save(saved_event_request)

    with pytest.raises(EquipmentNotReservableError) as exc_info:
        _confirm(equipment_type)

    assert exc_info.value.message == RESERVATIONS_CLOSED


@pytest.mark.parametrize("reference", [REFERENCE, "EVR-ZZZZZZZZ"], ids=["draft", "unknown"])
def test_a_draft_or_unknown_event_is_not_found(
    equipment_type: EquipmentType, saved_event_request: EventRequest, save: Save, reference: str
) -> None:
    saved_event_request.status = EventRequestStatus.DRAFT
    save(saved_event_request)

    with pytest.raises(NotFoundError) as exc_info:
        confirm_reservation_move(reference, equipment_type.id, confirmed_by="5")

    assert exc_info.value.message == "Event request not found."
