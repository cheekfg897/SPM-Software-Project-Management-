"""Request and response schemas for the organisations module (marshmallow).

Input schemas describe the payload and raise marshmallow errors, which
:func:`app.common.validation.load_or_raise` turns into the project's 400
``ValidationError`` with per-field details. Output schemas are ``dump_only``.
"""

from __future__ import annotations

from typing import Any

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    post_load,
    validate,
)

from app.modules.organisations.models import (
    CONTACT_EMAIL_MAX_LENGTH,
    CONTACT_NAME_MAX_LENGTH,
    CONTACT_PHONE_MAX_LENGTH,
    NAME_MAX_LENGTH,
)


def _not_blank(value: str) -> None:
    if not value.strip():
        raise MarshmallowValidationError("Must not be blank.")


class CreateClientOrganisationSchema(Schema):
    """Payload for ``POST /api/organisations`` (SCRUM-66 AC1)."""

    name = fields.String(
        required=True,
        validate=[
            _not_blank,
            validate.Length(
                max=NAME_MAX_LENGTH, error=f"Name must be at most {NAME_MAX_LENGTH} characters."
            ),
        ],
    )
    contact_name = fields.String(
        required=True,
        validate=[
            _not_blank,
            validate.Length(
                max=CONTACT_NAME_MAX_LENGTH,
                error=f"Contact name must be at most {CONTACT_NAME_MAX_LENGTH} characters.",
            ),
        ],
    )
    contact_email = fields.Email(
        required=True,
        validate=validate.Length(
            max=CONTACT_EMAIL_MAX_LENGTH,
            error=f"Contact email must be at most {CONTACT_EMAIL_MAX_LENGTH} characters.",
        ),
    )
    contact_phone = fields.String(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Length(
            max=CONTACT_PHONE_MAX_LENGTH,
            error=f"Contact phone must be at most {CONTACT_PHONE_MAX_LENGTH} characters.",
        ),
    )

    @post_load
    def _normalise(self, data: dict[str, Any], **_: Any) -> dict[str, Any]:
        data["name"] = data["name"].strip()
        data["contact_name"] = data["contact_name"].strip()
        phone = data["contact_phone"]
        if phone is not None:
            # A blank phone number is the same as none at all.
            data["contact_phone"] = phone.strip() or None
        return data


class ClientOrganisationSchema(Schema):
    """Public representation of a client organisation, for internal users only (AC5)."""

    id = fields.Integer(dump_only=True)
    name = fields.String(dump_only=True)
    contact_name = fields.String(dump_only=True)
    contact_email = fields.Email(dump_only=True)
    contact_phone = fields.String(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True, allow_none=True)
