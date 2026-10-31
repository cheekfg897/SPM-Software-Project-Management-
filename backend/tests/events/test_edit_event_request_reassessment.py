"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

AC2: after a significant edit that could affect equipment already requested,
Technical Support Staff are warned once per edit, so they can check the equipment
still fits the event (ADR-0025). Nobody is told when the event has no equipment
lines yet, or when none of the changed fields could affect equipment. Venue
arrangements are reassessed in ``tests/venue/test_reassess_arrangements.py`` (AC6).

Runs against ``db_session`` with ``saved_users``, so the recipients are found by a
real query; the failed-notification test uses ``mock_session``, as
``test_event_equipment_notifications.py`` does for the same pattern on SCRUM-37 AC5.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import EventEdit, update_event_request
from app.modules.notifications.services import NotificationKind

#: Each test edits an approved event, the first status a direct edit is allowed in
#: (SCRUM-110).
pytestmark = [pytest.mark.scrum_33, pytest.mark.usefixtures("approved_event_request")]

EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
MakeEventRequest = Callable[..., EventRequest]
MakeEquipmentLine = Callable[..., EventEquipmentLine]
MakeEquipmentType = Callable[..., EquipmentType]
SetStatus = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3


@pytest.fixture()
def event_with_equipment(
    saved_event_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: MakeEquipmentLine,
    save: Callable[..., None],
) -> EventRequest:
    """``saved_event_request`` with one equipment line already on it."""
    save(make_equipment_line(saved_event_request, equipment_type))
    return saved_event_request


@pytest.fixture()
def significant_change_notification(event_with_equipment: EventRequest) -> tuple[Any, ...]:
    """What a notification about a significant change to REFERENCE records."""
    return (
        event_with_equipment.id,
        REFERENCE,
        "Partner Summit",
        NotificationKind.SIGNIFICANT_CHANGE,
        None,
    )


# --------------------------------------------------------------------------
# AC2 — every Technical Support Staff member is warned, once per edit
# --------------------------------------------------------------------------


@pytest.mark.parametrize("technical_support_id", [2, 5])
def test_every_technical_support_staff_member_is_warned_of_a_significant_change(
    saved_users: list[User],
    event_with_equipment: EventRequest,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
    significant_change_notification: tuple[Any, ...],
    technical_support_id: int,
) -> None:
    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert notifications_of(technical_support_id) == [significant_change_notification]


def test_one_edit_raises_only_one_notification_even_with_two_affecting_fields(
    saved_users: list[User],
    event_with_equipment: EventRequest,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
    significant_change_notification: tuple[Any, ...],
) -> None:
    edit_event(COORDINATOR_ID, {"expected_attendance": 300, "equipment_requirements": "4 mics"})

    assert notifications_of(5) == [significant_change_notification]


@pytest.mark.scrum_110
def test_an_amendment_while_the_answer_is_awaited_still_warns_technical_support(
    saved_users: list[User],
    event_with_equipment: EventRequest,
    set_status: SetStatus,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
    significant_change_notification: tuple[Any, ...],
) -> None:
    """ADR-0116 decision 5: they already own a line recorded before approval."""
    set_status(EventRequestStatus.AWAITING_CLARIFICATION)

    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert notifications_of(5) == [significant_change_notification]


@pytest.mark.parametrize(
    "user_id",
    [3, 4, 7, 9],
    ids=["the-coordinator", "venue-staff", "the-organiser", "another-coordinator"],
)
def test_nobody_else_is_told_about_a_significant_change(
    saved_users: list[User],
    event_with_equipment: EventRequest,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
    user_id: int,
) -> None:
    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert notifications_of(user_id) == []


# --------------------------------------------------------------------------
# A change that couldn't affect equipment, or an event with none, tells nobody
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{"description": "New notes"}, {"venue_requirements": "Stage needed"}],
    ids=["not-a-significant-field", "affects-a-venue-but-not-equipment"],
)
def test_a_change_that_cannot_affect_equipment_notifies_nobody(
    saved_users: list[User],
    event_with_equipment: EventRequest,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
    payload: dict[str, Any],
) -> None:
    edit_event(COORDINATOR_ID, payload)

    assert notifications_of(5) == []
    assert notifications_of(2) == []


def test_an_event_with_no_equipment_lines_notifies_nobody(
    saved_users: list[User],
    saved_event_request: EventRequest,
    edit_event: EditEvent,
    notifications_of: NotificationsOf,
) -> None:
    edit_event(COORDINATOR_ID, {"expected_attendance": 300})

    assert notifications_of(5) == []


# --------------------------------------------------------------------------
# ADR-0015 — a failed reassessment notification doesn't fail the saved edit
# --------------------------------------------------------------------------


def test_a_failed_reassessment_notification_still_returns_the_edit(
    mock_session: MagicMock,
    make_event_request: MakeEventRequest,
    make_equipment_type: MakeEquipmentType,
    make_equipment_line: MakeEquipmentLine,
    today: date,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The edit is committed first; failing its reply would invite editing again."""
    event_request = make_event_request(
        coordinator_id=COORDINATOR_ID, status=EventRequestStatus.APPROVED
    )
    event_request.id = 1
    event_request.equipment_lines = [make_equipment_line(event_request, make_equipment_type())]
    # The request, then no safety check in its history (SCRUM-33 AC7).
    mock_session.scalar.side_effect = [event_request, None]
    mock_session.scalars.side_effect = [
        [],  # no venue arrangements to flag (AC6)
        [5],  # one Technical Support Staff member
        [],  # no Venue Staff, who have nothing to hear about anyway
    ]
    lost_connection = OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))
    mock_session.commit.side_effect = [None, lost_connection]

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        edit = update_event_request(
            COORDINATOR_ID,
            REFERENCE,
            {"expected_attendance": 300},
            session=mock_session,
            today=today,
        )

    assert [change.field for change in edit.changes] == ["expected_attendance"]
    assert mock_session.commit.call_count == 2
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_notification_failed reference=EVR-AAAAAAAA kind=significant_change"
    ]
