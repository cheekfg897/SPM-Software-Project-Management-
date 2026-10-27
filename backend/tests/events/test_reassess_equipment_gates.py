"""Unit tests for SCRUM-60 AC5 and AC12: what holds back Safety Review and confirmation.

AC5: while a reservation is marked for reassessment, the event cannot enter Safety
Review (SCRUM-97) or be confirmed (SCRUM-49), and the refusal names the reservation.
AC12: a line a date or time change reopened has no current outcome, so it holds both
back too (ADR-0114).

Runs against ``db_session``: the event is Approved, or in Safety Review with the Safety
Officer's approval, with an approved venue arrangement, so equipment is the only gap.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentType
from app.modules.equipment.services import mark_event_reservations_for_reassessment
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import (
    EventConfirmationNotAllowedError,
    EventEdit,
    SafetyReviewNotAllowedError,
    confirm_event_request,
    submit_for_safety_review,
)
from app.modules.venue.models import BookingRequestStatus
from tests.conftest import ReserveAndReview, approve_safety
from tests.events.cases import Arrange

pytestmark = pytest.mark.scrum_60

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
Save = Callable[..., None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3


Gate = tuple[Callable[[int, str], EventRequest], type, EventRequestStatus]

#: Each gate: the status it is asked from, the service, the refusal it raises and the
#: status it moves the event to.
GATES = [
    (
        EventRequestStatus.APPROVED,
        submit_for_safety_review,
        SafetyReviewNotAllowedError,
        EventRequestStatus.SAFETY_REVIEW,
    ),
    (
        EventRequestStatus.SAFETY_REVIEW,
        confirm_event_request,
        EventConfirmationNotAllowedError,
        EventRequestStatus.CONFIRMED,
    ),
]


@pytest.fixture(params=GATES, ids=["safety-review", "confirmation"])
def gate(
    request: pytest.FixtureRequest,
    saved_event_request: EventRequest,
    arrange: Arrange,
    save: Save,
) -> Gate:
    """The event set up to pass the gate but for its equipment, and the gate itself."""
    status_before, service, refusal, status_after = request.param
    saved_event_request.status = status_before
    save(saved_event_request)
    approve_safety(saved_event_request, save)
    arrange(BookingRequestStatus.APPROVED)
    return service, refusal, status_after


def test_a_marked_reservation_holds_the_event_back_naming_it(
    saved_event_request: EventRequest,
    two_projectors: EventEquipmentLine,
    db_session: Session,
    gate: Gate,
) -> None:
    service, refusal, _ = gate
    mark_event_reservations_for_reassessment(saved_event_request.id)
    db_session.commit()

    with pytest.raises(refusal) as exc_info:
        service(COORDINATOR_ID, REFERENCE)

    assert exc_info.value.details == {
        "equipment": [
            "Equipment reservation 1 (Projector) is awaiting reassessment by Technical Support."
        ]
    }


def test_the_same_reservation_unmarked_lets_the_event_through(
    saved_event_request: EventRequest,
    two_projectors: EventEquipmentLine,
    gate: Gate,
) -> None:
    service, _, status_after = gate

    passed = service(COORDINATOR_ID, REFERENCE)

    assert passed.status is status_after


def test_a_line_a_date_change_reopened_holds_the_safety_review_back(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    reserve_and_review: ReserveAndReview,
    edit_event: EditEvent,
    arrange: Arrange,
    save: Save,
) -> None:
    """The edit flags the venue arrangement too; the equipment gap is the line's."""
    saved_event_request.status = EventRequestStatus.APPROVED
    save(saved_event_request)
    arrange(BookingRequestStatus.APPROVED)
    line = reserve_and_review(equipment_type, quantity=2, reserved=0, provided=0)
    edit_event(COORDINATOR_ID, {"start_time": "10:00"})

    with pytest.raises(SafetyReviewNotAllowedError) as exc_info:
        submit_for_safety_review(COORDINATOR_ID, REFERENCE)

    assert exc_info.value.details["equipment"] == [
        f"Equipment request {line.id} has no outcome from Technical Support."
    ]
