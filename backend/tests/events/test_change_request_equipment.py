"""Unit tests for SCRUM-57 "Review and decide a change request": the equipment.

An approved change to the event's date or time hands its equipment back to Technical
Support, as the coordinator's own edit does (SCRUM-60 AC1, ADR-0114, ADR-0127): every
reservation is marked for reassessment in the decision's commit, and Technical Support
Staff (users 2 and 5) are told once it is saved. A change that moves neither, or a
rejected one, marks nothing (SCRUM-60 AC7, SCRUM-57 AC3).

Runs against ``db_session`` with ``saved_event_request`` (``EVR-AAAAAAAA``: organiser
7's, assigned to Event Coordinator 3, on 15 Oct 2026 from 09:00 to 17:00), approved by
``reserve_and_review`` with two projectors reserved and recorded fulfilled.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.modules.equipment import services as equipment_services
from app.modules.equipment.models import EquipmentType
from app.modules.events import services as events_services
from app.modules.events.models import (
    ChangeRequestStatus,
    EquipmentLineStatus,
    EventChangeRequest,
    EventEquipmentLine,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import ChangeRequestAsShown
from app.modules.notifications.services import NotificationKind
from tests.conftest import ReservationRow, ReserveAndReview
from tests.events.cases import lose_connection

pytestmark = pytest.mark.scrum_57

RaiseChange = Callable[[int, Any], ChangeRequestAsShown]
DecideChange = Callable[[int, int, Any], ChangeRequestAsShown]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
ReservationRows = Callable[[], list[ReservationRow]]
ReloadEventRequest = Callable[[int], EventRequest]
ChangeRequestsOf = Callable[[int], list[EventChangeRequest]]
ReloadEquipmentLine = Callable[[int], EventEquipmentLine]
DecideRequested = Callable[[dict[str, Any], dict[str, Any]], None]

ORGANISER_ID = 7
COORDINATOR_ID = 3
TECHNICAL_SUPPORT_IDS = [2, 5]
APPROVE = {"outcome": "approved"}
REJECT = {"outcome": "rejected", "reason": "The hall is taken that morning."}
#: The projectors' period: the event's, 15 Oct 2026, 09:00 to 17:00 in Singapore.
STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)

#: Each field of the event's date or time, asked for on its own (SCRUM-60 AC1).
TIMING_CHANGES = [
    pytest.param({"proposed_date": "2026-10-14"}, id="proposed-date"),
    pytest.param({"end_date": "2026-10-16"}, id="end-date"),
    pytest.param({"start_time": "10:00"}, id="start-time"),
    pytest.param({"end_time": "18:00"}, id="end-time"),
]
MOVE_START = {"start_time": "10:00"}


@pytest.fixture()
def decide_requested(
    two_projectors: EventEquipmentLine, raise_change: RaiseChange, decide_change: DecideChange
) -> DecideRequested:
    """Raise a change request for ``change`` as the organiser, then decide it.

    The event already has its two projectors reserved, so it is approved.
    """

    def _decide_requested(change: dict[str, Any], decision: dict[str, Any]) -> None:
        raised = raise_change(ORGANISER_ID, {**change, "reason": "The keynote moved."})
        decide_change(COORDINATOR_ID, raised.id, decision)

    return _decide_requested


def _kinds(notifications: list[tuple[Any, ...]]) -> list[NotificationKind]:
    """The kind of each notification, from ``notifications_of`` rows."""
    return [notification[3] for notification in notifications]


@pytest.mark.parametrize("change", TIMING_CHANGES)
def test_an_approved_date_or_time_change_marks_the_reservation_held_where_it_was(
    decide_requested: DecideRequested,
    equipment_type: EquipmentType,
    reservation_rows: ReservationRows,
    change: dict[str, Any],
) -> None:
    decide_requested(change, APPROVE)

    assert reservation_rows() == [(equipment_type.id, 2, STARTS_AT, ENDS_AT, True)]


def test_an_approved_timing_change_reopens_a_line_short_of_its_request(
    decide_requested: DecideRequested,
    two_projectors: EventEquipmentLine,
    microphone: EquipmentType,
    reserve_and_review: ReserveAndReview,
    reload_equipment_line: ReloadEquipmentLine,
) -> None:
    """SCRUM-60 AC12: an outcome decided for the old period; a fulfilled one stays."""
    unavailable = reserve_and_review(microphone, quantity=4, reserved=0, provided=0)

    decide_requested(MOVE_START, APPROVE)

    reopened = reload_equipment_line(unavailable.id)
    assert (reopened.status, reopened.provided_quantity) == (
        EquipmentLineStatus.REQUESTED,
        None,
    )
    kept = reload_equipment_line(two_projectors.id)
    assert (kept.status, kept.provided_quantity) == (EquipmentLineStatus.FULFILLED, 2)


@pytest.mark.parametrize(
    ("status", "status_after"),
    [
        pytest.param(EventRequestStatus.APPROVED, EventRequestStatus.APPROVED, id="approved"),
        pytest.param(
            EventRequestStatus.SAFETY_REVIEW, EventRequestStatus.APPROVED, id="safety-review"
        ),
        pytest.param(EventRequestStatus.CONFIRMED, EventRequestStatus.CONFIRMED, id="confirmed"),
    ],
)
def test_an_approved_timing_change_sends_back_only_an_event_in_safety_review(
    decide_requested: DecideRequested,
    set_status: Callable[[EventRequestStatus], None],
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
    status_after: EventRequestStatus,
) -> None:
    """SCRUM-33 AC9, as after an edit (ADR-0107); a Confirmed event stays Confirmed."""
    set_status(status)

    decide_requested(MOVE_START, APPROVE)

    assert reload_event_request(saved_event_request.id).status is status_after


def test_the_equipment_handed_back_is_committed_even_when_every_notice_fails(
    decide_requested: DecideRequested,
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    set_status: Callable[[EventRequestStatus], None],
    equipment_type: EquipmentType,
    microphone: EquipmentType,
    reserve_and_review: ReserveAndReview,
    reservation_rows: ReservationRows,
    reload_equipment_line: ReloadEquipmentLine,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    """The notices commit too, so with them gone only the decision's commit is left."""
    unavailable = reserve_and_review(microphone, quantity=4, reserved=0, provided=0)
    set_status(EventRequestStatus.SAFETY_REVIEW)
    monkeypatch.setattr(events_services, "notify_users", lose_connection)

    decide_requested(MOVE_START, APPROVE)
    db_session.rollback()

    assert reservation_rows() == [(equipment_type.id, 2, STARTS_AT, ENDS_AT, True)]
    assert reload_equipment_line(unavailable.id).status is EquipmentLineStatus.REQUESTED
    event_request = reload_event_request(saved_event_request.id)
    assert event_request.status is EventRequestStatus.APPROVED


def test_the_change_is_not_saved_if_its_equipment_cant_be_handed_back(
    decide_requested: DecideRequested,
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    reload_event_request: ReloadEventRequest,
    change_requests_of: ChangeRequestsOf,
    saved_event_request: EventRequest,
) -> None:
    """The change, its reassessment and the decision share one commit (ADR-0127)."""

    def _marking_fails(*_args: Any, **_kwargs: Any) -> int:
        raise RuntimeError("the reservations could not be marked")

    monkeypatch.setattr(
        equipment_services, "mark_event_reservations_for_reassessment", _marking_fails
    )

    with pytest.raises(RuntimeError):
        decide_requested(MOVE_START, APPROVE)
    db_session.rollback()

    assert reload_event_request(saved_event_request.id).start_time == time(9, 0)
    [change_request] = change_requests_of(saved_event_request.id)
    assert change_request.status is ChangeRequestStatus.PENDING


@pytest.mark.parametrize("technical_support_id", TECHNICAL_SUPPORT_IDS)
def test_technical_support_are_told_once_of_an_approved_timing_change(
    decide_requested: DecideRequested,
    notifications_of: NotificationsOf,
    technical_support_id: int,
) -> None:
    decide_requested(MOVE_START, APPROVE)

    assert _kinds(notifications_of(technical_support_id)) == [NotificationKind.SIGNIFICANT_CHANGE]


def test_an_approved_change_to_neither_date_nor_time_marks_nothing(
    decide_requested: DecideRequested,
    equipment_type: EquipmentType,
    reservation_rows: ReservationRows,
) -> None:
    """SCRUM-60 AC7: attendance and notes don't move the period held for."""
    decide_requested({"expected_attendance": 300, "programme_notes": "Panel added."}, APPROVE)

    assert reservation_rows() == [(equipment_type.id, 2, STARTS_AT, ENDS_AT, False)]


@pytest.mark.parametrize("technical_support_id", TECHNICAL_SUPPORT_IDS)
def test_technical_support_are_told_of_an_approved_attendance_change_as_after_an_edit(
    decide_requested: DecideRequested,
    notifications_of: NotificationsOf,
    technical_support_id: int,
) -> None:
    """A new size could affect the equipment asked for, so they look again."""
    decide_requested({"expected_attendance": 300}, APPROVE)

    assert _kinds(notifications_of(technical_support_id)) == [NotificationKind.SIGNIFICANT_CHANGE]


def test_a_rejected_timing_change_marks_nothing_and_tells_technical_support_nothing(
    decide_requested: DecideRequested,
    equipment_type: EquipmentType,
    reservation_rows: ReservationRows,
    notifications_of: NotificationsOf,
) -> None:
    """AC3: rejecting leaves every arrangement as it was."""
    decide_requested(MOVE_START, REJECT)

    assert reservation_rows() == [(equipment_type.id, 2, STARTS_AT, ENDS_AT, False)]
    assert notifications_of(5) == []
