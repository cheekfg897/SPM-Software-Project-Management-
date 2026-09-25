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
