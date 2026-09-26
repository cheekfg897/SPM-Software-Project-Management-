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
from app.modules.notifications.schemas import MESSAGE_BY_KIND, NotificationSchema
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users

pytestmark = pytest.mark.scrum_31

ReloadNotification = Callable[[int], Notification]

REASON = "The venue is too small for the expected attendance."


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
        detail=REASON,
    )
    db_session.add(notification)
    db_session.commit()

    reloaded = reload_notification(notification.id)

    assert reloaded.detail == REASON


def test_a_notification_is_raised_with_its_detail(
    db_session: Session,
    event_summary: EventSummary,
    raised_at: datetime,
    reload_notification: ReloadNotification,
) -> None:
    notifications = notify_users(
        [7, 8],
        event_summary,
        NotificationKind.EVENT_REQUEST_REJECTED,
        session=db_session,
        now=raised_at,
        detail=REASON,
    )

    details = [reload_notification(notification.id).detail for notification in notifications]
    assert details == [REASON, REASON]


def test_a_notification_shows_its_detail(event_summary: EventSummary, raised_at: datetime) -> None:
    notification = Notification(
        id=1,
        recipient_id=7,
        event_request_id=event_summary.id,
        event_reference=event_summary.reference,
        event_name=event_summary.name,
        kind=NotificationKind.EVENT_REQUEST_REJECTED,
        created_at=raised_at,
        read_at=None,
        detail=REASON,
    )

    assert NotificationSchema().dump(notification) == {
        "id": 1,
        "kind": "event_request_rejected",
        "message": "Your event request was rejected.",
        "event_reference": "EVR-AAAAAAAA",
        "event_name": "Partner Summit",
        "link": "/events/EVR-AAAAAAAA",
        "created_at": "2026-10-01T09:00:00+08:00",
        "read_at": None,
        "detail": REASON,
    }
