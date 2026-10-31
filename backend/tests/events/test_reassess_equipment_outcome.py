"""Unit tests for SCRUM-60: recording an outcome settles a marked reservation.

AC4: when all or part of the equipment isn't free for the new period, Technical Support
record a SCRUM-48 outcome. Partially fulfilled keeps the free quantity for the new
period and releases the rest; unavailable releases it all. The coordinator gets
SCRUM-48's one notice and no other.
AC9: for a lowered quantity, the outcome trims the reservation to the line's new
quantity, and the rest returns to stock.
AC10: an event that had passed its safety check must pass a new one.
AC11: preparation details already recorded are kept when a reservation moves.
AC12 and decision 2: a reopened line's reservation is moved by its fresh outcome.
Keeping more than is free for the event's period is refused, and nothing is saved
(ADR-0114).

The services run against ``db_session``; every row is read back as saved.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.equipment.models import (
    EquipmentReservation,
    EquipmentType,
    PreparationStatus,
)
from app.modules.equipment.services import (
    ReservationCannotMoveError,
    available_quantity,
    reserve_equipment,
)
from app.modules.events.models import (
    EquipmentLineStatus,
    EventEquipmentLine,
    EventRequest,
)
from app.modules.events.services import (
    EventEdit,
    record_equipment_outcome,
    update_equipment_line,
)
from app.modules.notifications.services import NotificationKind
from tests.conftest import ReservationRow, ReserveAndReview, approve_safety

pytestmark = pytest.mark.scrum_60

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
SafetyWithdrawalsOf = Callable[[int], list[tuple[int | None, dict[str, Any] | None]]]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]
ReservationRows = Callable[[], list[ReservationRow]]
ReloadEquipmentLine = Callable[[int], EventEquipmentLine]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_ID = 5

#: The reservation's own period: 15 Oct 2026, 09:00 to 17:00 in Singapore.
OLD_STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
OLD_ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
#: The event's period once it moves to 20 Oct 2026, same times.
NEW_STARTS_AT = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)
NEW_ENDS_AT = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
MOVE_TO_THE_20TH = {"proposed_date": "2026-10-20"}

#: Why keeping ``{kept}`` reserved projectors is refused when only one is free.
NOT_ENOUGH_FREE = (
    "Projector: only 1 free for the event's period, not the {kept} to keep."
    " Record an outcome that provides no more than 1."
)


def _record(line: EventEquipmentLine, provided: int) -> EventEquipmentLine:
    """Technical Support user 5 records ``provided`` units, with a note."""
    payload = {"provided_quantity": provided, "note": "What is free on the new date"}
    return record_equipment_outcome(TECHNICAL_SUPPORT_ID, REFERENCE, line.id, payload)


def _outcome_notices(notices: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """The coordinator's notices, newest first, as (kind, detail)."""
    return [(kind, detail) for _, kind, detail in notices]


# --------------------------------------------------------------------------
# AC3, AC4 — the outcome moves, trims or releases the marked reservation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("held_elsewhere", "provided", "kept"),
    [(7, 3, [3]), (9, 1, [1]), (10, 0, [])],
    ids=["fulfilled", "partially-fulfilled", "unavailable"],
)
def test_the_outcome_keeps_what_it_provides_for_the_new_period_and_releases_the_rest(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
    held_elsewhere: int,
    provided: int,
    kept: list[int],
) -> None:
    """The event's own reservation is saved first; the other event's hold comes last."""
    hold_on_the_20th(held_elsewhere)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _record(three_projectors, provided)

    expected = []
    for quantity in kept:
        expected.append((equipment_type.id, quantity, NEW_STARTS_AT, NEW_ENDS_AT, False))
    expected.append((equipment_type.id, held_elsewhere, NEW_STARTS_AT, NEW_ENDS_AT, False))
    assert reservation_rows() == expected


def test_the_units_released_are_free_again_for_the_old_period(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    edit_event: EditEvent,
) -> None:
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _record(three_projectors, 1)

    assert available_quantity(equipment_type.id, OLD_STARTS_AT, OLD_ENDS_AT) == 10
    assert available_quantity(equipment_type.id, NEW_STARTS_AT, NEW_ENDS_AT) == 9


def test_the_coordinator_hears_once_of_the_review_with_the_outcome(
    three_projectors: EventEquipmentLine,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    """SCRUM-48's notice and no other: a shortfall is not a notice of its own (AC2)."""
    hold_on_the_20th(9)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    before = len(detailed_notifications_of(COORDINATOR_ID))

    _record(three_projectors, 1)

    notices = _outcome_notices(detailed_notifications_of(COORDINATOR_ID))
    assert len(notices) == before + 1
    assert notices[0] == (
        NotificationKind.EQUIPMENT_OUTCOME_RECORDED,
        "Projector: partially fulfilled, 1 of 3 provided. Note: What is free on the new date",
    )


# --------------------------------------------------------------------------
# Keeping more than is free is refused, and nothing changes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("provided", [2, 3], ids=["one-more-than-is-free", "all-reserved"])
def test_keeping_more_than_is_free_for_the_new_period_is_refused_saying_how_many_are(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
    reload_equipment_line: ReloadEquipmentLine,
    detailed_notifications_of: DetailedNotificationsOf,
    provided: int,
) -> None:
    hold_on_the_20th(9)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    notices_before = detailed_notifications_of(COORDINATOR_ID)

    with pytest.raises(ReservationCannotMoveError) as exc_info:
        _record(three_projectors, provided)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "reservation_cannot_move"
    assert exc_info.value.message == NOT_ENOUGH_FREE.format(kept=provided)
    assert reservation_rows()[0] == (equipment_type.id, 3, OLD_STARTS_AT, OLD_ENDS_AT, True)
    line = reload_equipment_line(three_projectors.id)
    assert (line.status, line.provided_quantity) == (EquipmentLineStatus.FULFILLED, 3)
    assert detailed_notifications_of(COORDINATOR_ID) == notices_before


def test_exactly_what_is_free_can_be_kept(
    three_projectors: EventEquipmentLine,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    """One more is refused, in the test above."""
    hold_on_the_20th(9)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _record(three_projectors, 1)

    assert reload_equipment_line(three_projectors.id).provided_quantity == 1


# --------------------------------------------------------------------------
# AC9 — a lowered quantity's outcome trims the reservation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("new_quantity", "kept"),
    [(3, [2, 1]), (2, [2]), (1, [1])],
    ids=["into-the-second", "the-first-exactly", "into-the-first"],
)
def test_a_lowered_quantitys_outcome_trims_the_oldest_reservation_first(
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    reservation_rows: ReservationRows,
    new_quantity: int,
    kept: list[int],
) -> None:
    line = reserve_and_review(equipment_type, quantity=4, reserved=2, provided=4)
    units = {"equipment_type_id": equipment_type.id, "quantity": 2}
    reserve_equipment(REFERENCE, units, reserved_by=TECHNICAL_SUPPORT_ID)
    update_equipment_line(COORDINATOR_ID, REFERENCE, line.id, {"quantity": new_quantity})

    _record(line, new_quantity)

    expected = []
    for quantity in kept:
        expected.append((equipment_type.id, quantity, OLD_STARTS_AT, OLD_ENDS_AT, False))
    assert reservation_rows() == expected


def test_the_trimmed_units_return_to_stock(
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
) -> None:
    line = reserve_and_review(equipment_type, quantity=5, reserved=5, provided=5)
    update_equipment_line(COORDINATOR_ID, REFERENCE, line.id, {"quantity": 2})
    assert available_quantity(equipment_type.id, OLD_STARTS_AT, OLD_ENDS_AT) == 5

    _record(line, 2)

    assert available_quantity(equipment_type.id, OLD_STARTS_AT, OLD_ENDS_AT) == 8


def test_an_outcome_on_a_line_with_nothing_marked_leaves_its_reservation_alone(
    three_projectors: EventEquipmentLine,
    equipment_type: EquipmentType,
    reservation_rows: ReservationRows,
) -> None:
    """A revision as SCRUM-48 built it: Technical Support trim only what is marked."""
    _record(three_projectors, 1)

    assert reservation_rows() == [(equipment_type.id, 3, OLD_STARTS_AT, OLD_ENDS_AT, False)]


# --------------------------------------------------------------------------
# AC12, decision 2 — a reopened line's fresh outcome moves its reservation
# --------------------------------------------------------------------------


def test_a_reopened_lines_fresh_outcome_moves_the_reservation_it_kept(
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    hold_on_the_20th: Callable[[int], EventRequest],
    edit_event: EditEvent,
    reservation_rows: ReservationRows,
) -> None:
    """It keeps no more than it held: more units would be a new reservation.

    Two are free on the 20th, so keeping the 3 provided, not the 1 held, is refused.
    """
    line = reserve_and_review(equipment_type, quantity=3, reserved=1, provided=1)
    hold_on_the_20th(8)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _record(line, 3)

    assert reservation_rows() == [
        (equipment_type.id, 1, NEW_STARTS_AT, NEW_ENDS_AT, False),
        (equipment_type.id, 8, NEW_STARTS_AT, NEW_ENDS_AT, False),
    ]


# --------------------------------------------------------------------------
# AC11 — preparation details move with the reservation
# --------------------------------------------------------------------------


def test_preparation_details_are_kept_when_the_reservation_moves(
    three_projectors: EventEquipmentLine,
    edit_event: EditEvent,
    db_session: Session,
) -> None:
    db_session.execute(
        update(EquipmentReservation).values(
            preparation_status=PreparationStatus.IN_PROGRESS,
            preparation_notes="Bulbs checked",
        )
    )
    db_session.commit()
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)

    _record(three_projectors, 3)

    db_session.expire_all()
    moved = db_session.scalars(select(EquipmentReservation)).one()
    assert (moved.starts_at, moved.preparation_status, moved.preparation_notes) == (
        NEW_STARTS_AT,
        PreparationStatus.IN_PROGRESS,
        "Bulbs checked",
    )


# --------------------------------------------------------------------------
# AC10 — moving a reservation needs a new safety check
# --------------------------------------------------------------------------


def test_settling_a_reopened_lines_reservation_withdraws_a_safety_approval(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    safety_withdrawals_of: SafetyWithdrawalsOf,
    save: Save,
) -> None:
    """Approved again after the change, as a change request could leave it (SCRUM-57).

    The reopened line has no outcome, so this is its first, not a revision.
    """
    line = reserve_and_review(equipment_type, quantity=3, reserved=1, provided=1)
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    approve_safety(saved_event_request, save)

    _record(line, 3)

    assert safety_withdrawals_of(saved_event_request.id) == [
        (
            TECHNICAL_SUPPORT_ID,
            {"equipment_type_name": "Projector", "reservation_reassessed": True},
        )
    ]


def test_a_revision_that_settles_a_reservation_withdraws_the_approval_once(
    saved_event_request: EventRequest,
    three_projectors: EventEquipmentLine,
    edit_event: EditEvent,
    safety_withdrawals_of: SafetyWithdrawalsOf,
    save: Save,
) -> None:
    edit_event(COORDINATOR_ID, MOVE_TO_THE_20TH)
    approve_safety(saved_event_request, save)

    _record(three_projectors, 3)

    assert safety_withdrawals_of(saved_event_request.id) == [
        (
            TECHNICAL_SUPPORT_ID,
            {
                "equipment_line_id": three_projectors.id,
                "equipment_type_name": "Projector",
                "previous_provided_quantity": 3,
            },
        )
    ]
