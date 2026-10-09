"""Shared payload validation helpers.

Every module validates request bodies with marshmallow schemas and uses
:func:`load_or_raise` to turn marshmallow errors into the project's
:class:`~app.common.errors.ValidationError` (HTTP 400). :func:`not_blank` is the
validator for required text that must contain more than whitespace, and
:class:`TimeRangeSchema` is the base for every payload carrying a start and an
end instant (ADR-0009).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from marshmallow import (
    Schema,
    ValidationError as MarshmallowValidationError,
    post_load,
    validates_schema,
)

from app.common.clock import as_utc
from app.common.errors import ValidationError


def not_blank(value: str) -> None:
    """Marshmallow validator: reject a string that is empty or only whitespace."""
    if not value.strip():
        raise MarshmallowValidationError("Must not be blank.")


def load_or_raise(
    schema: Schema,
    payload: Mapping[str, Any] | None,
    *,
    partial: Sequence[str] = (),
) -> dict[str, Any]:
    """Validate ``payload`` with ``schema`` or raise the project ``ValidationError``.

    Args:
        schema: A marshmallow schema instance.
        payload: The decoded JSON body (may be ``None`` if the body was empty).
        partial: Top-level fields that may be left out, for ``PATCH``-style updates.
            Field names rather than marshmallow's ``partial=True``, which would also
            stop enforcing required fields inside nested schemas.

    Returns:
        The cleaned, validated data.

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


class TimeRangeSchema(Schema):
    """Base for payloads with a start and an end instant (ADR-0009).

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
