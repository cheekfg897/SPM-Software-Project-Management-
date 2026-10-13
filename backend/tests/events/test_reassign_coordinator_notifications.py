"""Unit tests for SCRUM-87 "Reassign an event to a different coordinator": who is told.

AC4: the newly assigned coordinator is notified, with the same
``coordinator_assigned`` notification a coordinator gets on submission (ADR-0021).
Since SCRUM-39 the organiser is also told, with ``request_assigned``
(``test_organiser_assignment_notifications.py``). Nobody else is: the previous
coordinator made the change themselves. A refused reassignment notifies nobody, and
a failed notification write doesn't fail the saved reassignment or the other notice
(ADR-0015). The same notice
is how SCRUM-39 AC4 tells the new coordinator on reassignment, so these tests are
also its regression guards.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3); the failed-write test uses
``mock_session``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.events.models import EventRequest
from app.modules.events.services import CoordinatorContact, reassign_coordinator
from app.modules.notifications.models import Notification
from app.modules.notifications.services import (
    NotificationKind,
)
from tests.events.cases import LEAD_ID, LOST_NOTIFICATION_CASES

pytestmark = [pytest.mark.scrum_87, pytest.mark.scrum_39]

Reassign = Callable[[str], tuple[EventRequest, CoordinatorContact]]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

REFERENCE = "EVR-AAAAAAAA"
NINE = "coordinator9@example.com"


# --------------------------------------------------------------------------
# AC4, ADR-0021 — the new coordinator is told, and no one else on the staff
# --------------------------------------------------------------------------


def test_the_new_coordinator_is_told_the_event_is_theirs(
    reassign: Reassign, notifications_of: NotificationsOf, saved_event_request: EventRequest
) -> None:
    reassign(NINE)

    assert notifications_of(9) == [
        (
            saved_event_request.id,
            REFERENCE,
            "Partner Summit",
            NotificationKind.COORDINATOR_ASSIGNED,
            None,
        )
    ]


@pytest.mark.parametrize(
    "user_id",
    [2, 3, 4, 5],
    ids=[
        "technical-support-2",
        "previous-coordinator",
        "venue-staff",
        "technical-support-5",
    ],
)
def test_nobody_else_is_notified_of_a_reassignment(
    reassign: Reassign, notifications_of: NotificationsOf, user_id: int
) -> None:
    reassign(NINE)

    assert notifications_of(user_id) == []


def test_a_refused_reassignment_notifies_nobody(reassign: Reassign, db_session: Session) -> None:
    with pytest.raises(ConflictError):
        reassign("coordinator3@example.com")

    assert db_session.scalars(select(Notification)).all() == []


# --------------------------------------------------------------------------
# ADR-0015 — a failed notification write doesn't fail the saved reassignment
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("commits", "lost_kind"), LOST_NOTIFICATION_CASES)
def test_a_failed_notification_write_still_returns_the_reassigned_event(
    mock_session: MagicMock,
    reassignment_lookups: EventRequest,
    caplog: pytest.LogCaptureFixture,
    commits: list[Exception | None],
    lost_kind: str,
) -> None:
    """The reassignment is committed first; failing its reply would invite a retry."""
    mock_session.commit.side_effect = commits

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        event_request, _ = reassign_coordinator(
            LEAD_ID, REFERENCE, {"coordinator_email": NINE}, session=mock_session
        )

    assert event_request.coordinator_id == 9
    assert mock_session.commit.call_count == 3
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference=EVR-AAAAAAAA kind={lost_kind}"
    ]
