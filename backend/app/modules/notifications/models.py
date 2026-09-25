"""SQLAlchemy models owned by the notifications module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.notifications.services`, which also re-exports
:class:`NotificationKind`.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import UTCDateTime
from app.extensions import db

#: "EVR-" plus 8 characters (ADR-0004). Kept here rather than imported from the
#: events module, because a module never imports another module's models.
EVENT_REFERENCE_MAX_LENGTH = 12


class NotificationKind(str, enum.Enum):
    """What happened to the event a notification is about. Later stories add kinds."""

    EVENT_REQUEST_SUBMITTED = "event_request_submitted"


class Notification(db.Model):  # type: ignore[name-defined]
    """One user's in-app notification about an event (SCRUM-28, ADR-0015).

    Each recipient gets their own row, so each has their own read state.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: The user it's for. A database-level foreign key only: the auth module's
    #: ``User`` model is not imported (module boundary).
    recipient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    #: The event request it's about. A database-level foreign key only, like
    #: ``recipient_id``.
    event_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event_requests.id"), nullable=False
    )
    #: The event's reference and name as they were when the notification was
    #: raised, so reading notifications never has to ask the events module (ADR-0015).
    event_reference: Mapped[str] = mapped_column(String(EVENT_REFERENCE_MAX_LENGTH), nullable=False)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(
            NotificationKind,
            name="notification_kind",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    #: Set by the service rather than the database, so every copy of one
    #: notification carries the same instant (ADR-0015).
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: ``None`` until the recipient marks it read (SCRUM-28 AC4).
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Notification id={self.id} recipient_id={self.recipient_id}"
            f" kind={self.kind!r} read_at={self.read_at!r}>"
        )
