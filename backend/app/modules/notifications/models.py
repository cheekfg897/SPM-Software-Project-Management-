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
    #: assigned to it, when the Event Coordinator Lead assigns one or on a
    #: reassignment (SCRUM-39 AC1, ADR-0030, ADR-0036). On a reassignment the previous
    #: coordinator gets it too, with a ``detail`` saying the event is no longer theirs
    #: (SCRUM-96 AC5, ADR-0041).
    REQUEST_ASSIGNED = "request_assigned"
    #: Tells Venue Staff a venue booking request was raised for their venue (SCRUM-42
    #: AC9, ADR-0035).
    VENUE_BOOKING_REQUESTED = "venue_booking_requested"
    #: Tells the coordinator who raised a request that Venue Staff approved or
    #: rejected it; the reason, if any, is the notification's ``detail``
    #: (SCRUM-43 AC6, ADR-0042).
    VENUE_BOOKING_APPROVED = "venue_booking_approved"
    VENUE_BOOKING_REJECTED = "venue_booking_rejected"
    #: Told the event's coordinator that equipment was reserved for it (ADR-0037). No
    #: longer raised: the coordinator hears once, of the outcome (SCRUM-46 AC5,
    #: ADR-0102). Kept because notifications already sent hold it, and dropping a
    #: Postgres enum value needs a migration.
    EQUIPMENT_RESERVED = "equipment_reserved"
    #: Tells the Event Coordinator Lead that a submitted request has entered the
    #: unassigned queue (SCRUM-95 AC4, ADR-0036).
    REQUEST_QUEUED_FOR_LEAD = "request_queued_for_lead"
    #: Technical Support recorded the outcome of an equipment review, so the
    #: coordinator knows what will be provided (SCRUM-48 AC3).
    EQUIPMENT_OUTCOME_RECORDED = "equipment_outcome_recorded"
    #: Tells every Safety Officer an event has entered Safety Review (SCRUM-97 AC4,
    #: ADR-0047).
    SAFETY_REVIEW_REQUESTED = "safety_review_requested"
    #: Tells the event's assigned coordinator the Safety Officer's outcome; the reason,
    #: if any, is the notification's ``detail`` (SCRUM-98 AC8).
    SAFETY_CHECK_APPROVED = "safety_check_approved"
    SAFETY_CHECK_REJECTED = "safety_check_rejected"
    SAFETY_CHANGES_REQUESTED = "safety_changes_requested"
    #: Tells the organiser who submitted the request that the coordinator confirmed the
    #: event (SCRUM-49 AC12, ADR-0051).
    EVENT_CONFIRMED = "event_confirmed"
    #: Venue Staff placed a tentative hold on one of the coordinator's venue requests,
    #: or changed its expiry; the expiry is the notification's ``detail`` (SCRUM-75).
    VENUE_HOLD_PLACED = "venue_hold_placed"
    VENUE_HOLD_EXPIRY_CHANGED = "venue_hold_expiry_changed"
    #: The coordinator's hold expires within 24 hours, or has expired; the expiry is the
    #: notification's ``detail`` (SCRUM-94, ADR-0052).
    VENUE_HOLD_EXPIRING = "venue_hold_expiring"
    VENUE_HOLD_EXPIRED = "venue_hold_expired"
    #: Tells the event's assigned coordinator that a venue booked or requested for it
    #: became unavailable; the venue, the reason and the period are the notification's
    #: ``detail`` (SCRUM-92 AC5, ADR-0053).
    ALTERNATIVE_VENUE_NEEDED = "alternative_venue_needed"
    #: Tells every Venue Staff user that a change to a venue's setup or turnaround time
    #: marked a confirmed booking Conflicting, once per booking it newly marks; the
    #: ``detail`` names the venue (SCRUM-50 AC6, ADR-0055).
    VENUE_BOOKING_CONFLICTING = "venue_booking_conflicting"
    #: Tells the event's assigned coordinator that a venue flagged as unavailable for
    #: one of its arrangements is available again, so the arrangement stands; the venue,
    #: the arrangement and its period are the notification's ``detail`` (SCRUM-92 AC8,
    #: ADR-0100).
    VENUE_AVAILABLE_AGAIN = "venue_available_again"
    #: Tells every Venue Staff user that rejecting an event during planning released one
    #: of its approved bookings or holds; the arrangement, the venue and its period are
    #: the notification's ``detail`` (SCRUM-49 AC10, ADR-0103).
    VENUE_BOOKING_RELEASED = "venue_booking_released"
    #: Tells every Safety Officer that a significant change was made to an event in
    #: Safety Review; the fields changed, and whether the event went back to planning,
    #: are the notification's ``detail`` (SCRUM-33 AC9, ADR-0107).
    SAFETY_REVIEW_EVENT_CHANGED = "safety_review_event_changed"
    #: Tells the Organiser who submitted an event that a venue sent back from Confirmed
    #: to Approved that Venue Staff approved a replacement venue for it; the event, the
    #: venues and the category are the notification's ``detail`` (SCRUM-92 AC9,
    #: ADR-0108). Migration 0047. The event's registered Attendees get it too, with a
    #: ``detail`` naming the event and both venues (SCRUM-62 AC6, ADR-0125).
    REPLACEMENT_VENUE_APPROVED = "replacement_venue_approved"
    #: Tells the event's assigned coordinator that Venue Staff reconfirmed one of its
    #: arrangements after a change, or moved an undecided request to the new period; the
    #: arrangement, its venue, its period and any reason are the notification's
    #: ``detail`` (SCRUM-59 AC2, AC4, AC11, ADR-0112). Migration 0049.
    VENUE_BOOKING_RECONFIRMED = "venue_booking_reconfirmed"
    #: Tells an Attendee their own registration is confirmed or withdrawn (SCRUM-62
    #: AC5, ADR-0125). Migration 0050.
    REGISTRATION_CONFIRMED = "registration_confirmed"
    REGISTRATION_WITHDRAWN = "registration_withdrawn"
    #: Tells the Organiser who submitted an event that an Attendee registered or
    #: withdrew; the places left are the notification's ``detail`` (SCRUM-62 AC4,
    #: ADR-0125). Migration 0050.
    ATTENDEE_REGISTERED = "attendee_registered"
    ATTENDEE_WITHDRAWN = "attendee_withdrawn"


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
