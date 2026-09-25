"""SQLAlchemy models owned by the events module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.events.services`.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

NAME_MAX_LENGTH = 200

#: "EVR-" plus 8 characters (ADR-0004).
REFERENCE_MAX_LENGTH = 12

#: Name of the unique constraint on ``reference``. The service looks for it to
#: tell a reference collision apart from other integrity errors (ADR-0004).
REFERENCE_UNIQUE_CONSTRAINT = "uq_event_requests_reference"


class EventRequestStatus(str, enum.Enum):
    """The stages an event request passes through (SCRUM-22, ADR-0012).

    ``UNDER_REVIEW`` is the story's "Under Review / Planning". Only ``SUBMITTED`` is
    written so far; each other value arrives with the story that performs the
    transition (SCRUM-20, SCRUM-31, SCRUM-49, SCRUM-61, SCRUM-68).
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class EventRequest(db.Model):  # type: ignore[name-defined]
    """An Event Organiser's request for ConnectSphere to plan an event (SCRUM-19)."""

    __tablename__ = "event_requests"
    __table_args__ = (
        UniqueConstraint("reference", name=REFERENCE_UNIQUE_CONSTRAINT),
        CheckConstraint(
            "expected_attendance >= 1", name="ck_event_requests_expected_attendance_min"
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
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Same as ``proposed_date`` unless the event runs past midnight (ADR-0002).
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    expected_attendance: Mapped[int] = mapped_column(Integer, nullable=False)
    venue_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessibility_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
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
