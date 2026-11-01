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
    """Where a venue booking request stands (SCRUM-42, 43, 93 and 111)."""

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
    #: The request's hold ran out before Venue Staff gave their final approval, so the
    #: venue is free again (SCRUM-94, ADR-0052). Like a rejected request, it stays one
    #: of the event's arrangements until the coordinator withdraws it.
    EXPIRED = "expired"
    #: The arrangement no longer holds its venue: Venue Staff approved a replacement
    #: after the venue became unavailable (SCRUM-92 AC7, ADR-0053), or the coordinator
    #: rejected the event during planning (SCRUM-49 AC10, ADR-0093).
    RELEASED = "released"
    #: The coordinator cancelled the approved booking, with a reason, while the event
    #: was being planned, so the venue is free for that period again (SCRUM-111 AC1,
    #: ADR-0117). Unlike ``RELEASED``, the coordinator chose it.
    CANCELLED = "cancelled"


class UnavailabilityCategory(str, enum.Enum):
    """Why a venue can't be used for a period (SCRUM-92 AC2, ADR-0053).

    Venue Staff choose one when they block or deactivate a venue, and add a note in
    ``reason``, the free text a block has carried since SCRUM-34.
    """

    MAINTENANCE = "maintenance"
    EQUIPMENT_FAILURE = "equipment_failure"
    RENOVATION = "renovation"
    SAFETY_CONCERN = "safety_concern"
    OTHER = "other"

    @property
    def label(self) -> str:
        """How a notification words it, e.g. ``"equipment failure"``."""
        return self.value.replace("_", " ")


class ReassessmentFlagKind(str, enum.Enum):
    """What a significant change to its event left an arrangement needing (ADR-0094).

    SCRUM-33 AC6, in the words of SCRUM-58 AC1 and AC2. Venue Staff settle either one
    (SCRUM-59); until then the event can't go to Safety Review or be confirmed.
    """

    #: The event's details changed under the booking, so Venue Staff must reconfirm it.
    REQUIRES_RECONFIRMATION = "requires_reconfirmation"
    #: The venue no longer meets what the arrangement needs; the reason names it.
    NO_LONGER_SUITABLE = "no_longer_suitable"

    @property
    def label(self) -> str:
        """How a refusal words it, e.g. ``"no longer suitable"``."""
        return self.value.replace("_", " ")


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

#: Statuses of a request that has a hold, live or run out, whose expiry is shown
#: (SCRUM-75 AC9, SCRUM-94 AC6).
REQUEST_STATUSES_WITH_A_HOLD = frozenset(
    {BookingRequestStatus.ON_HOLD, BookingRequestStatus.EXPIRED}
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
#: active venues. SCRUM-49 and SCRUM-97 ignore a cancelled one like a withdrawn one
#: (SCRUM-111, ADR-0117).
RETIRED_REQUEST_STATUSES = frozenset(
    {
        BookingRequestStatus.WITHDRAWN,
        BookingRequestStatus.RELEASED,
        BookingRequestStatus.CANCELLED,
    }
)

#: Arrangements a significant change to the event can flag: a confirmed booking, or a
#: request Venue Staff can still decide (SCRUM-33 AC6, ADR-0094 decision 2). A
#: decided or retired one has nothing left to lose. On Hold waits for its
#: own follow-up (ADR-0094), though a venue becoming unavailable flags it (ADR-0100).
FLAGGABLE_REQUEST_STATUSES = frozenset(
    {
        BookingRequestStatus.PENDING,
        BookingRequestStatus.CONFLICTING,
        BookingRequestStatus.APPROVED,
    }
)

#: Arrangements a venue becoming unavailable can leave needing another venue (SCRUM-92
#: AC1): a confirmed booking, a request Venue Staff can still decide, and a request On
#: Hold, whose tentative hold is a booking too (Product Owner, 19 Oct; ADR-0100).
UNAVAILABILITY_FLAGGABLE_STATUSES = frozenset(
    {
        BookingRequestStatus.PENDING,
        BookingRequestStatus.CONFLICTING,
        BookingRequestStatus.ON_HOLD,
        BookingRequestStatus.APPROVED,
    }
)


def _category_enum() -> Enum:
    """The column type for :class:`UnavailabilityCategory`, shared by two tables."""
    return Enum(
        UnavailabilityCategory,
        name="unavailability_category",
        # Store the enum *values* (snake_case), not the member names.
        values_callable=lambda enum_cls: [m.value for m in enum_cls],
    )


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
    #: When the coordinator was warned that the hold is about to expire (SCRUM-94). Set
    #: once per expiry, so the warning is never sent twice, and cleared when Venue Staff
    #: change the expiry, so the warning follows the new time (ADR-0052).
    hold_warning_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


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
    #: What kind of unavailability it is (SCRUM-92 AC2); ``reason`` is the note.
    category: Mapped[UnavailabilityCategory] = mapped_column(_category_enum(), nullable=False)
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
        # counts, and so does one On Hold (SCRUM-42 AC7, SCRUM-75). The unit suite runs
        # on SQLite, which has partial indexes too, so it enforces it.
        Index(
            "uq_venue_booking_requests_pending",
            "event_id",
            "venue_id",
            "starts_at",
            "ends_at",
            unique=True,
            postgresql_where=text("status IN ('pending', 'conflicting', 'on_hold')"),
            sqlite_where=text("status IN ('pending', 'conflicting', 'on_hold')"),
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
    #: The arrangement this one replaces because its venue became unavailable; approving
    #: this one releases that one (SCRUM-92 AC6, AC7).
    replaces_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("venue_booking_requests.id"), nullable=True
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

    #: Why the arrangement needs an alternative venue, one flag per block or
    #: deactivation that caused it, earliest first (SCRUM-92 AC1).
    flags: Mapped[list[AlternativeVenueFlag]] = relationship(
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="(AlternativeVenueFlag.starts_at, AlternativeVenueFlag.id)",
    )

    #: What significant changes to the event left the arrangement needing, one flag
    #: for each reason each change gave, oldest first (SCRUM-33 AC6, ADR-0094).
    reassessment_flags: Mapped[list[ReassessmentFlag]] = relationship(
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ReassessmentFlag.id",
    )

    @property
    def needs_alternative_venue(self) -> bool:
        """Whether the arrangement is flagged "Needs Alternative Venue" (SCRUM-92 AC1).

        Only while it still holds or asks for its venue, On Hold included (ADR-0100):
        once it is released, withdrawn or decided against, its flags stay as the record
        of why, but nothing is needed.
        """
        if self.status not in UNAVAILABILITY_FLAGGABLE_STATUSES:
            return False
        return len(self.flags) > 0

    @property
    def is_flagged_after_change(self) -> bool:
        """Whether a significant change to the event flagged the arrangement (ADR-0094).

        SCRUM-33 AC6. Only while it is Pending, Conflicting or Approved; unlike
        :attr:`needs_alternative_venue`, not while On Hold, which waits for its own
        follow-up (ADR-0094 decision 2, ADR-0100). Once it is released, withdrawn or
        decided against, its flags stay as the record of why, but nothing is needed.
        """
        if self.status not in FLAGGABLE_REQUEST_STATUSES:
            return False
        return len(self.reassessment_flags) > 0

    @property
    def hold_expires_at(self) -> datetime | None:
        """When the request's hold expires; ``None`` for a request that has no hold.

        An expired hold keeps showing when it expired (SCRUM-75 AC9, SCRUM-94 AC6).
        """
        if self.status not in REQUEST_STATUSES_WITH_A_HOLD:
            return None
        return self.booking.hold_expires_at


class AlternativeVenueFlag(db.Model):  # type: ignore[name-defined]
    """One reason an arrangement needs an alternative venue (SCRUM-92 AC1, ADR-0053).

    A block over the arrangement's period makes one, which removing the block deletes
    (AC8). Deactivating the venue makes one with no block and no end, which
    reactivating it deletes (AC9). The category, note and period are copied from the
    block or the deactivation, so the flag says what the coordinator was told.
    """

    __tablename__ = "alternative_venue_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("venue_booking_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    #: The block that caused it, or ``None`` when the venue was deactivated.
    venue_block_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("venue_blocks.id", ondelete="CASCADE"), index=True, nullable=True
    )
    category: Mapped[UnavailabilityCategory] = mapped_column(_category_enum(), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    #: The period the venue is unavailable; ``ends_at`` is ``None`` for a deactivation,
    #: which lasts until the venue is reactivated.
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReassessmentFlag(db.Model):  # type: ignore[name-defined]
    """One reason a significant change to the event flagged an arrangement (ADR-0094).

    SCRUM-33 AC6. Each arrangement is reassessed on its own, so only the arrangements
    the change affects get one. Kept beside the arrangement's status, as an
    :class:`AlternativeVenueFlag` is, so the booking itself stands untouched until Venue
    Staff reconfirm or withdraw it (SCRUM-59).
    """

    __tablename__ = "reassessment_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("venue_booking_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[ReassessmentFlagKind] = mapped_column(
        Enum(
            ReassessmentFlagKind,
            name="reassessment_flag_kind",
            # Store the enum *values* (snake_case), not the member names.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    #: What changed, or the requirement the venue now fails, as Venue Staff are told.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
