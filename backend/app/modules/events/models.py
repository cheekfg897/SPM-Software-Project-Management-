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
    """The stages an event request passes through (SCRUM-22, ADR-0012).

    ``UNDER_REVIEW`` is the story's "Under Review / Planning". ``APPROVED`` is not one
    of SCRUM-22's seven: SCRUM-31 adds it for a request the coordinator has approved,
    before it is confirmed (ADR-0028). ``SUBMITTED`` and ``DRAFT`` are written so far
    (SCRUM-20), and ``COMPLETED`` by SCRUM-68; each other value arrives with the story
    that performs the transition (SCRUM-31, SCRUM-49, SCRUM-61).
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class EventHistoryKind(str, enum.Enum):
    """What an event history entry records (SCRUM-30, ADR-0018).

    Later stories add kinds: SCRUM-33 edits, SCRUM-68 completions, SCRUM-31 reviews
    and decisions.
    """

    #: The system assigned a coordinator to a new request; ``details`` holds
    #: ``coordinator_id`` and ``actor_id`` is NULL (SCRUM-30).
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


class DecisionOutcome(str, enum.Enum):
    """A coordinator's ruling on a request (SCRUM-31 AC1, ADR-0028).

    Not a database enum: it is stored as the ``outcome`` in a ``decision_recorded``
    history entry's ``details``.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


class EquipmentLineStatus(str, enum.Enum):
    """Where an event's equipment line stands (SCRUM-37 AC4, ADR-0019).

    Only ``REQUESTED`` is written so far; SCRUM-46 adds ``reserved`` with an
    ``ALTER TYPE ... ADD VALUE`` migration.
    """

    REQUESTED = "requested"


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
    #: Notes for internal staff only; never shown to the organiser (SCRUM-33 AC1,
    #: ADR-0025).
    internal_planning_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
