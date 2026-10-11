"""Unit tests for who is notified when an event request is submitted: nobody.

SCRUM-28 "Receive notifications about my events" AC3 raised a new request to the
Event Coordinators, and SCRUM-30 "Assign a coordinator to a submitted event" AC4
narrowed that to the one it was assigned to, with ``coordinator_assigned``
(ADR-0018); SCRUM-39 added the organiser's ``request_assigned`` (ADR-0030).
SCRUM-95 supersedes both on this path: submitting assigns nobody (AC1, ADR-0036), so
neither notice is raised and the request waits in the Event Coordinator Lead's queue.
These tests are the regression guard that submission stays silent about assignment.
Nothing produces ``event_request_submitted`` any more either.

Where those two notices are raised now is tested where it happens: the Lead's
assignment (SCRUM-95) and a reassignment, in
``test_reassign_coordinator_notifications.py``, which also owns ADR-0015's
lost-notice cases. Submission has no notification write left to lose, so the only
commit it makes is the request's own; that test uses ``mock_session``.

Runs against ``db_session`` with the ``saved_users`` fixture, so the Event
Coordinators really are there to be found and still nobody is told.
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

pytestmark = [
    pytest.mark.scrum_28,
    pytest.mark.scrum_30,
    pytest.mark.scrum_39,
    pytest.mark.scrum_95,
]

SubmitValidRequest = Callable[..., EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
AssignmentNoticesOf = Callable[[int], list[NotificationKind]]


# --------------------------------------------------------------------------
# SCRUM-95 AC1 — no coordinator is assigned, so no assignment notice is raised
# --------------------------------------------------------------------------


def test_neither_coordinator_is_told_a_request_is_theirs(
    saved_users: list[User],
    submit_valid_request: SubmitValidRequest,
    assignment_notices_of: AssignmentNoticesOf,
) -> None:
    """Coordinator 3 would have had it under ADR-0018, and 9 on their next turn."""
    submit_valid_request()

    assert assignment_notices_of(3) == []
    assert assignment_notices_of(9) == []


def test_the_organiser_is_not_told_a_coordinator_was_assigned(
    saved_users: list[User],
    submit_valid_request: SubmitValidRequest,
    assignment_notices_of: AssignmentNoticesOf,
) -> None:
    submit_valid_request()

    assert assignment_notices_of(7) == []


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
    """The message the Lead's assignment and a reassignment both send."""
    assert (
        MESSAGE_BY_KIND[NotificationKind.COORDINATOR_ASSIGNED]
        == "You have been assigned to coordinate this event."
    )


# --------------------------------------------------------------------------
# ADR-0015 — submission has no notification write left to lose
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("organiser_is_found")
def test_submitting_commits_once_and_sends_nothing(
    mock_session: MagicMock,
    valid_event_request_payload: dict[str, Any],
    today: date,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One commit, the request's own: the two notices it used to send are gone.

    ADR-0015's lost-notice cases belong to the paths that still raise those notices;
    ``LOST_NOTIFICATION_CASES`` drives them in
    ``test_reassign_coordinator_notifications.py``.
    """
    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        event_request = submit_event_request(
            7,
            valid_event_request_payload,
            session=mock_session,
            today=today,
            reference_factory=lambda: "EVR-AAAAAAAA",
        )

    assert event_request.reference == "EVR-AAAAAAAA"
    assert mock_session.commit.call_count == 1
    mock_session.rollback.assert_not_called()
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_unassigned reference=EVR-AAAAAAAA"
    ]
