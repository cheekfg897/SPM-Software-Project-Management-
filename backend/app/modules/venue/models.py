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
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    func,
    text,
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

#: Longest reason a block may carry (SCRUM-34, ADR-0016). The column is ``Text``, so
#: this is an API rule rather than a column length: a reason is a short note.
BLOCK_REASON_MAX_LENGTH = 500


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
    #: A confirmed booking that a change to the venue's setup or turnaround time made
    #: overlap another booking or a block (SCRUM-44). It still holds the venue.
    CONFLICTING = "conflicting"
    CANCELLED = "cancelled"


#: Booking statuses that hold the venue for their period. A Conflicting booking still
#: does: marking it records a problem, it doesn't release the venue (SCRUM-44).
HOLDING_BOOKING_STATUSES = frozenset({BookingStatus.CONFIRMED, BookingStatus.CONFLICTING})


class CalendarEntryKind(str, enum.Enum):
    """What makes a period unavailable on a venue's calendar (SCRUM-26)."""

    CONFIRMED_BOOKING = "confirmed_booking"
    TENTATIVE_HOLD = "tentative_hold"
    BLOCK = "block"


class RequirementKind(str, enum.Enum):
    """What an event asks of a venue, as the suitability check names it (SCRUM-36)."""

    CAPACITY = "capacity"
    FACILITIES = "facilities"
    ACCESSIBILITY = "accessibility"
    LAYOUT = "layout"


class BookingRequestStatus(str, enum.Enum):
    """Where a venue booking request stands (SCRUM-42, SCRUM-93, SCRUM-43).

    Nothing cancels a request yet: SCRUM-93 withdraws one and SCRUM-43 decides one, so a
    ``CANCELLED`` value waits for the story that needs it. SCRUM-94 adds ``EXPIRED``.
    """

    PENDING = "pending"
    #: Venue Staff approved the venue and are holding it tentatively until the
    #: coordinator finalises the event's arrangements (SCRUM-75, ADR-0045).
    ON_HOLD = "on_hold"
    #: The coordinator retracted the arrangement before Venue Staff decided it
    #: (SCRUM-93 AC6). The row stays so SCRUM-75 can ignore it when counting venues.
    WITHDRAWN = "withdrawn"
    #: Venue Staff approved the request, so the venue is booked (SCRUM-43 AC3).
    APPROVED = "approved"
    #: Venue Staff refused the request, with a reason (SCRUM-43 AC3, AC6).
    REJECTED = "rejected"
    #: A Pending request that clashes with one Venue Staff approved (SCRUM-44). They can
    #: still reject it, and nothing clears the status on its own (ADR-0045).
    CONFLICTING = "conflicting"


class BookingDecision(str, enum.Enum):
    """What Venue Staff decided about a request (SCRUM-43 AC3).

    The events module has its own ``DecisionOutcome`` for event requests, with the same
    two values. A module never imports another module's models, so this one is its
    own; unifying them would mean moving the enum into ``app.common``, which is a
    refactor across both modules rather than part of this story (ADR-0042).
    """

    APPROVED = "approved"
    REJECTED = "rejected"


#: Statuses Venue Staff can still decide (SCRUM-43, SCRUM-44, SCRUM-75). A Conflicting
#: request is one of them, or nothing could ever settle it, and so is a request On Hold:
#: the final approval turns its hold into the booking, a rejection releases the venue.
DECIDABLE_REQUEST_STATUSES = frozenset(
    {
        BookingRequestStatus.PENDING,
        BookingRequestStatus.CONFLICTING,
        BookingRequestStatus.ON_HOLD,
    }
)

#: Statuses Venue Staff can place a hold on (SCRUM-75): a request not yet approved.
HOLDABLE_REQUEST_STATUSES = frozenset(
    {BookingRequestStatus.PENDING, BookingRequestStatus.CONFLICTING}
)


class PreparationStatus(str, enum.Enum):
    """How far Venue Staff have got in setting up a booking (SCRUM-84, ADR-0049).

    The equipment module has its own, with the same values: a module never imports
    another module's models.
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY = "ready"


#: Statuses that take an arrangement out of an event's venue count (SCRUM-93).
#: ``REJECTED`` stays out, because SCRUM-49 and SCRUM-97 gate on every active
#: arrangement being approved, so a rejected one must keep them waiting. ``ON_HOLD``
#: stays out too, because SCRUM-75 treats a held arrangement as one of the event's
#: active venues.
RETIRED_REQUEST_STATUSES = frozenset({BookingRequestStatus.WITHDRAWN})


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
    #: When a tentative hold stops holding the venue (SCRUM-75). Venue Staff choose it.
    #: ``None`` on a confirmed booking, and on a tentative booking made before holds had
    #: an expiry, which is treated as not expiring.
    hold_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class VenueBlock(db.Model):  # type: ignore[name-defined]
    """A period a venue can't be used, such as maintenance.

    The calendar shows blocks (SCRUM-26); Venue Staff create and remove them
    (SCRUM-34, ADR-0016). Times are stored in UTC (ADR-0009).
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


class VenueBookingRequest(db.Model):  # type: ignore[name-defined]
    """A coordinator's request for Venue Staff to hold a venue for an approved event.

    ``event_id`` and ``requested_by`` are database-level foreign keys only: the venue
    module never imports the events or auth models. Times are stored in UTC (ADR-0009).
    """

    __tablename__ = "venue_booking_requests"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_venue_booking_requests_ends_after_start"),
        CheckConstraint("expected_occupancy >= 1", name="ck_venue_booking_requests_occupancy_min"),
        # AC6: one Pending request per event, venue and period. A partial index, so
        # requests that are no longer Pending (SCRUM-43) don't block a new one. A
        # Conflicting request is a Pending one that clashes (SCRUM-44), so it still
        # counts. The unit suite runs on SQLite, which has partial indexes too, so it
        # enforces it.
        Index(
            "uq_venue_booking_requests_pending",
            "event_id",
            "venue_id",
            "starts_at",
            "ends_at",
            unique=True,
            postgresql_where=text("status IN ('pending', 'conflicting')"),
            sqlite_where=text("status IN ('pending', 'conflicting')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event_requests.id"), index=True, nullable=False
    )
    venue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venues.id"), index=True, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    expected_occupancy: Mapped[int] = mapped_column(Integer, nullable=False)
    #: A layout value, or ``None`` when the event has no layout to carry over.
    required_layout: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Why the request goes ahead although the venue is unsuitable for it (AC7).
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Why Venue Staff decided as they did; required to reject (SCRUM-43 AC6). Who
    #: decided and when are in the event's history entry, as for raising a request.
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BookingRequestStatus] = mapped_column(
        Enum(
            BookingRequestStatus,
            name="booking_request_status",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=BookingRequestStatus.PENDING,
    )
    #: How far Venue Staff have got in preparing the venue, and their notes (SCRUM-84).
    #: Who recorded each update and when are in the event's history entries, as for a
    #: decision.
    preparation_status: Mapped[PreparationStatus] = mapped_column(
        Enum(
            PreparationStatus,
            name="venue_preparation_status",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=PreparationStatus.NOT_STARTED,
    )
    preparation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The tentative booking that holds the venue while the request is On Hold, and the
    #: confirmed booking it becomes (SCRUM-75). ``None`` until a hold is placed.
    booking_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bookings.id"), nullable=True
    )
    booking: Mapped[Booking | None] = relationship()
    requested_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
