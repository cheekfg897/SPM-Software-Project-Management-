"""Unit tests for SCRUM-31 "Review and decide a submitted request": who is told.

AC10: the organiser who submitted the request is notified of each decision, with an
``event_request_approved`` or ``event_request_rejected`` notification whose
``detail`` carries the reason (ADR-0028; also SCRUM-39 AC3). Nobody else is told, a
refused decision notifies nobody, and a failed notification write doesn't fail the
saved decision (ADR-0015).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, by organiser 7, submitted, assigned to Event Coordinator 3); the
failed-write test uses ``mock_session``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import decide_event_request
from app.modules.notifications.models import Notification
from app.modules.notifications.services import NotificationKind
from tests.events.cases import APPROVAL_REASON, REJECTION_REASON

pytestmark = pytest.mark.scrum_31

Decide = Callable[..., EventRequest]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_ID = 3
ORGANISER_ID = 7


# --------------------------------------------------------------------------
# AC10 — the organiser is told of the decision, with its reason
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "reason", "kind"),
    [
        ("approved", None, NotificationKind.EVENT_REQUEST_APPROVED),
        ("approved", APPROVAL_REASON, NotificationKind.EVENT_REQUEST_APPROVED),
        ("rejected", REJECTION_REASON, NotificationKind.EVENT_REQUEST_REJECTED),
    ],
    ids=["approved", "approved-with-reason", "rejected"],
)
def test_the_organiser_is_told_of_the_decision_with_its_reason(
    decide: Decide,
    detailed_notifications_of: DetailedNotificationsOf,
    outcome: str,
    reason: str | None,
    kind: NotificationKind,
) -> None:
    decide(COORDINATOR_ID, outcome, reason)

    assert detailed_notifications_of(ORGANISER_ID) == [(REFERENCE, kind, reason)]


@pytest.mark.parametrize(
    "user_id",
    [2, 3, 4, 5, 8, 9],
    ids=[
        "technical-support-2",
        "the-deciding-coordinator",
        "venue-staff",
        "technical-support-5",
        "a-colleague-in-the-same-organisation",
        "another-coordinator",
    ],
)
def test_nobody_else_is_told_of_a_decision(
    decide: Decide,
    detailed_notifications_of: DetailedNotificationsOf,
    other_organisers: list[User],
    user_id: int,
) -> None:
    """Only the organiser who submitted it is told, not their whole organisation."""
    decide(COORDINATOR_ID, "rejected", REJECTION_REASON)

    assert detailed_notifications_of(user_id) == []


def test_a_refused_decision_notifies_nobody(decide: Decide, db_session: Session) -> None:
    with pytest.raises(ValidationError):
        decide(COORDINATOR_ID, "rejected")

    assert db_session.scalars(select(Notification)).all() == []


# --------------------------------------------------------------------------
# ADR-0015 — a failed notification write doesn't fail the saved decision
# --------------------------------------------------------------------------


def test_a_failed_notification_write_still_returns_the_decided_request(
    mock_session: MagicMock,
    decidable_by_mock_session: EventRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The decision is committed first; failing its reply would invite a retry."""
    lost_connection = OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))
    mock_session.commit.side_effect = [None, lost_connection]

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        decided = decide_event_request(
            COORDINATOR_ID, REFERENCE, {"outcome": "approved"}, session=mock_session
        )

    assert decided.status is EventRequestStatus.APPROVED
    assert mock_session.commit.call_count == 2
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_notification_failed reference=EVR-AAAAAAAA kind=event_request_approved"
    ]
