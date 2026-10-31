"""Unit tests for SCRUM-37 "Record what equipment an event needs": the notifications.

Covers AC6: Technical Support Staff are notified when equipment is requested. Every
Technical Support Staff member gets one notification per added line, and nobody else
does (ADR-0019). Changing what a line asks for, or removing it, is a significant
change they hear about too (AC4, ``test_equipment_line_reopens_review.py``); changing
only its notes tells nobody. Runs against
``db_session`` with ``saved_users``, so the recipients are found by a real query. A
failed notification write doesn't fail the saved line (ADR-0015); that test uses
``mock_session``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    add_equipment_line,
    update_equipment_line,
)
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)

#: Each test starts on an approved event, the first status its equipment lines change
#: in (SCRUM-110); a test that needs another status sets it.
pytestmark = [pytest.mark.scrum_37, pytest.mark.usefixtures("approved_event_request")]

NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
REFERENCE = "EVR-AAAAAAAA"


@pytest.fixture()
def requested_notification(saved_event_request: EventRequest) -> tuple[Any, ...]:
    """What a notification about equipment requested for REFERENCE records.

    In the order ``notifications_of`` lists it: event request id, reference, name,
    kind, read at.
    """
    return (
        saved_event_request.id,
        REFERENCE,
        "Partner Summit",
        NotificationKind.EQUIPMENT_REQUESTED,
        None,
    )


# --------------------------------------------------------------------------
# AC6 — every Technical Support Staff member hears about requested equipment
# --------------------------------------------------------------------------


@pytest.mark.parametrize("technical_support_id", [2, 5])
def test_every_technical_support_staff_member_is_notified_when_equipment_is_requested(
    saved_users: list[User],
    valid_equipment_line_payload: dict[str, Any],
    notifications_of: NotificationsOf,
    requested_notification: tuple[Any, ...],
    technical_support_id: int,
) -> None:
    add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    assert notifications_of(technical_support_id) == [requested_notification]


@pytest.mark.parametrize(
    "user_id", [3, 4, 7], ids=["event-coordinator", "venue-staff", "the-organiser"]
)
def test_nobody_else_is_notified_when_equipment_is_requested(
    saved_users: list[User],
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    notifications_of: NotificationsOf,
    user_id: int,
) -> None:
    add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    assert notifications_of(user_id) == []


def test_each_added_line_raises_its_own_notification(
    saved_users: list[User],
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    microphone: EquipmentType,
    notifications_of: NotificationsOf,
) -> None:
    add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)
    add_equipment_line(
        COORDINATOR_ID, REFERENCE, {"equipment_type_id": microphone.id, "quantity": 4}
    )

    kinds = [notification[3] for notification in notifications_of(5)]
    assert kinds == [NotificationKind.EQUIPMENT_REQUESTED, NotificationKind.EQUIPMENT_REQUESTED]


def test_a_rejected_line_notifies_nobody(
    saved_users: list[User],
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    notifications_of: NotificationsOf,
) -> None:
    valid_equipment_line_payload["quantity"] = 0

    with pytest.raises(ValidationError):
        add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    assert notifications_of(5) == []


def test_editing_only_a_lines_notes_notifies_nobody(
    saved_users: list[User],
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    notifications_of: NotificationsOf,
    requested_notification: tuple[Any, ...],
) -> None:
    line = add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    update_equipment_line(COORDINATOR_ID, REFERENCE, line.id, {"notes": "Bring a spare"})

    assert notifications_of(5) == [requested_notification]


def test_the_notification_says_equipment_was_requested_and_links_to_the_event(
    saved_users: list[User],
    saved_event_request: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
) -> None:
    add_equipment_line(COORDINATOR_ID, REFERENCE, valid_equipment_line_payload)

    shown = NotificationSchema().dump(list_notifications_for_recipient(5)[0])

    assert shown["kind"] == "equipment_requested"
    assert shown["message"] == "Equipment was requested for an event."
    assert shown["link"] == "/events/EVR-AAAAAAAA"
    assert shown["event_name"] == "Partner Summit"


# --------------------------------------------------------------------------
# ADR-0015 — a failed notification write doesn't fail the saved line
# --------------------------------------------------------------------------


def test_a_failed_notification_write_still_returns_the_saved_line(
    mock_session: MagicMock,
    make_event_request: Callable[..., EventRequest],
    make_equipment_type: Callable[..., EquipmentType],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The line is committed first; failing its reply would invite adding it again."""
    event_request = make_event_request(
        coordinator_id=COORDINATOR_ID, status=EventRequestStatus.APPROVED
    )
    event_request.id = 1
    # The request, then no safety check in its history (SCRUM-37 AC4).
    mock_session.scalar.side_effect = [event_request, None]
    mock_session.get.return_value = make_equipment_type()
    mock_session.scalars.return_value = [5]  # one Technical Support Staff member
    lost_connection = OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))
    mock_session.commit.side_effect = [None, lost_connection]
    payload = {"equipment_type_id": 1, "quantity": 2}

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        line = add_equipment_line(COORDINATOR_ID, REFERENCE, payload, session=mock_session)

    assert (line.event_request_id, line.quantity) == (1, 2)
    assert mock_session.commit.call_count == 2
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_notification_failed reference=EVR-AAAAAAAA kind=equipment_requested"
    ]
