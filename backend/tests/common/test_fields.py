"""Unit tests for :class:`app.common.fields.BusinessDateTime` (SCRUM-26, ADR-0009).

Responses show times in business time with its offset, so a client in Singapore can
display them as they come.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from marshmallow import Schema

from app.common.fields import BusinessDateTime

pytestmark = pytest.mark.scrum_26


class _MomentSchema(Schema):
    moment = BusinessDateTime(allow_none=True)


def test_a_utc_time_is_written_out_in_business_time() -> None:
    dumped = _MomentSchema().dump({"moment": datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)})

    assert dumped == {"moment": "2026-10-01T09:00:00+08:00"}


def test_no_time_is_written_out_as_null() -> None:
    assert _MomentSchema().dump({"moment": None}) == {"moment": None}
