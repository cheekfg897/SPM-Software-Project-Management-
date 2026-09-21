"""Shared payload validation helper.

Every module validates request bodies with marshmallow schemas and uses
:func:`load_or_raise` to turn marshmallow errors into the project's
:class:`~app.common.errors.ValidationError` (HTTP 400).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from marshmallow import Schema, ValidationError as MarshmallowValidationError

from app.common.errors import ValidationError


def load_or_raise(schema: Schema, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate ``payload`` with ``schema`` or raise the project ``ValidationError``.

    Args:
        schema: A marshmallow schema instance.
        payload: The decoded JSON body (may be ``None`` if the body was empty).

    Returns:
        The cleaned, validated data.

    Raises:
        ValidationError: HTTP 400, ``details`` maps field name → list of messages.
    """
    if payload is None or not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.")
    try:
        return dict(schema.load(payload))
    except MarshmallowValidationError as exc:
        messages = exc.normalized_messages()
        raise ValidationError("Invalid request.", details=messages) from exc
