"""SQLAlchemy models owned by the equipment module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.equipment.services`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

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
    #: Units held in total. Reservations (SCRUM-37/45) and out-of-service units
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
