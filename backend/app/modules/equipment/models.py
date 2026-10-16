"""SQLAlchemy models owned by the equipment module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.equipment.services`.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from app.common.database import UTCDateTime
from app.extensions import db

#: Longest equipment type name.
NAME_MAX_LENGTH = 200
#: Longest store name.
STORE_NAME_MAX_LENGTH = 200


class EquipmentType(db.Model):  # type: ignore[name-defined]
    """A kind of equipment ConnectSphere holds, such as projectors (SCRUM-27).

    One record per type, with a unique name, kept at exactly one place: a catalogued
    venue or a named store (ADR-0014).
    """

    __tablename__ = "equipment_types"
    __table_args__ = (
        UniqueConstraint("name", name="uq_equipment_types_name"),
        CheckConstraint(
            "total_quantity >= 0", name="ck_equipment_types_total_quantity_not_negative"
        ),
        CheckConstraint(
            "(venue_id IS NULL) <> (store_name IS NULL)", name="ck_equipment_types_one_location"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    #: Free text; a blank description is stored as ``NULL``.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Units held in total. Reservations (SCRUM-46) and out-of-service units
    #: (SCRUM-47) are subtracted when availability is calculated, never written here.
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Where the equipment is kept: a venue *or* a store, never both (ADR-0014). The
    #: venue is a plain foreign key; the venue module owns that table.
    venue_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("venues.id"), index=True, nullable=True
    )
    store_name: Mapped[str | None] = mapped_column(String(STORE_NAME_MAX_LENGTH), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OutOfServiceReason(str, enum.Enum):
    """Why units of an equipment type cannot be used (SCRUM-45 AC2, ADR-0037)."""

    DAMAGED = "damaged"
    UNDER_MAINTENANCE = "under_maintenance"


class EquipmentReservation(db.Model):  # type: ignore[name-defined]
    """Units of one equipment type held for one event's exact period (SCRUM-46).

    Several rows may exist for the same event and type; they add up. The period is
    copied from the event when the units are reserved, so availability is calculated
    for those exact times and never the whole day (SCRUM-45 AC4). ``event_id`` and
    ``reserved_by`` are plain foreign keys to tables other modules own, with no ORM
    relationship across the module boundary.
    """

    __tablename__ = "equipment_reservations"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_equipment_reservations_quantity_min"),
        # Availability looks up the reservations of one type that overlap a period.
        Index("ix_equipment_reservations_type_period", "equipment_type_id", "starts_at", "ends_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event_requests.id"), index=True, nullable=False
    )
    equipment_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("equipment_types.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    reserved_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    #: Set while units going out of service leave the type short of what is reserved
    #: for the period (SCRUM-47 AC3, ADR-0046). Nothing is released: it only asks for
    #: someone to look.
    needs_attention: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=expression.false()
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

    #: Same module, so an ORM relationship is allowed: it gives the API the type's name.
    equipment_type: Mapped[EquipmentType] = relationship()


class EquipmentOutOfService(db.Model):  # type: ignore[name-defined]
    """Units of one equipment type recorded as damaged or under maintenance (ADR-0037).

    Availability subtracts the units of every row whose ``resolved_at`` is ``NULL``
    (SCRUM-45 AC2). Technical Support write the rows and resolve them (SCRUM-47,
    ADR-0046): ``recorded_by`` and ``recorded_at`` say who took the units out and when,
    ``resolved_by`` and ``resolved_at`` who put them back and when (AC4).
    """

    __tablename__ = "equipment_out_of_service"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_equipment_out_of_service_quantity_min"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("equipment_types.id"), index=True, nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[OutOfServiceReason] = mapped_column(
        Enum(
            OutOfServiceReason,
            name="out_of_service_reason",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    recorded_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: ``NULL`` while the units are still out of service; set when they are back.
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    #: Who put the units back; ``NULL`` while they are still out of service.
    resolved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
