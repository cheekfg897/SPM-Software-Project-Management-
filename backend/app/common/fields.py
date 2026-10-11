"""Marshmallow fields shared by every module's schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from marshmallow import fields, validate

from app.common.clock import to_business_time


class BusinessDateTime(fields.DateTime):
    """A timestamp written out in business time, e.g. ``+08:00`` (ADR-0009).

    Values are stored and compared in UTC; only the response shows business time, so
    clients display what they receive and never need to know the timezone themselves.
    """

    def _serialize(self, value: datetime | None, attr: str | None, obj: Any, **kwargs: Any) -> Any:
        if value is None:
            return None
        return super()._serialize(to_business_time(value), attr, obj, **kwargs)


class WholeNumber(fields.Integer):
    """An integer field that also rejects JSON booleans.

    ``fields.Integer(strict=True)`` accepts ``true`` because ``bool`` is an
    integer subclass in Python.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(strict=True, **kwargs)

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs: Any) -> int:
        if isinstance(value, bool):
            raise self.make_error("invalid")
        return super()._deserialize(value, attr, data, **kwargs)


class PositiveId(WholeNumber):
    """The id of something the payload points at: a whole number of at least 1.

    The message names the field as the client sent it, e.g. "equipment_type_id must
    be a positive number.", so the id itself is passed in.
    """

    def __init__(self, field_name: str, **kwargs: Any) -> None:
        at_least_one = validate.Range(min=1, error=f"{field_name} must be a positive number.")
        super().__init__(validate=at_least_one, **kwargs)


class PositiveQuantity(WholeNumber):
    """How many units of something: a whole number of at least 1."""

    def __init__(self, **kwargs: Any) -> None:
        at_least_one = validate.Range(min=1, error="Quantity must be at least 1.")
        super().__init__(validate=at_least_one, **kwargs)
