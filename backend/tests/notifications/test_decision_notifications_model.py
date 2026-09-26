"""Unit tests for SCRUM-31 "Review and decide a submitted request": notification kinds.

AC10: the organiser is told when their request is approved or rejected. Each outcome
has its own kind and message, and a notification can carry a detail, such as the
reason for a rejection, which also meets SCRUM-39's AC3 (ADR-0028). Raising them is in
``tests/events/test_decision_notifications.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.notifications.services import EventSummary, NotificationKind

pytestmark = pytest.mark.scrum_31

ReloadNotification = Callable[[int], Notification]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("event_request_approved", "Your event request was approved."),
        ("event_request_rejected", "Your event request was rejected."),
    ],
    ids=["approved", "rejected"],
)
def test_the_decision_notifications_say_the_outcome(value: str, message: str) -> None:
    kind = NotificationKind(value)

    assert MESSAGE_BY_KIND[kind] == message


def test_a_notification_can_hold_a_detail(
    db_session: Session,
    event_summary: EventSummary,
    raised_at: datetime,
    reload_notification: ReloadNotification,
) -> None:
    notification = Notification(
        recipient_id=7,
        event_request_id=event_summary.id,
        event_reference=event_summary.reference,
        event_name=event_summary.name,
        kind=NotificationKind.EVENT_REQUEST_SUBMITTED,
        created_at=raised_at,
        detail="The venue is too small for the expected attendance.",
    )
    db_session.add(notification)
    db_session.commit()

    reloaded = reload_notification(notification.id)

    assert reloaded.detail == "The venue is too small for the expected attendance."
