"""Unit tests for SCRUM-28 "Receive notifications about my events": reading them.

Covers AC2 (a user sees only their own notifications, newest first), AC4 (marking one
read, which is kept) and AC5 (how many are unread). Someone else's notification is
"not found", the same as a missing one (ADR-0015). Runs against ``db_session``, so the
recipient filter, the ordering and the count are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from app.common.errors import NotFoundError
from app.modules.notifications.models import Notification
from app.modules.notifications.services import (
    count_unread_notifications,
    list_notifications_for_recipient,
    mark_notification_read,
)

pytestmark = pytest.mark.scrum_28

Notify = Callable[..., list[Notification]]
ReloadNotification = Callable[[int], Notification]

FIRST_READ_AT = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)


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


# --------------------------------------------------------------------------
# AC4 — marking a notification read saves when, and keeps the first time
# --------------------------------------------------------------------------


def test_marking_read_saves_when_it_was_read(
    notify: Notify, reload_notification: ReloadNotification
) -> None:
    [notification] = notify(5)

    marked = mark_notification_read(notification.id, "5", now=FIRST_READ_AT)

    assert marked.id == notification.id
    assert reload_notification(notification.id).read_at == FIRST_READ_AT


def test_marking_read_again_keeps_the_first_read_time(
    notify: Notify, reload_notification: ReloadNotification
) -> None:
    [notification] = notify(5)
    mark_notification_read(notification.id, 5, now=FIRST_READ_AT)

    mark_notification_read(notification.id, 5, now=datetime(2026, 10, 2, 3, 0, tzinfo=timezone.utc))

    assert reload_notification(notification.id).read_at == FIRST_READ_AT


def test_read_at_defaults_to_the_current_instant(
    notify: Notify, reload_notification: ReloadNotification
) -> None:
    [notification] = notify(5)
    before = datetime.now(timezone.utc)

    mark_notification_read(notification.id, 5)

    after = datetime.now(timezone.utc)
    read_at = reload_notification(notification.id).read_at
    assert read_at is not None
    assert before <= read_at <= after


@pytest.mark.parametrize("notification_id", [1, 99], ids=["another-users", "unknown"])
def test_a_notification_that_is_not_the_callers_is_not_found(
    notify: Notify, reload_notification: ReloadNotification, notification_id: int
) -> None:
    """Another user's notification gets the same answer as a missing one (ADR-0015)."""
    [someone_elses] = notify(6)

    with pytest.raises(NotFoundError) as exc_info:
        mark_notification_read(notification_id, 5)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Notification not found."
    assert reload_notification(someone_elses.id).read_at is None


# --------------------------------------------------------------------------
# AC5 — how many of the caller's notifications are unread
# --------------------------------------------------------------------------


def test_unread_count_counts_only_the_callers_unread_notifications(notify: Notify) -> None:
    [first_for_7, _, _] = notify(7, 7, 8)
    mark_notification_read(first_for_7.id, 7, now=FIRST_READ_AT)

    counts = (
        count_unread_notifications(7),
        count_unread_notifications("8"),
        count_unread_notifications(9),
    )

    assert counts == (1, 1, 0)
