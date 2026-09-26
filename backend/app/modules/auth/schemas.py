"""Request/response validation for the auth module (marshmallow).

Schemas describe the *shape* of a payload. They raise marshmallow errors,
which :func:`app.common.validation.load_or_raise` converts into the project's
:class:`~app.common.errors.ValidationError` (HTTP 400) with per-field details.
"""

from __future__ import annotations

import re
from typing import Any

from flask import current_app, has_app_context
from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    fields,
    validate,
    validates_schema,
)

from app.common.fields import WholeNumber
from app.modules.auth.permissions import ALL_ROLES, INTERNAL_ROLES, Role, role_value

# Password policy (SCRUM-65): see ADR-0005.
DEFAULT_PASSWORD_MIN_LENGTH = 8
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")


def password_min_length() -> int:
    """Read the configured minimum length, falling back to the default."""
    if has_app_context():
        return int(current_app.config.get("PASSWORD_MIN_LENGTH", DEFAULT_PASSWORD_MIN_LENGTH))
    return DEFAULT_PASSWORD_MIN_LENGTH  # pragma: no cover - only hit outside an app context


def validate_password_strength(password: str) -> None:
    """Enforce the password policy.

    Policy: at least ``PASSWORD_MIN_LENGTH`` characters (default 8), and must
    contain at least one letter and at least one digit.

    Raises:
        marshmallow.ValidationError: with a message naming the failed rule.
    """
    min_len = password_min_length()
    if len(password) < min_len:
        raise MarshmallowValidationError(f"Password must be at least {min_len} characters long.")
    if not _HAS_LETTER.search(password):
        raise MarshmallowValidationError("Password must contain at least one letter.")
    if not _HAS_DIGIT.search(password):
        raise MarshmallowValidationError("Password must contain at least one digit.")


def _role_field(allowed: frozenset[Role]) -> fields.String:
    """A required role field, restricted to the values in ``allowed``.

    Choices are sorted so the validation message reads the same regardless of the
    frozenset's iteration order.
    """
    choices = sorted(role.value for role in allowed)
    return fields.String(
        required=True, validate=validate.OneOf(choices, error="Role must be one of: {choices}.")
    )


class _NewUserSchema(Schema):
    """Fields common to every new account, whoever creates it (SCRUM-88)."""

    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True, validate=validate_password_strength)
    full_name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=120, error="Full name must be 1–120 characters."),
    )


class RegisterSchema(_NewUserSchema):
    """Payload for ``POST /api/auth/register`` (SCRUM-65 AC3, AC4; ADR-0023)."""

    # Kept at ALL_ROLES in this commit so self-registration is unchanged; the
    # next commit in SCRUM-88 narrows this to EXTERNAL_ROLES.
    role = _role_field(ALL_ROLES)
    #: The client organisation an Event Organiser belongs to (SCRUM-66 AC2, ADR-0013).
    #: Whether it exists is checked by the service, which can read the database.
    organisation_id = WholeNumber(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Range(min=1, error="Organisation id must be a positive number."),
    )

    @validates_schema
    def _organisation_matches_role(self, data: dict[str, Any], **_: Any) -> None:
        # Only runs when every field passed its own validation, so ``role`` is a
        # known role here.
        is_organiser = data["role"] == Role.EVENT_ORGANISER.value
        has_organisation = data["organisation_id"] is not None
        if is_organiser and not has_organisation:
            raise MarshmallowValidationError(
                "Event Organisers must belong to a client organisation.",
                field_name="organisation_id",
            )
        if has_organisation and not is_organiser:
            raise MarshmallowValidationError(
                "Only Event Organisers belong to a client organisation.",
                field_name="organisation_id",
            )


class CreateStaffUserSchema(_NewUserSchema):
    """Payload for ``flask create-staff-user`` (SCRUM-88, ADR-0023).

    No ``organisation_id`` field: staff accounts never belong to a client organisation.
    """

    role = _role_field(INTERNAL_ROLES)


class LoginSchema(Schema):
    """Payload for ``POST /api/auth/login``."""

    email = fields.String(required=True)
    password = fields.String(required=True, load_only=True)


class UserSchema(Schema):
    """Public representation of a user. ``password_hash`` is never included."""

    id = fields.Integer(dump_only=True)
    email = fields.Email(dump_only=True)
    full_name = fields.String(dump_only=True)
    role = fields.Method("get_role", dump_only=True)
    #: The caller's own client organisation, for Event Organisers (SCRUM-66).
    organisation_id = fields.Integer(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True, allow_none=True)

    def get_role(self, obj: Any) -> str:
        """Serialise the role enum to its string value."""
        return role_value(obj.role)
