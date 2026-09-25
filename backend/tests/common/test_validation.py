"""Unit tests for partial loads in :func:`app.common.validation.load_or_raise`.

Partial loads exist for SCRUM-25's ``PATCH /api/venues/<id>``, where a client sends
only the fields it changes.
"""

from __future__ import annotations

import pytest
from marshmallow import Schema, fields

from app.common.errors import ValidationError
from app.common.validation import load_or_raise

pytestmark = pytest.mark.scrum_25


class _PeriodSchema(Schema):
    start = fields.String(required=True)
    end = fields.String(required=True)


class _VenueLikeSchema(Schema):
    name = fields.String(required=True)
    capacity = fields.Integer(required=True)
    period = fields.Nested(_PeriodSchema)


PARTIAL_FIELDS = ("name", "capacity", "period")


def test_a_full_load_still_requires_every_required_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        load_or_raise(_VenueLikeSchema(), {"name": "Hall"})

    assert exc_info.value.details == {"capacity": ["Missing data for required field."]}


def test_a_partial_load_accepts_only_the_fields_sent() -> None:
    data = load_or_raise(_VenueLikeSchema(), {"capacity": 20}, partial=PARTIAL_FIELDS)

    assert data == {"capacity": 20}


def test_a_partial_load_by_field_name_keeps_nested_fields_required() -> None:
    with pytest.raises(ValidationError) as exc_info:
        load_or_raise(_VenueLikeSchema(), {"period": {"start": "09:00"}}, partial=PARTIAL_FIELDS)

    assert exc_info.value.details == {"period": {"end": ["Missing data for required field."]}}
