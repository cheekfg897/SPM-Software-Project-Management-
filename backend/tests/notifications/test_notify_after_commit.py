"""Unit tests for raising notices about a change already committed (SCRUM-62, ADR-0125).

The registration module tells people about a place taken or given back after the
registration's own commit, as the events and venue modules do (ADR-0015). If the notices
can't be saved, only they are lost: the reply still succeeds, and a warning is logged.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification
from app.modules.notifications.services import (
    EventSummary,
    NotificationKind,
    notify_users_after_commit,
)

pytestmark = pytest.mark.scrum_62

KIND = NotificationKind.EVENT_CONFIRMED


def test_each_recipient_is_told_with_the_detail(
    db_session: Session, event_summary: EventSummary
) -> None:
    notify_users_after_commit([3, 5], event_summary, KIND, session=db_session, detail="Note.")

    db_session.rollback()
    saved = db_session.scalars(select(Notification).order_by(Notification.id))
    rows = [(row.recipient_id, row.event_request_id, row.kind, row.detail) for row in saved]
    assert rows == [(3, 42, KIND, "Note."), (5, 42, KIND, "Note.")]


def test_a_failed_write_is_rolled_back_and_logged_not_raised(
    mock_session: MagicMock, event_summary: EventSummary, caplog: pytest.LogCaptureFixture
) -> None:
    """What the notices announce is saved; failing the reply would invite a retry."""
    mock_session.commit.side_effect = OperationalError("INSERT ...", {}, Exception("gone"))

    with caplog.at_level(logging.WARNING, logger="connectsphere.notifications"):
        notify_users_after_commit([3], event_summary, KIND, session=mock_session)

    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        "notification_failed reference=EVR-AAAAAAAA kind=event_confirmed"
    ]
