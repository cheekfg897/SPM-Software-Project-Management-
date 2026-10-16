"""SQLAlchemy models owned by the registration module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.registration.services`.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import UTCDateTime
from app.extensions import db


class RegistrationStatus(str, enum.Enum):
    """Where an Attendee's place stands (ADR-0032).

    Only ``REGISTERED`` places count against the event's capacity. A withdrawal keeps
    the row (SCRUM-53), and registering again sets the same row back.
    """

    REGISTERED = "registered"
    WITHDRAWN = "withdrawn"


#: Name of the unique constraint on (event, attendee). The service relies on it to turn
#: a duplicate that two requests slipped past the check into a 409 (SCRUM-52 AC3).
ONE_PLACE_PER_ATTENDEE_CONSTRAINT = "uq_registrations_event_request_id_attendee_id"


class Registration(db.Model):  # type: ignore[name-defined]
    """One Attendee's place at one event (SCRUM-52, ADR-0032)."""

    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("event_request_id", "attendee_id", name=ONE_PLACE_PER_ATTENDEE_CONSTRAINT),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: The event. A database-level foreign key only: the events module's model is not
    #: imported (module boundary).
    event_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event_requests.id"), index=True, nullable=False
    )
    #: The Attendee. A database-level foreign key only, like ``event_request_id``.
    attendee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(
            RegistrationStatus,
            name="registration_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    #: Set by the service in UTC (ADR-0009), so tests can pin it.
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: When the Attendee withdrew (SCRUM-53); empty while they hold the place.
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
