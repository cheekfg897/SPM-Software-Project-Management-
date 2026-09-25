"""Request/response validation for the auth module (marshmallow).

Schemas describe the *shape* of a payload. They raise marshmallow errors,
which :func:`app.common.validation.load_or_raise` converts into the project's
:class:`~app.common.errors.ValidationError` (HTTP 400) with per-field details.
"""

from __future__ import annotations

import re
from typing import Any

from flask import current_app, has_app_context
from marshmallow import Schema, ValidationError as MarshmallowValidationError, fields, validate

from app.modules.auth.permissions import Role, role_value

# Password policy (SCRUM-65). See STORIES.md for the stated rule.
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


class RegisterSchema(Schema):
    """Payload for ``POST /api/auth/register``."""

    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True, validate=validate_password_strength)
    full_name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=120, error="Full name must be 1–120 characters."),
    )
    role = fields.String(
        required=True,
        validate=validate.OneOf(Role.values(), error="Role must be one of: {choices}."),
    )
    organisation = fields.String(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=120, error="Organisation must be at most 120 characters."),
    )


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
    organisation = fields.String(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True, allow_none=True)

    def get_role(self, obj: Any) -> str:
        """Serialise the role enum to its string value."""
        return role_value(obj.role)
