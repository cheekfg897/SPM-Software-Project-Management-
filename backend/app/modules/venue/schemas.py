"""Request/response validation for the venue module (marshmallow).

Same shape as ``app.modules.auth.schemas``: schemas describe the payload,
raise marshmallow errors, and :func:`load_or_raise` converts those into the
project's :class:`~app.common.errors.ValidationError` (400) with per-field
details. Duplicated here (rather than imported from auth) because it has no
real coupling to auth — it just needs a schema and a mapping.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    validate,
    validates_schema,
)

from app.common.errors import ValidationError
from app.modules.venue.models import LayoutType

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_hhmm(value: str) -> None:
    if not _HHMM.match(value):
        raise MarshmallowValidationError('Must be a 24-hour "HH:MM" time.')


class VenueSchema(Schema):
    """Payload for create (``POST``) and update (``PATCH``, loaded with
    ``partial=True`` so only the supplied fields are validated/changed).
    """

    name = fields.String(
        required=True, validate=validate.Length(min=1, max=200, error="Name must be 1–200 characters.")
    )
    location = fields.String(
        required=True,
        validate=validate.Length(min=1, max=200, error="Location must be 1–200 characters."),
    )
    capacity = fields.Integer(
        required=True,
        validate=validate.Range(min=1, error="Capacity must be a positive number."),
    )
    facilities = fields.List(fields.String(), load_default=list)
    accessibility_features = fields.List(fields.String(), load_default=list)
    supported_layouts = fields.List(
        fields.String(validate=validate.OneOf(LayoutType.values())), load_default=list
    )
    operating_hours_start = fields.String(load_default="09:00", validate=_validate_hhmm)
    operating_hours_end = fields.String(load_default="18:00", validate=_validate_hhmm)
    setup_minutes = fields.Integer(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Range(min=0, error="Setup time cannot be negative."),
    )
    turnaround_minutes = fields.Integer(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Range(min=0, error="Turnaround time cannot be negative."),
    )

    @validates_schema
    def _hours_make_sense(self, data: dict[str, Any], **kwargs: Any) -> None:
        start = data.get("operating_hours_start")
        end = data.get("operating_hours_end")
        if start and end and start >= end:
            raise MarshmallowValidationError(
                "operating_hours_end must be after operating_hours_start.",
                field_name="operating_hours_end",
            )


class VenueBlockSchema(Schema):
    """Payload for ``POST /api/venues/<id>/blocks``."""

    start_time = fields.DateTime(required=True)
    end_time = fields.DateTime(required=True)
    reason = fields.String(required=False, load_default="", validate=validate.Length(max=1000))

    @validates_schema
    def _end_after_start(self, data: dict[str, Any], **kwargs: Any) -> None:
        if data["end_time"] <= data["start_time"]:
            raise MarshmallowValidationError("end_time must be after start_time.", field_name="end_time")


class CalendarQuerySchema(Schema):
    """Query params for ``GET /api/venues/<id>/calendar``."""

    range_start = fields.DateTime(required=True)
    range_end = fields.DateTime(required=True)

    @validates_schema
    def _end_after_start(self, data: dict[str, Any], **kwargs: Any) -> None:
        if data["range_end"] <= data["range_start"]:
            raise MarshmallowValidationError("range_end must be after range_start.", field_name="range_end")


class VenueSearchSchema(Schema):
    """Payload for ``POST /api/venues/search`` (SCRUM-35)."""

    start_time = fields.DateTime(required=True)
    end_time = fields.DateTime(required=True)
    min_capacity = fields.Integer(
        required=True, validate=validate.Range(min=1, error="min_capacity must be a positive number.")
    )
    location = fields.String(required=False, allow_none=True, load_default=None)
    required_layout = fields.String(
        required=False, allow_none=True, load_default=None, validate=validate.OneOf(LayoutType.values())
    )
    required_facilities = fields.List(fields.String(), load_default=list)
    required_accessibility = fields.List(fields.String(), load_default=list)

    @validates_schema
    def _end_after_start(self, data: dict[str, Any], **kwargs: Any) -> None:
        if data["end_time"] <= data["start_time"]:
            raise MarshmallowValidationError("end_time must be after start_time.", field_name="end_time")


def load_or_raise(schema: Schema, payload: Mapping[str, Any] | None, *, partial: bool = False) -> dict[str, Any]:
    """Validate ``payload`` with ``schema`` or raise the project ``ValidationError``.

    Args:
        schema: A marshmallow schema instance.
        payload: The decoded JSON body (may be ``None`` if the body was empty).
        partial: If ``True``, missing fields are left out rather than failing
            "required" — used for ``PATCH``-style partial updates.

    Raises:
        ValidationError: HTTP 400, ``details`` maps field name → list of messages.
    """
    if payload is None or not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.")
    try:
        return dict(schema.load(payload, partial=partial))
    except MarshmallowValidationError as exc:
        messages = exc.normalized_messages()
        raise ValidationError("Invalid request.", details=messages) from exc
