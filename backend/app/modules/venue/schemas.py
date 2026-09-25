"""Request and response schemas for the venue module (marshmallow).

Same shape as the other modules: input schemas describe the payload and raise
marshmallow errors, which :func:`app.common.validation.load_or_raise` turns into
the project's 400 ``ValidationError`` with per-field details. Output schemas are
``dump_only`` and define exactly what the API returns.
"""

from __future__ import annotations

from datetime import time
from typing import Any, ClassVar

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)

from app.common.clock import as_utc
from app.common.fields import BusinessDateTime
from app.modules.venue.models import (
    LIST_ITEM_MAX_LENGTH,
    LIST_MAX_ITEMS,
    LIST_SEPARATOR,
    CalendarEntryKind,
    LayoutType,
    Venue,
    Weekday,
)
from app.modules.venue.opening_hours import Period, find_overlap, period_error


def _not_blank(value: str) -> None:
    if not value.strip():
        raise MarshmallowValidationError("Must not be blank.")


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
            _not_blank,
            validate.Length(max=200, error="Name must be at most 200 characters."),
        ],
    )
    location = fields.String(
        required=True,
        validate=[
            _not_blank,
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


class _TimeRangeSchema(Schema):
    """Base for payloads with a start and an end time (ADR-0009).

    Both ends are converted to UTC before they're compared (a time with no offset is
    read as business time), so mixing the two forms can't fail, and the loaded values
    are always timezone-aware UTC. Subclasses declare the two fields and name them.
    """

    start_field: ClassVar[str] = "start_time"
    end_field: ClassVar[str] = "end_time"

    @validates_schema
    def _ends_after_it_starts(self, data: dict[str, Any], **_: Any) -> None:
        if as_utc(data[self.end_field]) <= as_utc(data[self.start_field]):
            raise MarshmallowValidationError(
                f"{self.end_field} must be after {self.start_field}.", field_name=self.end_field
            )

    @post_load
    def _to_utc(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        for key in (self.start_field, self.end_field):
            data[key] = as_utc(data[key])
        return data


class CalendarQuerySchema(_TimeRangeSchema):
    """Query parameters for ``GET /api/venues/<id>/calendar`` (SCRUM-26)."""

    start_field = "range_start"
    end_field = "range_end"

    range_start = fields.DateTime(required=True)
    range_end = fields.DateTime(required=True)


class CalendarEntrySchema(Schema):
    """One unavailable period on a venue's calendar, in business time (ADR-0009)."""

    start_time = BusinessDateTime(dump_only=True)
    end_time = BusinessDateTime(dump_only=True)
    kind = fields.Enum(CalendarEntryKind, by_value=True, dump_only=True)
    reason = fields.String(dump_only=True)
