"""Unit tests for SCRUM-28 "Receive notifications about my events": reading them.

Covers AC2 (a user sees only their own notifications, newest first). Runs against
``db_session``, so the recipient filter and the ordering are real SQL (ADR-0015).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from app.modules.notifications.models import Notification
from app.modules.notifications.services import list_notifications_for_recipient

pytestmark = pytest.mark.scrum_28

Notify = Callable[..., list[Notification]]


def _listed_ids(recipient_id: int) -> list[int]:
    return [notification.id for notification in list_notifications_for_recipient(recipient_id)]


# --------------------------------------------------------------------------
# AC2 — a user's list holds only their notifications, newest first
# --------------------------------------------------------------------------


def test_list_shows_only_the_callers_notifications(notify: Notify) -> None:
    notify(5, 6, 5)

    assert _listed_ids(5) == [3, 1]


def test_list_is_newest_first_with_later_ids_first_on_a_tie(notify: Notify) -> None:
    earlier = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
    later = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)
    notify(5, now=earlier)
    notify(5, now=later)
    notify(5, now=earlier)

    assert _listed_ids(5) == [2, 3, 1]
