"""Marshmallow fields shared by every module's schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from marshmallow import fields

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
