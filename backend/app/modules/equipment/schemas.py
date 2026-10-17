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
    validates,
    validates_schema,
)

from app.common.fields import BusinessDateTime, PositiveId, PositiveQuantity, WholeNumber
from app.common.validation import not_blank
from app.modules.equipment.models import (
    NAME_MAX_LENGTH,
    PREPARATION_NOTES_MAX_LENGTH,
    STORE_NAME_MAX_LENGTH,
    OutOfServiceReason,
    PreparationStatus,
)

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


class EquipmentUnitsSchema(Schema):
    """An equipment type and how many of its units, to reserve them (SCRUM-46 AC1).

    The event comes from the URL and the period from the event, so neither is sent.
    """

    equipment_type_id = PositiveId("equipment_type_id", required=True)
    quantity = PositiveQuantity(required=True)


class UpdatePreparationSchema(Schema):
    """Payload for ``PUT /api/equipment/reservations/<id>/preparation`` (SCRUM-85 AC1).

    Each update states the whole picture: the ``status``, and the ``notes`` if there are
    any (left out, they are cleared). Nothing else of the reservation can be sent
    (AC3): marshmallow rejects an unknown field. Notes that are sent must not be blank,
    and are trimmed.
    """

    status = fields.Enum(
        PreparationStatus,
        by_value=True,
        required=True,
        error_messages={"unknown": "Status must be not_started, in_progress or ready."},
    )
    notes = fields.String(allow_none=True, load_default=None, validate=not_blank)

    @validates("notes")
    def _notes_fit(self, value: str | None, **_: Any) -> None:
        # Marshmallow also runs this on the default of notes left out.
        if value is None:
            return
        # Measured once trimmed, since that's what is stored.
        if len(value.strip()) > PREPARATION_NOTES_MAX_LENGTH:
            raise MarshmallowValidationError(
                f"Notes must be at most {PREPARATION_NOTES_MAX_LENGTH} characters."
            )

    @post_load
    def _trim_notes(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        if data["notes"] is not None:
            data["notes"] = data["notes"].strip()
        return data


class EquipmentReservationSchema(Schema):
    """One reservation as the API shows it, times in business time (SCRUM-46 AC4).

    The event is left out: a reservation is always read under the event's reference.
    ``reserved_by`` is the reserver's full name, never their id, as on the event
    record; it is ``null`` once their account no longer exists.
    """

    id = fields.Integer(dump_only=True)
    equipment_type_id = fields.Integer(dump_only=True)
    equipment_type_name = fields.String(dump_only=True)
    quantity = fields.Integer(dump_only=True)
    starts_at = BusinessDateTime(dump_only=True)
    ends_at = BusinessDateTime(dump_only=True)
    reserved_by = fields.String(dump_only=True, allow_none=True)
    created_at = BusinessDateTime(dump_only=True)
    #: True while units out of service leave the reservation short (SCRUM-47 AC3).
    needs_attention = fields.Boolean(dump_only=True)
    preparation_status = fields.Enum(PreparationStatus, by_value=True, dump_only=True)
    preparation_notes = fields.String(dump_only=True, allow_none=True)


class MarkOutOfServiceSchema(Schema):
    """Units of an equipment type to take out of service, and why (SCRUM-47 AC1).

    The type comes from the URL and the user and time from the request, so none is sent.
    """

    quantity = PositiveQuantity(required=True)
    reason = fields.Enum(OutOfServiceReason, by_value=True, required=True)


class OutOfServiceSchema(Schema):
    """Units out of service as the API shows them (SCRUM-47 AC4), in business time.

    ``recorded_by`` and ``resolved_by`` are full names, never ids, as on a
    reservation.
    """

    id = fields.Integer(dump_only=True)
    equipment_type_id = fields.Integer(dump_only=True)
    quantity = fields.Integer(dump_only=True)
    reason = fields.Enum(OutOfServiceReason, by_value=True, dump_only=True)
    recorded_by = fields.String(dump_only=True, allow_none=True)
    recorded_at = BusinessDateTime(dump_only=True)
    resolved_by = fields.String(dump_only=True, allow_none=True)
    resolved_at = BusinessDateTime(dump_only=True, allow_none=True)
