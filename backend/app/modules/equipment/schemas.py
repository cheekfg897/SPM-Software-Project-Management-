"""Request and response schemas for the equipment module (marshmallow).

Same shape as the other modules: input schemas raise marshmallow errors, which
:func:`app.common.validation.load_or_raise` turns into the project's 400
``ValidationError`` with per-field details. Output schemas are ``dump_only`` and
define exactly what the API returns.
"""

from __future__ import annotations

from typing import Any

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    post_load,
    validate,
    validates_schema,
)

from app.common.fields import WholeNumber
from app.common.validation import not_blank
from app.modules.equipment.models import NAME_MAX_LENGTH, STORE_NAME_MAX_LENGTH

#: ADR-0014: an equipment type is kept at exactly one venue or store.
NO_LOCATION_MESSAGE = "Either venue_id or store_name is required."
BOTH_LOCATIONS_MESSAGE = "Set either venue_id or store_name, not both."


class EditEquipmentTypeSchema(Schema):
    """Payload for creating (``POST``) and updating (``PATCH``) an equipment type.

    Updates are loaded with ``partial`` set to this schema's field names, so any
    field may be left out; a field that is sent is checked the same way as on create.
    """

    name = fields.String(
        required=True,
        validate=[
            not_blank,
            validate.Length(
                max=NAME_MAX_LENGTH, error=f"Name must be at most {NAME_MAX_LENGTH} characters."
            ),
        ],
    )
    description = fields.String(allow_none=True, load_default=None)
    total_quantity = WholeNumber(
        required=True,
        validate=validate.Range(min=0, error="Total quantity cannot be negative."),
    )
    venue_id = WholeNumber(
        allow_none=True,
        load_default=None,
        validate=validate.Range(min=1, error="venue_id must be a positive number."),
    )
    store_name = fields.String(
        allow_none=True,
        load_default=None,
        validate=[
            not_blank,
            validate.Length(
                max=STORE_NAME_MAX_LENGTH,
                error=f"Store name must be at most {STORE_NAME_MAX_LENGTH} characters.",
            ),
        ],
    )

    @validates_schema
    def _exactly_one_location(self, data: dict[str, Any], **_: Any) -> None:
        # An update that sends neither field keeps the stored location. Sending
        # either one replaces the whole location, so it must still name one place.
        if "venue_id" not in data and "store_name" not in data:
            return
        has_venue = data.get("venue_id") is not None
        has_store = data.get("store_name") is not None
        if has_venue and has_store:
            raise MarshmallowValidationError(BOTH_LOCATIONS_MESSAGE, field_name="venue_id")
        if not has_venue and not has_store:
            raise MarshmallowValidationError(NO_LOCATION_MESSAGE, field_name="venue_id")

    @post_load
    def _normalise(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        # Only keys present are touched, so this is safe for partial updates.
        for key in ("name", "store_name"):
            if data.get(key) is not None:
                data[key] = data[key].strip()
        if data.get("description") is not None:
            data["description"] = data["description"].strip() or None
        return data


class EquipmentTypeSchema(Schema):
    """Public representation of an equipment type, as every route returns it."""

    id = fields.Integer(dump_only=True)
    name = fields.String(dump_only=True)
    description = fields.String(dump_only=True, allow_none=True)
    total_quantity = fields.Integer(dump_only=True)
    venue_id = fields.Integer(dump_only=True, allow_none=True)
    store_name = fields.String(dump_only=True, allow_none=True)


class EquipmentAvailabilitySchema(Schema):
    """One equipment type's availability for an event, with its shortfall (SCRUM-45)."""

    equipment_type_id = fields.Integer(dump_only=True)
    equipment_type_name = fields.String(dump_only=True)
    available = fields.Integer(dump_only=True)
    requested = fields.Integer(dump_only=True)
    shortfall = fields.Integer(dump_only=True)
