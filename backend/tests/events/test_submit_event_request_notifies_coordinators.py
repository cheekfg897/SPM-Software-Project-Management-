"""Unit tests for who is notified when an event request is submitted.

SCRUM-28 "Receive notifications about my events" AC3 raises a new request to Event
Coordinators; SCRUM-30 "Assign a coordinator to a submitted event" AC4 tells the
coordinator it is assigned to. Since SCRUM-30, the assigned coordinator is the only
one it is raised to: they get one ``coordinator_assigned`` notification (ADR-0018,
replacing ADR-0015's notice to every coordinator). Since SCRUM-39 the organiser is
also told, with ``request_assigned`` (``test_organiser_assignment_notifications.py``),
and nobody else is notified.
Nothing produces ``event_request_submitted`` any more. The same notice is how
SCRUM-39 "Be notified about review and approval decisions" AC4 tells the new
coordinator on assignment, so these tests are also its regression guards.

Runs against ``db_session`` with the ``saved_users`` fixture, so the coordinators are
found by a real query; coordinator 3 is the one assigned. With no coordinator at all,
nobody is notified (``test_assign_coordinator.py``). A failed notification write
doesn't fail the saved request or the other notice (ADR-0015); that test uses
``mock_session``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.events.models import EventRequest
from app.modules.events.services import submit_event_request
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import NotificationKind
from tests.events.cases import LOST_NOTIFICATION_CASES

pytestmark = [pytest.mark.scrum_28, pytest.mark.scrum_30, pytest.mark.scrum_39]

SubmitValidRequest = Callable[..., EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

#: What the assignment notification records, in the order ``notifications_of``
#: lists it: event request id, reference, name, kind, read at.
ASSIGNED_NOTIFICATION = (
    1,
    "EVR-AAAAAAAA",
    "ConnectSphere Partner Summit",
    NotificationKind.COORDINATOR_ASSIGNED,
    None,
)


# --------------------------------------------------------------------------
# SCRUM-28 AC3, SCRUM-30 AC4 — of the staff, only the assigned coordinator is told, once
# --------------------------------------------------------------------------


def test_the_assigned_coordinator_gets_one_assignment_notification(
    saved_users: list[User],
    submit_valid_request: SubmitValidRequest,
    notifications_of: NotificationsOf,
) -> None:
    submit_valid_request()

    assert notifications_of(3) == [ASSIGNED_NOTIFICATION]


@pytest.mark.parametrize(
    "user_id",
    [9, 4, 5],
    ids=["the-other-coordinator", "venue-staff", "technical-support"],
)
def test_nobody_else_is_notified_of_a_new_request(
    saved_users: list[User],
    submit_valid_request: SubmitValidRequest,
    notifications_of: NotificationsOf,
    user_id: int,
) -> None:
    submit_valid_request()

    assert notifications_of(user_id) == []


def test_a_rejected_request_notifies_nobody(
    saved_users: list[User],
    valid_event_request_payload: dict[str, Any],
    submit_valid_request: SubmitValidRequest,
    notifications_of: NotificationsOf,
) -> None:
    valid_event_request_payload["proposed_date"] = "2026-09-14"  # yesterday

    with pytest.raises(ValidationError):
        submit_valid_request()

    assert notifications_of(3) == []


def test_the_assignment_notification_says_what_happened() -> None:
    assert (
        MESSAGE_BY_KIND[NotificationKind.COORDINATOR_ASSIGNED]
        == "You have been assigned to coordinate this event."
    )


# --------------------------------------------------------------------------
# ADR-0015 — a failed notification write doesn't fail the saved request
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("organiser_is_found")
@pytest.mark.parametrize(("commits", "lost_kind"), LOST_NOTIFICATION_CASES)
def test_a_failed_notification_write_still_returns_the_saved_request(
    mock_session: MagicMock,
    valid_event_request_payload: dict[str, Any],
    today: date,
    caplog: pytest.LogCaptureFixture,
    commits: list[Exception | None],
    lost_kind: str,
) -> None:
    """The request is committed first; failing its reply would invite a resubmission."""
    mock_session.scalars.return_value = [3]  # one Event Coordinator, who is assigned
    mock_session.commit.side_effect = commits

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        event_request = submit_event_request(
            7,
            valid_event_request_payload,
            session=mock_session,
            today=today,
            reference_factory=lambda: "EVR-AAAAAAAA",
        )

    assert event_request.reference == "EVR-AAAAAAAA"
    assert mock_session.commit.call_count == 3
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference=EVR-AAAAAAAA kind={lost_kind}"
    ]
