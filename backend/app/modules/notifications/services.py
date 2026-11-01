"""Business logic for the notifications module.

These functions are the module's public API. Other modules raise notifications
with :func:`notify_users`, passing an :class:`EventSummary` and a
:class:`NotificationKind` (re-exported here so callers never import ``models``).
Routes read a user's own notifications with the other functions.

Every function takes an optional ``session`` so unit tests can pass their own. In
production the default ``db.session`` is used.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.common.errors import NotFoundError
from app.modules.notifications.models import Notification, NotificationKind

logger = logging.getLogger("connectsphere.notifications")


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
    detail: str | None = None,
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
        detail: More about what happened, such as the reason for a decision
            (SCRUM-31 AC10); ``None`` for kinds that carry none.

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
            detail=detail,
        )
        notifications.append(notification)

    sess = resolve_session(session)
    sess.add_all(notifications)
    sess.commit()
    return notifications


def notify_users_after_commit(
    recipient_ids: Iterable[int],
    event: EventSummary,
    kind: NotificationKind,
    *,
    session: Session | None = None,
    detail: str | None = None,
) -> None:
    """Raise :func:`notify_users` notices about a change already committed (ADR-0015).

    If they can't be saved, only they are lost and a warning is logged: what they
    announce is already saved, and failing the reply would invite the caller to do it
    again. The events and venue modules still keep their own copies of this, each
    with its own log line; moving them here is a follow-up (ADR-0125).

    Args:
        recipient_ids: User ids to notify.
        event: The event the notices are about.
        kind: What happened to it.
        session: Database session; defaults to ``db.session``.
        detail: More about what happened; ``None`` for kinds that carry none.
    """
    sess = resolve_session(session)
    try:
        notify_users(recipient_ids, event, kind, session=sess, detail=detail)
    except SQLAlchemyError:
        sess.rollback()
        logger.warning("notification_failed reference=%s kind=%s", event.reference, kind.value)


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


def count_unread_notifications(recipient_id: int | str, *, session: Session | None = None) -> int:
    """Return how many of the recipient's notifications are unread (SCRUM-28 AC5)."""
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_id == int(recipient_id),
            Notification.read_at.is_(None),
        )
    )
    return resolve_session(session).scalars(stmt).one()


def mark_notification_read(
    notification_id: int,
    recipient_id: int | str,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> Notification:
    """Mark one of the recipient's own notifications read (SCRUM-28 AC4).

    Marking it again keeps the first read time and writes nothing (ADR-0015).

    Args:
        notification_id: The notification to mark.
        recipient_id: The caller's user id, taken from their token.
        session: Database session; defaults to ``db.session``.
        now: When it was read; defaults to the current instant.

    Returns:
        The notification, with ``read_at`` set.

    Raises:
        NotFoundError: 404 — no such notification, or it is someone else's. Both get
            the same answer, so the response never confirms another user's id exists
            (ADR-0015).
    """
    sess = resolve_session(session)
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_id == int(recipient_id),
    )
    notification = sess.scalar(stmt)
    if notification is None:
        raise NotFoundError("Notification not found.")
    if notification.read_at is not None:
        return notification

    if now is None:
        now = datetime.now(timezone.utc)
    notification.read_at = now
    sess.commit()
    return notification
