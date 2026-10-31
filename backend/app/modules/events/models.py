"""SQLAlchemy models owned by the events module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.events.services`.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import UTCDateTime
from app.extensions import db

NAME_MAX_LENGTH = 200

#: "EVR-" plus 8 characters (ADR-0004).
REFERENCE_MAX_LENGTH = 12

#: Name of the unique constraint on ``reference``. The service looks for it to
#: tell a reference collision apart from other integrity errors (ADR-0004).
REFERENCE_UNIQUE_CONSTRAINT = "uq_event_requests_reference"


class EventRequestStatus(str, enum.Enum):
    """The ten stages an event request passes through (SCRUM-22, ADR-0048).

    There is no Planning status: planning work happens while the request is
    ``APPROVED``, and a request that "returns to planning" returns to ``APPROVED``.
    ``APPROVED`` means the coordinator has approved the request to go on to planning
    (SCRUM-31, ADR-0028), not the customer's "event approved", which is ``CONFIRMED``.
    ``AWAITING_CLARIFICATION`` is the coordinator waiting for the organiser's answer
    (SCRUM-32, ADR-0029). ``SAFETY_REVIEW`` sits between ``APPROVED`` and ``CONFIRMED``,
    for an event whose venues and equipment are settled and which awaits the Safety
    Officer (SCRUM-97, ADR-0047).
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    APPROVED = "approved"
    SAFETY_REVIEW = "safety_review"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class EventHistoryKind(str, enum.Enum):
    """What an event history entry records (SCRUM-30, ADR-0018).

    Later stories add kinds: SCRUM-33 edits, SCRUM-68 completions, SCRUM-31 reviews
    and decisions, SCRUM-32 clarification requests and answers.
    """

    #: A coordinator was first assigned to a request; ``details`` holds
    #: ``coordinator_id``. ``actor_id`` is the Event Coordinator Lead who assigned it
    #: (SCRUM-95); entries SCRUM-30 wrote before the Lead existed have a NULL actor,
    #: because the system chose then.
    COORDINATOR_ASSIGNED = "coordinator_assigned"
    #: A user moved the request to another coordinator; ``details`` holds
    #: ``previous_coordinator_id``, ``previous_coordinator_name``, ``coordinator_id``
    #: and ``coordinator_name``, the names as they were then, and ``actor_id`` is who
    #: did it (SCRUM-87, ADR-0021).
    COORDINATOR_REASSIGNED = "coordinator_reassigned"
    #: The assigned coordinator changed one field; ``details`` holds ``field``,
    #: ``previous_value``, ``new_value`` (JSON-safe forms: dates and times as
    #: ISO strings) and ``significant``, and ``actor_id`` is who made the edit
    #: (SCRUM-33, ADR-0025).
    FIELD_CHANGED = "field_changed"
    #: The assigned coordinator marked the event completed after it ended;
    #: ``actor_id`` is who did it and ``details`` is NULL (SCRUM-68, ADR-0027).
    EVENT_COMPLETED = "event_completed"
    #: The assigned coordinator moved a submitted request to under review;
    #: ``details`` is ``None`` and ``actor_id`` is the coordinator (SCRUM-31 AC3,
    #: ADR-0028).
    REVIEW_STARTED = "review_started"
    #: The assigned coordinator approved or rejected the request; ``details`` holds
    #: ``outcome`` and ``reason`` (``None`` when none was given), and ``actor_id`` is
    #: the coordinator. The latest one is the current decision (SCRUM-31 AC8,
    #: ADR-0028).
    DECISION_RECORDED = "decision_recorded"
    #: The assigned coordinator asked the organiser for clarification; ``details``
    #: holds ``message``, and ``actor_id`` is the coordinator (SCRUM-32 AC1, AC4,
    #: ADR-0029).
    CLARIFICATION_REQUESTED = "clarification_requested"
    #: An organiser answered the clarification request and resubmitted; ``details``
    #: holds ``response``, and ``actor_id`` is the organiser (SCRUM-32 AC2, AC4,
    #: ADR-0029).
    CLARIFICATION_ANSWERED = "clarification_answered"
    #: The assigned coordinator raised a venue booking request; ``details`` holds
    #: ``venue_booking_request_id``, ``venue_id``, ``starts_at`` and ``ends_at`` (ISO
    #: strings), and ``actor_id`` is the coordinator (SCRUM-42, ADR-0035).
    VENUE_BOOKING_REQUESTED = "venue_booking_requested"
    #: Venue Staff approved a venue booking request for the event (SCRUM-43 AC3).
    VENUE_BOOKING_APPROVED = "venue_booking_approved"
    #: Venue Staff rejected a venue booking request for the event (SCRUM-43 AC3).
    VENUE_BOOKING_REJECTED = "venue_booking_rejected"
    #: Technical Support reserved units of an equipment type for the event; ``details``
    #: holds ``equipment_type_id``, ``equipment_type_name``, ``quantity`` and
    #: ``reservation_id``, and ``actor_id`` is who reserved them (SCRUM-46, ADR-0037).
    EQUIPMENT_RESERVED = "equipment_reserved"
    #: The assigned coordinator changed one of the event's venue arrangements;
    #: ``details`` holds ``venue_booking_request_id``, ``venue_id`` and each changed
    #: field with its ``previous`` and ``new`` value (SCRUM-93 AC6).
    VENUE_ARRANGEMENT_CHANGED = "venue_arrangement_changed"
    #: The assigned coordinator withdrew one of the event's venue arrangements before
    #: Venue Staff decided it; ``details`` holds ``venue_booking_request_id`` and
    #: ``venue_id`` (SCRUM-93 AC6).
    VENUE_ARRANGEMENT_WITHDRAWN = "venue_arrangement_withdrawn"
    #: Technical Support recorded or revised the outcome of an equipment review;
    #: ``details`` holds ``equipment_line_id``, ``equipment_type_id``,
    #: ``equipment_type_name``, ``quantity``, ``provided_quantity``, ``status`` and
    #: ``note`` (``None`` when the request was met in full), and ``actor_id`` is the
    #: reviewer (SCRUM-48 AC4, AC5).
    EQUIPMENT_OUTCOME_RECORDED = "equipment_outcome_recorded"
    #: The assigned coordinator sent the approved event to the Safety Officer once its
    #: venues and equipment were settled; ``details`` is ``None`` and ``actor_id`` is
    #: the coordinator (SCRUM-97 AC1, ADR-0047).
    SAFETY_REVIEW_REQUESTED = "safety_review_requested"
    #: The Safety Officer recorded the safety check's outcome; ``details`` holds the
    #: ``outcome``, the ``checklist`` of notes and the ``reason`` (``None`` on an
    #: approval without one), and ``actor_id`` is the Safety Officer (SCRUM-98 AC7).
    SAFETY_OUTCOME_RECORDED = "safety_outcome_recorded"
    #: The assigned coordinator confirmed the event; ``details`` is ``None`` and
    #: ``actor_id`` is the coordinator (SCRUM-49 AC1, ADR-0051).
    EVENT_CONFIRMED = "event_confirmed"
    #: Venue Staff recorded the preparation of an approved venue booking; ``details``
    #: holds ``venue_booking_request_id``, ``venue_id``, ``status`` and ``notes``
    #: (``None`` when none were given), and ``actor_id`` is the Venue Staff user
    #: (SCRUM-84 AC4, ADR-0049).
    VENUE_PREPARATION_UPDATED = "venue_preparation_updated"
    #: Technical Support recorded the preparation of a reservation; ``details`` holds
    #: ``reservation_id``, ``equipment_type_id``, ``equipment_type_name``, ``status``
    #: and ``notes`` (``None`` when none were given), and ``actor_id`` is the Technical
    #: Support user (SCRUM-85 AC4, ADR-0050).
    EQUIPMENT_PREPARATION_UPDATED = "equipment_preparation_updated"
    #: A tentative hold on one of the event's venues ran out before Venue Staff's final
    #: approval; ``details`` holds ``venue_booking_request_id``, ``venue_id``,
    #: ``booking_id`` and ``expires_at`` (an ISO string), and ``actor_id`` is NULL,
    #: because the system expired it (SCRUM-94 AC6, ADR-0052).
    VENUE_HOLD_EXPIRED = "venue_hold_expired"
    #: A block or deactivation left one of the event's venue arrangements needing an
    #: alternative venue. ``details`` holds the arrangement, the venue, the category,
    #: reason and period of the unavailability, and whether a Confirmed event went back
    #: to Approved; ``actor_id`` is ``None`` (SCRUM-92 AC1, AC3, ADR-0053).
    ALTERNATIVE_VENUE_NEEDED = "alternative_venue_needed"
    #: A replacement venue was approved after the event passed its safety check, so the
    #: approval no longer counts; ``details`` names the replacement arrangement and
    #: ``actor_id`` is the Venue Staff user who approved it (SCRUM-92 AC10, ADR-0053).
    SAFETY_APPROVAL_WITHDRAWN = "safety_approval_withdrawn"


class SafetyOutcome(str, enum.Enum):
    """The Safety Officer's ruling on an event in Safety Review (SCRUM-98 AC1).

    Not a database enum: it is stored as the ``outcome`` in a
    ``safety_outcome_recorded`` history entry's ``details``.
    """

    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class DecisionOutcome(str, enum.Enum):
    """A coordinator's ruling on a request (SCRUM-31 AC1, ADR-0028).

    Not a database enum: it is stored as the ``outcome`` in a ``decision_recorded``
    history entry's ``details``.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


class EquipmentLineStatus(str, enum.Enum):
    """Where an event's equipment line stands (SCRUM-37 AC4, ADR-0019, SCRUM-48).

    ``REQUESTED`` until Technical Support records the outcome of their review, which
    is then one of the three outcome values. The outcome follows from how much was
    provided: :func:`app.modules.events.services.outcome_status_for` is the only
    place that decides, so the status and ``provided_quantity`` cannot disagree.
    """

    REQUESTED = "requested"
    #: Everything the coordinator asked for will be provided (SCRUM-48 AC2).
    FULFILLED = "fulfilled"
    #: Some but not all of it; the shortfall is ``quantity - provided_quantity``
    #: and a note says why (SCRUM-48 AC1).
    PARTIALLY_FULFILLED = "partially_fulfilled"
    #: None of it is available; the note carries the required reason (SCRUM-48 AC3).
    UNAVAILABLE = "unavailable"


class EventRequest(db.Model):  # type: ignore[name-defined]
    """An Event Organiser's request for ConnectSphere to plan an event (SCRUM-19)."""

    __tablename__ = "event_requests"
    __table_args__ = (
        UniqueConstraint("reference", name=REFERENCE_UNIQUE_CONSTRAINT),
        CheckConstraint(
            "expected_attendance >= 1", name="ck_event_requests_expected_attendance_min"
        ),
        # NULL passes a CHECK, so this stays alongside the rule below: a draft's NULL
        # attendance is untouched, and a non-draft's must both exist and be >= 1.
        CheckConstraint(
            "status = 'draft' OR ("
            "proposed_date IS NOT NULL AND end_date IS NOT NULL AND "
            "start_time IS NOT NULL AND end_time IS NOT NULL AND "
            "expected_attendance IS NOT NULL"
            ")",
            name="ck_event_requests_details_unless_draft",
        ),
        # NULL passes a CHECK, so a capacity that was never set is untouched.
        CheckConstraint(
            "registration_capacity >= 1", name="ck_event_requests_registration_capacity_min"
        ),
        CheckConstraint(
            "NOT registration_enabled OR registration_capacity IS NOT NULL",
            name="ck_event_requests_enabled_registration_has_capacity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Identifier shown to users. The integer ``id`` stays internal.
    reference: Mapped[str] = mapped_column(String(REFERENCE_MAX_LENGTH), nullable=False)
    #: The organiser who submitted it. A database-level foreign key only: the
    #: auth module's ``User`` model is not imported (module boundary).
    organiser_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    #: The organiser's client organisation when they submitted (SCRUM-66 AC4,
    #: ADR-0013). Rows from before migration 0007 are NULL. A database-level foreign
    #: key only, like ``organiser_id``.
    organisation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("client_organisations.id"), index=True, nullable=True
    )
    #: The Event Coordinator assigned when the request was submitted (SCRUM-30 AC1,
    #: ADR-0018), or since reassigned to (SCRUM-87, ADR-0021). One column, so a request
    #: never has more than one (AC2); NULL when no coordinator existed. A database-level
    #: foreign key only, like ``organiser_id``.
    coordinator_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Indexed because Technical Support's list of equipment awaiting action keeps only
    #: events from today on, soonest first (SCRUM-38, ADR-0022).
    #: NULL only on a draft (SCRUM-20, ADR-0024).
    proposed_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    #: Same as ``proposed_date`` unless the event runs past midnight (ADR-0002).
    #: NULL only on a draft (SCRUM-20, ADR-0024).
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: NULL only on a draft (SCRUM-20, ADR-0024).
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    #: NULL only on a draft (SCRUM-20, ADR-0024).
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    #: NULL only on a draft (SCRUM-20, ADR-0024).
    expected_attendance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessibility_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: What the event needs from planning, editable by the assigned coordinator and
    #: shown to the organiser (SCRUM-33 AC1, ADR-0025).
    programme_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The planning notes, editable by the assigned coordinator and shown to staff and
    #: the organiser (SCRUM-33 AC1, ADR-0104); the name is from when they were internal.
    internal_planning_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    #: Whether Attendees may register, set by the assigned coordinator (SCRUM-69 AC1,
    #: ADR-0043). ``registration_required`` is only what the organiser asked for.
    registration_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    #: How many places there are; NULL until the coordinator sets it, and always set
    #: while registration is enabled (SCRUM-69 AC2, ADR-0043).
    registration_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: When Attendees can no longer withdraw, decided by the organiser and recorded by
    #: the assigned coordinator; NULL when none is set, so withdrawals close when the
    #: event starts (SCRUM-69 AC6, SCRUM-53 AC2, ADR-0086).
    withdrawal_cut_off: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[EventRequestStatus] = mapped_column(
        Enum(
            EventRequestStatus,
            name="event_request_status",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=EventRequestStatus.SUBMITTED,
    )
    #: The equipment recorded for the event (SCRUM-37), in the order it was added.
    #: Loaded on access, so the organiser's list query never touches that table.
    equipment_lines: Mapped[list[EventEquipmentLine]] = relationship(
        order_by="EventEquipmentLine.id"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EventRequest id={self.id} reference={self.reference!r} status={self.status!r}>"


class EventHistoryEntry(db.Model):  # type: ignore[name-defined]
    """Something that happened to an event request, and who did it (SCRUM-30, ADR-0018).

    One table for every story that changes an event: assignment (SCRUM-30),
    reassignment (SCRUM-87), decisions (SCRUM-31) and edits (SCRUM-33) each add a
    kind and put what they need to say in ``details``.
    """

    __tablename__ = "event_history_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event_requests.id"), index=True, nullable=False
    )
    #: Same-module relationship, so an entry can be attached to a request that hasn't
    #: been flushed yet and land in the same commit as the change it records.
    event_request: Mapped[EventRequest] = relationship()
    kind: Mapped[EventHistoryKind] = mapped_column(
        Enum(
            EventHistoryKind,
            name="event_history_entry_kind",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    #: The user who did it; NULL when the system did, as for automatic assignment.
    #: A database-level foreign key only.
    actor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    #: What the kind needs to say, e.g. ``{"coordinator_id": 3}``.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Set by the service in UTC (ADR-0009), so tests can pin it.
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<EventHistoryEntry id={self.id} event_request_id={self.event_request_id}"
            f" kind={self.kind!r}>"
        )


class EventEquipmentLine(db.Model):  # type: ignore[name-defined]
    """One kind of equipment an event needs, and how many (SCRUM-37, ADR-0019).

    One line per equipment type per event: to change the number, edit the line.
    """

    __tablename__ = "event_equipment_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_event_equipment_lines_quantity_min"),
        CheckConstraint(
            "provided_quantity IS NULL OR provided_quantity BETWEEN 0 AND quantity",
            name="ck_event_equipment_lines_provided_within_quantity",
        ),
        UniqueConstraint(
            "event_request_id",
            "equipment_type_id",
            name="uq_event_equipment_lines_event_request_id_equipment_type_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event_requests.id"), index=True, nullable=False
    )
    #: The catalogue entry (SCRUM-27). A database-level foreign key only: the
    #: equipment module's model is not imported (module boundary).
    equipment_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("equipment_types.id"), index=True, nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Technical notes; a blank note is stored as ``NULL``.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EquipmentLineStatus] = mapped_column(
        Enum(
            EquipmentLineStatus,
            name="event_equipment_line_status",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=EquipmentLineStatus.REQUESTED,
    )
    #: How many units Technical Support will actually provide (SCRUM-48). ``None``
    #: means no outcome has been recorded yet, which is what SCRUM-97 and SCRUM-49
    #: gate the Safety Review on; the shortfall is ``quantity`` minus this.
    provided_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Why the request could not be met in full. Required when less than the whole
    #: quantity is provided (SCRUM-48 AC1, AC3).
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The Technical Support user who recorded the outcome, shown by name on the
    #: event record (SCRUM-48 AC4).
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
