"""Business logic for the notifications module.

These functions are the module's public API. Other modules raise notifications
with :func:`notify_users`, passing an :class:`EventSummary` and a
:class:`NotificationKind` (re-exported here so callers never import ``models``).
Routes read a user's own notifications with the other functions.

Every function takes an optional ``session`` so unit tests can pass their own. In
production the default ``db.session`` is used.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.modules.notifications.models import Notification, NotificationKind


@dataclass(frozen=True)
class EventSummary:
    """What a notification records about its event, as the raising module knows it."""

    id: int
    reference: str
    name: str


def notify_users(
    recipient_ids: Iterable[int],
    event: EventSummary,
    kind: NotificationKind,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> list[Notification]:
    """Raise one notification per recipient about ``event`` (SCRUM-28 AC1, AC2).

    The caller decides who the event is relevant to (ADR-0015). With no recipients
    nothing is written and nothing is committed.

    Args:
        recipient_ids: User ids to notify. Passing an id twice notifies it twice.
        event: The event the notifications are about.
        kind: What happened to it.
        session: Database session; defaults to ``db.session``.
        now: When it happened; defaults to the current instant.

    Returns:
        The saved notifications, in the order of ``recipient_ids``.
    """
    recipients = list(recipient_ids)
    if not recipients:
        return []
    if now is None:
        now = datetime.now(timezone.utc)

    notifications: list[Notification] = []
    for recipient_id in recipients:
        notification = Notification(
            recipient_id=recipient_id,
            event_request_id=event.id,
            event_reference=event.reference,
            event_name=event.name,
            kind=kind,
            created_at=now,
        )
        notifications.append(notification)

    sess = resolve_session(session)
    sess.add_all(notifications)
    sess.commit()
    return notifications


def list_notifications_for_recipient(
    recipient_id: int | str, *, session: Session | None = None
) -> list[Notification]:
    """Return the recipient's own notifications, newest first (SCRUM-28 AC2)."""
    stmt = (
        select(Notification)
        .where(Notification.recipient_id == int(recipient_id))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    return list(resolve_session(session).scalars(stmt))
