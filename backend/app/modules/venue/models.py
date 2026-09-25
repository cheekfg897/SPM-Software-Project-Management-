"""SQLAlchemy models owned by the venue module.

Other modules must **not** import these directly; they go through the
functions in :mod:`app.modules.venue.services`.
"""

from __future__ import annotations

import enum
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import UTCDateTime
from app.extensions import db

#: Separator for the multi-value string columns. Item values must never contain
#: it — ``VenueSchema`` rejects them on the way in.
LIST_SEPARATOR = ","

#: Length of the free-text multi-value columns (facilities, accessibility features).
LIST_COLUMN_LENGTH = 500
#: Longest single item a client may send for those columns.
LIST_ITEM_MAX_LENGTH = 50
#: Most items that always fit the column: n items plus the n - 1 separators.
LIST_MAX_ITEMS = (LIST_COLUMN_LENGTH + len(LIST_SEPARATOR)) // (
    LIST_ITEM_MAX_LENGTH + len(LIST_SEPARATOR)
)


def join_list_field(items: list[str]) -> str:
    """Pack a list of values into one of the multi-value string columns."""
    return LIST_SEPARATOR.join(items)


def split_list_field(value: str | None) -> list[str]:
    """Unpack a multi-value string column into a list (inverse of the above)."""
    return [v for v in value.split(LIST_SEPARATOR) if v] if value else []


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
        """Return every layout's string value."""
        return [member.value for member in cls]


class Weekday(enum.IntEnum):
    """Day of the week, numbered like :meth:`datetime.date.weekday` (Monday = 0).

    Stored as the integer. The API uses the lower-case name (``"monday"``).
    """

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    @property
    def label(self) -> str:
        """The API spelling, e.g. ``"monday"``."""
        return self.name.lower()

    @classmethod
    def labels(cls) -> list[str]:
        """Every day's API spelling, Monday first."""
        return [member.label for member in cls]


class BookingStatus(str, enum.Enum):
    """Lifecycle of a booking against a venue."""

    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class CalendarEntryKind(str, enum.Enum):
    """What makes a period unavailable on a venue's calendar (SCRUM-26)."""

    CONFIRMED_BOOKING = "confirmed_booking"
    TENTATIVE_HOLD = "tentative_hold"
    BLOCK = "block"


class Venue(db.Model):  # type: ignore[name-defined]
    """A ConnectSphere venue (SCRUM-25)."""

    __tablename__ = "venues"
    __table_args__ = (
        CheckConstraint("setup_minutes >= 0", name="ck_venues_setup_minutes_not_negative"),
        CheckConstraint(
            "turnaround_minutes >= 0", name="ck_venues_turnaround_minutes_not_negative"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Multi-value fields, stored as one separator-joined string (see
    #: :func:`join_list_field` / :func:`split_list_field`). Simplest structure
    #: that satisfies the ACs — no query needs to filter *by* an individual
    #: facility/feature value at the database level, only after a venue is
    #: already loaded.
    facilities: Mapped[str] = mapped_column(String(LIST_COLUMN_LENGTH), nullable=False, default="")
    accessibility_features: Mapped[str] = mapped_column(
        String(LIST_COLUMN_LENGTH), nullable=False, default=""
    )
    supported_layouts: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    #: Weekly opening hours (ADR-0008). A day with no period is a closed day.
    #: Replaced as a whole on update, so orphaned periods are deleted.
    opening_periods: Mapped[list[VenueOpeningPeriod]] = relationship(
        back_populates="venue", cascade="all, delete-orphan", lazy="selectin"
    )

    #: SCRUM-67 — minutes a venue needs before and after each event. A booking holds
    #: the venue from ``start - setup`` to ``end + turnaround`` (ADR-0011).
    setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    turnaround_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    #: SCRUM-25 AC5/AC6 — deactivate/reactivate. A deactivated venue is
    #: excluded from listing and search; the row itself is never deleted.
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

    def facilities_list(self) -> list[str]:
        """Return the facilities as a list."""
        return split_list_field(self.facilities)

    def accessibility_list(self) -> list[str]:
        """Return the accessibility features as a list."""
        return split_list_field(self.accessibility_features)

    def layouts_list(self) -> list[str]:
        """Return the supported layouts as a list."""
        return split_list_field(self.supported_layouts)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Venue id={self.id} name={self.name!r} active={self.is_active}>"


class VenueOpeningPeriod(db.Model):  # type: ignore[name-defined]
    """One opening period in a venue's weekly hours (ADR-0008).

    Modelled on Google Places ``opening_hours.periods``: an ``open`` day/time
    and a ``close`` day/time. ``close_day`` is either ``open_day`` or the day
    after it, so a period past midnight (Friday 18:00 → Saturday 02:00) is
    written out explicitly and a period lasts at most 24 hours.
    """

    __tablename__ = "venue_opening_periods"
    __table_args__ = (
        CheckConstraint("open_day BETWEEN 0 AND 6", name="ck_venue_opening_periods_open_day_range"),
        CheckConstraint(
            "close_day BETWEEN 0 AND 6", name="ck_venue_opening_periods_close_day_range"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venues.id", ondelete="CASCADE"), index=True, nullable=False
    )
    open_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    open_time: Mapped[time] = mapped_column(Time, nullable=False)
    close_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    close_time: Mapped[time] = mapped_column(Time, nullable=False)

    venue: Mapped[Venue] = relationship(back_populates="opening_periods")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<VenueOpeningPeriod {Weekday(self.open_day).label} {self.open_time:%H:%M}"
            f" → {Weekday(self.close_day).label} {self.close_time:%H:%M}>"
        )


class Booking(db.Model):  # type: ignore[name-defined]
    """A tentative or confirmed hold on a venue for a period (SCRUM-26).

    ``event_id`` is a bare integer, not a foreign key: the events module only has
    event *requests* so far, not the confirmed events a booking will belong to. Times
    are stored in UTC (ADR-0009).
    """

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_bookings_ends_after_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venues.id"), index=True, nullable=False
    )
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=BookingStatus.TENTATIVE,
    )


class VenueBlock(db.Model):  # type: ignore[name-defined]
    """A period a venue can't be used, such as maintenance (SCRUM-26).

    The calendar shows blocks; creating and removing them is SCRUM-34. Times are
    stored in UTC (ADR-0009).
    """

    __tablename__ = "venue_blocks"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_venue_blocks_ends_after_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venues.id"), index=True, nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
