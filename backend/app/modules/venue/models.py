"""SQLAlchemy models owned by the venue module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.venue.services`.

``Booking`` is a minimal stand-in: no Events module exists yet (Sprint 1 only
built auth), but the calendar (SCRUM-26) and search (SCRUM-35) stories both
need to know what a venue's confirmed/tentative bookings are. Once an Events
module lands with a real "submit an event request" workflow, booking
creation should move there and this table should move with it (or become a
read-mirror) rather than staying owned by venues.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class LayoutType(str, enum.Enum):
    """Room layouts a venue can support (SCRUM-25 AC1)."""

    CLASSROOM = "classroom"
    THEATRE = "theatre"
    BOARDROOM = "boardroom"
    BANQUET = "banquet"
    EXHIBITION = "exhibition"
    OTHER = "other"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class BookingStatus(str, enum.Enum):
    """Lifecycle of a booking against a venue."""

    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Venue(db.Model):  # type: ignore[name-defined]
    """A ConnectSphere venue (SCRUM-25). SCRUM-67 adds the buffer fields."""

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Comma-separated values. Simplest structure that satisfies the ACs —
    #: no query needs to filter *by* an individual facility/feature value at
    #: the database level, only after a venue is already loaded.
    facilities: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    accessibility_features: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    supported_layouts: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    operating_hours_start: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    operating_hours_end: Mapped[str] = mapped_column(String(5), nullable=False, default="18:00")

    #: SCRUM-67 — buffer minutes required before/after an event. ``None``
    #: means "not set explicitly"; services resolve the configured default.
    setup_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turnaround_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: SCRUM-25 AC5/AC6 — deactivate/reactivate. A deactivated venue is
    #: excluded from search but existing bookings keep their FK.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="venue", cascade="all, delete-orphan"
    )
    blocks: Mapped[list["VenueBlock"]] = relationship(
        "VenueBlock", back_populates="venue", cascade="all, delete-orphan"
    )

    def facilities_list(self) -> list[str]:
        return _from_csv(self.facilities)

    def accessibility_list(self) -> list[str]:
        return _from_csv(self.accessibility_features)

    def layouts_list(self) -> list[str]:
        return _from_csv(self.supported_layouts)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Venue id={self.id} name={self.name!r} active={self.is_active}>"


class Booking(db.Model):  # type: ignore[name-defined]
    """A (tentative or confirmed) booking against a venue.

    ``event_id`` is a bare nullable int rather than a foreign key: there is
    no Events module/table to reference yet.
    """

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venues.id"), nullable=False, index=True
    )
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=BookingStatus.TENTATIVE,
    )

    venue: Mapped["Venue"] = relationship("Venue", back_populates="bookings")


class VenueBlock(db.Model):  # type: ignore[name-defined]
    """A maintenance/renovation/safety block shown on the calendar (SCRUM-26)."""

    __tablename__ = "venue_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venues.id"), nullable=False, index=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    venue: Mapped["Venue"] = relationship("Venue", back_populates="blocks")


def _to_csv(items: list[str]) -> str:
    return ",".join(items)


def _from_csv(value: str | None) -> list[str]:
    return [v for v in value.split(",") if v] if value else []


def venue_to_dict(venue: Venue) -> dict[str, Any]:
    """Public representation of a venue (used by ``VenueSchema.get_*`` methods)."""
    return {
        "id": venue.id,
        "name": venue.name,
        "location": venue.location,
        "capacity": venue.capacity,
        "facilities": venue.facilities_list(),
        "accessibility_features": venue.accessibility_list(),
        "supported_layouts": venue.layouts_list(),
        "operating_hours_start": venue.operating_hours_start,
        "operating_hours_end": venue.operating_hours_end,
        "setup_minutes": venue.setup_minutes,
        "turnaround_minutes": venue.turnaround_minutes,
        "is_active": venue.is_active,
    }
