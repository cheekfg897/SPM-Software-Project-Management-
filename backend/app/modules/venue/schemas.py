"""Request and response schemas for the venue module (marshmallow).

Same shape as the other modules: input schemas describe the payload and raise
marshmallow errors, which :func:`app.common.validation.load_or_raise` turns into
the project's 400 ``ValidationError`` with per-field details. Output schemas are
``dump_only`` and define exactly what the API returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)

from app.common.clock import as_utc, local_today, to_business_time
from app.common.fields import BusinessDateTime
from app.common.validation import TimeRangeSchema, not_blank
from app.modules.venue.models import (
    BLOCK_REASON_MAX_LENGTH,
    LIST_ITEM_MAX_LENGTH,
    LIST_MAX_ITEMS,
    LIST_SEPARATOR,
    BookingRequestStatus,
    CalendarEntryKind,
    LayoutType,
    RequirementKind,
    Venue,
    VenueBookingRequest,
    Weekday,
)
from app.modules.venue.opening_hours import Period, find_overlap, period_error


def _validate_list_item(value: str) -> None:
    # A separator inside a value would silently split into two items on read.
    if not value.strip():
        raise MarshmallowValidationError("Items cannot be blank.")
    if LIST_SEPARATOR in value:
        raise MarshmallowValidationError(f'Items cannot contain "{LIST_SEPARATOR}".')


def _free_text_list() -> fields.List:
    """A list field stored joined in one column, sized so it can never overflow it."""
    item = fields.String(
        validate=[
            _validate_list_item,
            validate.Length(
                max=LIST_ITEM_MAX_LENGTH,
                error=f"Items must be at most {LIST_ITEM_MAX_LENGTH} characters.",
            ),
        ]
    )
    return fields.List(
        item,
        load_default=list,
        validate=validate.Length(
            max=LIST_MAX_ITEMS, error=f"At most {LIST_MAX_ITEMS} items are allowed."
        ),
    )


def _normalised_item(value: str) -> str:
    """Stored form of a list item, so every search compares like with like."""
    return value.strip().lower()


class _DayTimeSchema(Schema):
    """One end of an opening period: ``{"day": "friday", "time": "18:00"}``."""

    day = fields.String(required=True, validate=validate.OneOf(Weekday.labels()))
    time = fields.Time(required=True, format="%H:%M")

    @post_load
    def _to_weekday(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        data["day"] = Weekday[data["day"].upper()]
        return data


def _as_period(data: dict[str, Any]) -> Period:
    return Period(
        open_day=data["open"]["day"],
        open_time=data["open"]["time"],
        close_day=data["close"]["day"],
        close_time=data["close"]["time"],
    )


class OpeningPeriodSchema(Schema):
    """One opening period (ADR-0008), loaded into an ``opening_hours.Period``."""

    open = fields.Nested(_DayTimeSchema, required=True)
    close = fields.Nested(_DayTimeSchema, required=True)

    @validates_schema
    def _valid_period(self, data: dict[str, Any], **_: Any) -> None:
        error = period_error(_as_period(data))
        if error:
            raise MarshmallowValidationError(error, field_name="close")

    @post_load
    def _to_period(self, data: dict[str, Any], **_: Any) -> Period:
        return _as_period(data)


def _default_opening_hours() -> list[Period]:
    """Every day 09:00 to 18:00, the same default the flat start/end fields had."""
    return [Period(day, time(9, 0), day, time(18, 0)) for day in Weekday]


class EditVenueSchema(Schema):
    """Payload for creating (``POST``) and updating (``PATCH``) a venue.

    Updates are loaded with ``partial`` set to this schema's field names, so
    top-level fields may be left out but every opening period sent must still
    be complete. (``partial=True`` would relax the nested schemas too.)
    """

    name = fields.String(
        required=True,
        validate=[
            not_blank,
            validate.Length(max=200, error="Name must be at most 200 characters."),
        ],
    )
    location = fields.String(
        required=True,
        validate=[
            not_blank,
            validate.Length(max=200, error="Location must be at most 200 characters."),
        ],
    )
    capacity = fields.Integer(
        required=True,
        validate=validate.Range(min=1, error="Capacity must be a positive number."),
    )
    facilities = _free_text_list()
    accessibility_features = _free_text_list()
    supported_layouts = fields.List(
        fields.String(validate=validate.OneOf(LayoutType.values())),
        load_default=list,
        validate=validate.Length(
            max=len(LayoutType), error=f"At most {len(LayoutType)} layouts are allowed."
        ),
    )
    #: SCRUM-67. Left out on create, they take the configured defaults (in the service).
    setup_minutes = fields.Integer(
        validate=validate.Range(min=0, error="Setup time cannot be negative.")
    )
    turnaround_minutes = fields.Integer(
        validate=validate.Range(min=0, error="Turnaround time cannot be negative.")
    )
    #: The whole weekly schedule. On update it replaces the stored schedule,
    #: so each request is checked on its own and never against saved hours.
    opening_hours = fields.List(
        fields.Nested(OpeningPeriodSchema), load_default=_default_opening_hours
    )

    @validates("opening_hours")
    def _periods_do_not_overlap(self, value: list[Any], **_: Any) -> None:
        # Marshmallow still calls this when some items failed (they arrive as
        # raw dicts); those already have their own errors, so skip the check.
        if not all(isinstance(period, Period) for period in value):
            return
        overlap = find_overlap(value)
        if overlap:
            first, second = overlap
            # Keyed by list position, like marshmallow's own per-item errors.
            raise MarshmallowValidationError({second: [f"Overlaps opening period {first}."]})

    @post_load
    def _normalise(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        # Only keys present are touched, so this is safe for partial updates.
        for key in ("name", "location"):
            if key in data:
                data[key] = data[key].strip()
        for key in ("facilities", "accessibility_features"):
            if key in data:
                data[key] = [_normalised_item(item) for item in data[key]]
        return data


def _day_time(day: int, moment: time) -> dict[str, str]:
    """One end of an opening period, in the shape the API accepts."""
    return {"day": Weekday(day).label, "time": f"{moment:%H:%M}"}


class VenueSchema(Schema):
    """Public representation of a venue, as every venue route returns it."""

    id = fields.Integer(dump_only=True)
    name = fields.String(dump_only=True)
    location = fields.String(dump_only=True)
    capacity = fields.Integer(dump_only=True)
    facilities = fields.Function(Venue.facilities_list, dump_only=True)
    accessibility_features = fields.Function(Venue.accessibility_list, dump_only=True)
    supported_layouts = fields.Function(Venue.layouts_list, dump_only=True)
    opening_hours = fields.Method("get_opening_hours", dump_only=True)
    setup_minutes = fields.Integer(dump_only=True)
    turnaround_minutes = fields.Integer(dump_only=True)
    is_active = fields.Boolean(dump_only=True)

    def get_opening_hours(self, venue: Venue) -> list[dict[str, dict[str, str]]]:
        """The weekly schedule in week order (ADR-0008)."""
        periods = sorted(venue.opening_periods, key=lambda p: (p.open_day, p.open_time))
        return [
            {
                "open": _day_time(p.open_day, p.open_time),
                "close": _day_time(p.close_day, p.close_time),
            }
            for p in periods
        ]


class CalendarQuerySchema(TimeRangeSchema):
    """Query parameters for ``GET /api/venues/<id>/calendar`` (SCRUM-26)."""

    start_field = "range_start"
    end_field = "range_end"

    range_start = fields.DateTime(required=True)
    range_end = fields.DateTime(required=True)


class CalendarEntrySchema(Schema):
    """One unavailable period on a venue's calendar, in business time (ADR-0009)."""

    start_time = BusinessDateTime(dump_only=True)
    end_time = BusinessDateTime(dump_only=True)
    event_start = BusinessDateTime(dump_only=True, allow_none=True)
    event_end = BusinessDateTime(dump_only=True, allow_none=True)
    kind = fields.Enum(CalendarEntryKind, by_value=True, dump_only=True)
    reason = fields.String(dump_only=True)


class OverlapWarningSchema(Schema):
    """Two confirmed bookings whose padded periods overlap after a buffer change."""

    booking_ids = fields.List(fields.Integer(), dump_only=True)
    overlap_start = BusinessDateTime(dump_only=True)
    overlap_end = BusinessDateTime(dump_only=True)


class _RequirementsSchema(Schema):
    """Base for payloads that say what an event asks of a venue (SCRUM-35, SCRUM-36).

    Search and the suitability check load requirements through this one schema, so
    they validate and normalise them the same way.
    """

    required_layout = fields.String(
        load_default=None, allow_none=True, validate=validate.OneOf(LayoutType.values())
    )
    required_facilities = _free_text_list()
    required_accessibility = _free_text_list()

    @post_load
    def _normalise_requirements(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        # Stored items are trimmed and lower case; requests are compared the same way.
        for key in ("required_facilities", "required_accessibility"):
            data[key] = [_normalised_item(item) for item in data[key]]
        return data


class VenueSearchSchema(_RequirementsSchema, TimeRangeSchema):
    """Payload for ``POST /api/venues/search`` (SCRUM-35)."""

    start_time = fields.DateTime(required=True)
    end_time = fields.DateTime(required=True)
    min_capacity = fields.Integer(
        required=True,
        validate=validate.Range(min=1, error="min_capacity must be a positive number."),
    )
    location = fields.String(load_default=None, allow_none=True)

    @post_load
    def _normalise_location(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        if data["location"] is not None:
            # A blank location means "anywhere", not "a location containing nothing".
            data["location"] = data["location"].strip() or None
        return data


class VenueMatchSchema(Schema):
    """One search result: the venue and which requested requirements it meets."""

    id = fields.Integer(attribute="venue.id", dump_only=True)
    name = fields.String(attribute="venue.name", dump_only=True)
    capacity = fields.Integer(attribute="venue.capacity", dump_only=True)
    location = fields.String(attribute="venue.location", dump_only=True)
    matched_requirements = fields.Method("get_matched_requirements", dump_only=True)

    def get_matched_requirements(self, match: Any) -> dict[str, Any]:
        """What the venue offers of each requested requirement (AC3)."""
        return {
            "facilities": match.facilities,
            "accessibility_features": match.accessibility_features,
            "layout": match.layout,
        }


class BlockVenueSchema(TimeRangeSchema):
    """Payload for ``POST /api/venues/<id>/blocks`` (SCRUM-34, ADR-0016).

    A block may start in the past, so a fault found part-way through can be recorded
    from when it began, but it can't have ended before today. Opening hours aren't
    checked.

    Args:
        today: The date "ended before today" is measured against. Defaults to today
            in the business timezone; tests pass a fixed date.
    """

    start_time = fields.DateTime(required=True)
    end_time = fields.DateTime(required=True)
    reason = fields.String(required=True, validate=not_blank)

    def __init__(self, *, today: date | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._today = today

    @property
    def today(self) -> date:
        """The reference date for the "not ended before today" rule."""
        return self._today if self._today is not None else local_today()

    @validates("reason")
    def _reason_fits(self, value: str, **_: Any) -> None:
        # Measured once trimmed, since that's what is stored: surrounding spaces
        # mustn't push a reason of the maximum length over it.
        if len(value.strip()) > BLOCK_REASON_MAX_LENGTH:
            raise MarshmallowValidationError(
                f"Reason must be at most {BLOCK_REASON_MAX_LENGTH} characters."
            )

    @validates_schema
    def _does_not_end_before_today(self, data: dict[str, Any], **_: Any) -> None:
        ends_on = to_business_time(as_utc(data["end_time"])).date()
        if ends_on < self.today:
            raise MarshmallowValidationError(
                "Block cannot end before today.", field_name="end_time"
            )

    @post_load
    def _trim_reason(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        data["reason"] = data["reason"].strip()
        return data


class VenueBlockSchema(Schema):
    """One of a venue's blocked periods, in business time (SCRUM-34, ADR-0009)."""

    id = fields.Integer(dump_only=True)
    venue_id = fields.Integer(dump_only=True)
    start_time = BusinessDateTime(dump_only=True)
    end_time = BusinessDateTime(dump_only=True)
    reason = fields.String(dump_only=True)


class ConflictingBookingSchema(Schema):
    """A confirmed booking a new block cuts into, as the period it holds the venue.

    SCRUM-34 AC2; the period includes setup and turnaround (ADR-0011, ADR-0016).
    """

    booking_id = fields.Integer(dump_only=True)
    event_id = fields.Integer(dump_only=True, allow_none=True)
    start_time = BusinessDateTime(dump_only=True)
    end_time = BusinessDateTime(dump_only=True)


class VenueSuitabilitySchema(_RequirementsSchema):
    """Payload for ``POST /api/venues/<id>/suitability`` (SCRUM-36)."""

    expected_attendance = fields.Integer(
        required=True,
        validate=validate.Range(min=1, error="expected_attendance must be a positive number."),
    )


class UnmetRequirementSchema(Schema):
    """One reason a venue can't host an event (SCRUM-36)."""

    requirement = fields.Enum(RequirementKind, by_value=True, dump_only=True)
    message = fields.String(dump_only=True)


class SuitabilityResultSchema(Schema):
    """What ``POST /api/venues/<id>/suitability`` returns (SCRUM-36)."""

    suitable = fields.Boolean(dump_only=True)
    reasons = fields.List(fields.Nested(UnmetRequirementSchema), dump_only=True)


class RaiseBookingRequestSchema(TimeRangeSchema):
    """Payload for raising a venue booking request for an approved event (SCRUM-42).

    Occupancy and layout may be left out; the service then takes them from the event
    (AC3). The justification is only needed when the venue is unsuitable (AC7), which
    the service checks.
    """

    start_field = "starts_at"
    end_field = "ends_at"

    venue_id = fields.Integer(required=True)
    starts_at = fields.DateTime(required=True)
    ends_at = fields.DateTime(required=True)
    purpose = fields.String(required=True, validate=not_blank)
    expected_occupancy = fields.Integer(
        validate=validate.Range(min=1, error="expected_occupancy must be a positive number.")
    )
    required_layout = fields.String(validate=validate.OneOf(LayoutType.values()))
    justification = fields.String()


@dataclass(frozen=True)
class BookingRequestAsShown:
    """A booking request with the event details Venue Staff need beside it (AC4).

    The event's timing is kept as the event stores it, in local business time. The
    event details are read through the events service, never its models.
    """

    request: VenueBookingRequest
    proposed_date: date
    end_date: date | None
    start_time: time
    end_time: time
    accessibility_needs: str | None


class VenueBookingRequestSchema(Schema):
    """A booking request as Venue Staff see it, in business time (AC4, ADR-0009)."""

    id = fields.Integer(attribute="request.id", dump_only=True)
    event_id = fields.Integer(attribute="request.event_id", dump_only=True)
    venue_id = fields.Integer(attribute="request.venue_id", dump_only=True)
    starts_at = BusinessDateTime(attribute="request.starts_at", dump_only=True)
    ends_at = BusinessDateTime(attribute="request.ends_at", dump_only=True)
    purpose = fields.String(attribute="request.purpose", dump_only=True)
    expected_occupancy = fields.Integer(attribute="request.expected_occupancy", dump_only=True)
    required_layout = fields.String(attribute="request.required_layout", dump_only=True)
    justification = fields.String(attribute="request.justification", dump_only=True)
    status = fields.Enum(
        BookingRequestStatus, by_value=True, attribute="request.status", dump_only=True
    )
    event_proposed_date = fields.Date(attribute="proposed_date", dump_only=True)
    event_end_date = fields.Date(attribute="end_date", dump_only=True)
    event_start_time = fields.Time(attribute="start_time", dump_only=True)
    event_end_time = fields.Time(attribute="end_time", dump_only=True)
    accessibility_needs = fields.String(dump_only=True)
