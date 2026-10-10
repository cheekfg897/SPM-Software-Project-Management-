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

    #: SCRUM-28 sent this to every Event Coordinator. Since SCRUM-30 only the assigned
    #: coordinator is told, with ``COORDINATOR_ASSIGNED``, so nothing produces it any
    #: more (ADR-0018). It stays: Postgres enums don't lose values, and older rows
    #: still carry it.
    EVENT_REQUEST_SUBMITTED = "event_request_submitted"
    #: Added by SCRUM-30: the recipient is now the event's coordinator (ADR-0018).
    COORDINATOR_ASSIGNED = "coordinator_assigned"
    EQUIPMENT_REQUESTED = "equipment_requested"
    #: A significant change to an event affects arrangements already made for it
    #: (SCRUM-33, ADR-0025).
    SIGNIFICANT_CHANGE = "significant_change"
    #: The assigned coordinator approved or rejected the organiser's request; the
    #: reason, if any, is the notification's ``detail`` (SCRUM-31 AC10, ADR-0028).
    EVENT_REQUEST_APPROVED = "event_request_approved"
    EVENT_REQUEST_REJECTED = "event_request_rejected"
    #: The assigned coordinator asked the organiser for clarification, and the
    #: question is the notification's ``detail`` (SCRUM-32 AC1, ADR-0029).
    CLARIFICATION_REQUESTED = "clarification_requested"
    #: The organiser answered, and the answer is the notification's ``detail``
    #: (SCRUM-32 AC2, ADR-0029).
    CLARIFICATION_ANSWERED = "clarification_answered"
    #: Tells the organiser who submitted a request that an Event Coordinator has been
    #: assigned to it, on submission or reassignment (SCRUM-39 AC1, ADR-0030).
    REQUEST_ASSIGNED = "request_assigned"
    #: Tells Venue Staff a venue booking request was raised for their venue (SCRUM-42
    #: AC9, ADR-0035).
    VENUE_BOOKING_REQUESTED = "venue_booking_requested"
    #: Tells the event's coordinator that equipment was reserved for it (SCRUM-46 AC5,
    #: ADR-0037).
    EQUIPMENT_RESERVED = "equipment_reserved"
    #: Tells the Event Coordinator Lead that a submitted request has entered the
    #: unassigned queue (SCRUM-95 AC4, ADR-0036).
    REQUEST_QUEUED_FOR_LEAD = "request_queued_for_lead"


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
    #: More about what happened, such as the reason for a decision; ``None`` for
    #: kinds that carry none (SCRUM-31 AC10, ADR-0028).
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Notification id={self.id} recipient_id={self.recipient_id}"
            f" kind={self.kind!r} read_at={self.read_at!r}>"
        )
