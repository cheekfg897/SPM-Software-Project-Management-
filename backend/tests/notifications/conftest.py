"""Fixtures for the notifications module tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users


@pytest.fixture()
def event_summary() -> EventSummary:
    """The event the tests' notifications are about."""
    return EventSummary(id=42, reference="EVR-AAAAAAAA", name="Partner Summit")


@pytest.fixture()
def raised_at() -> datetime:
    """When the tests' notifications are raised: 09:00 Singapore time, 1 Oct 2026."""
    return datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)


@pytest.fixture()
def notify(
    db_session: Session, event_summary: EventSummary, raised_at: datetime
) -> Callable[..., list[Notification]]:
    """Save a "request submitted" notification about ``event_summary`` for each id."""

    def _notify(*recipient_ids: int, now: datetime | None = raised_at) -> list[Notification]:
        return notify_users(
            recipient_ids,
            event_summary,
            NotificationKind.EVENT_REQUEST_SUBMITTED,
            session=db_session,
            now=now,
        )

    return _notify


@pytest.fixture()
def reload_notification(db_session: Session) -> Callable[[int], Notification]:
    """Read a notification back from the database, dropping anything uncommitted."""

    def _reload(notification_id: int) -> Notification:
        db_session.rollback()
        notification = db_session.get(Notification, notification_id)
        assert notification is not None
        return notification

    return _reload
