"""Unit tests for SCRUM-42 — Request a venue booking for an approved event.

This file covers the stored request: a new one is Pending (AC5) and keeps the purpose,
occupancy, layout and period it was raised with (AC3). It also covers the payload that
raises one and the shape Venue Staff see it in, with the event's timing and
accessibility requirements alongside (AC4).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.common.validation import load_or_raise
from app.modules.venue.models import BookingRequestStatus, VenueBookingRequest
from app.modules.venue.schemas import (
    BookingRequestAsShown,
    RaiseBookingRequestSchema,
    VenueBookingRequestSchema,
)

pytestmark = pytest.mark.scrum_42

STARTS_AT = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
ENDS_AT = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def test_a_new_request_is_pending(db_session: Session) -> None:
    request = VenueBookingRequest(
        event_id=1,
        venue_id=1,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        purpose="Main hall",
        expected_occupancy=150,
        required_layout="theatre",
        requested_by=1,
    )
    db_session.add(request)
    db_session.flush()

    assert request.status is BookingRequestStatus.PENDING


def test_a_saved_request_keeps_its_details_and_has_no_justification_yet(
    db_session: Session,
) -> None:
    db_session.add(
        VenueBookingRequest(
            event_id=1,
            venue_id=1,
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
            purpose="Main hall",
            expected_occupancy=150,
            required_layout=None,
            requested_by=7,
        )
    )
    db_session.commit()
    db_session.expire_all()

    saved = db_session.query(VenueBookingRequest).one()

    assert saved.starts_at == STARTS_AT
    assert saved.ends_at == ENDS_AT
    assert (saved.purpose, saved.expected_occupancy, saved.requested_by) == ("Main hall", 150, 7)
    assert saved.required_layout is None
    assert saved.justification is None


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "venue_id": 3,
        "starts_at": "2026-11-01T09:00:00+08:00",
        "ends_at": "2026-11-01T12:00:00+08:00",
        "purpose": "Main hall",
    }
    return {**payload, **overrides}


def _load(**overrides: Any) -> dict[str, Any]:
    return load_or_raise(RaiseBookingRequestSchema(), _payload(**overrides))


def test_a_valid_payload_loads_with_utc_instants_and_optional_fields_left_out() -> None:
    loaded = _load()

    assert loaded == {
        "venue_id": 3,
        "starts_at": datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
        "ends_at": datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        "purpose": "Main hall",
    }


def test_optional_occupancy_layout_and_justification_load_when_sent() -> None:
    loaded = _load(expected_occupancy=80, required_layout="theatre", justification="Only hall free")

    assert (loaded["expected_occupancy"], loaded["required_layout"], loaded["justification"]) == (
        80,
        "theatre",
        "Only hall free",
    )


@pytest.mark.parametrize("ends_at", ["2026-11-01T09:00:00+08:00", "2026-11-01T08:00:00+08:00"])
def test_a_request_ending_at_or_before_it_starts_is_rejected_on_ends_at(ends_at: str) -> None:
    with pytest.raises(ValidationError) as caught:
        _load(ends_at=ends_at)

    assert caught.value.details == {"ends_at": ["ends_at must be after starts_at."]}


def test_a_purpose_of_only_whitespace_is_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        _load(purpose="   ")

    assert caught.value.details == {"purpose": ["Must not be blank."]}


def _request() -> VenueBookingRequest:
    return VenueBookingRequest(
        id=9,
        event_id=1,
        venue_id=3,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        purpose="Main hall",
        expected_occupancy=150,
        required_layout="theatre",
        justification=None,
        status=BookingRequestStatus.PENDING,
        requested_by=7,
    )


def test_a_request_is_shown_with_the_events_timing_and_accessibility_needs() -> None:
    shown = BookingRequestAsShown(
        request=_request(),
        proposed_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
        start_time=time(9, 0),
        end_time=time(17, 30),
        accessibility_needs="Step-free entrance",
    )

    assert VenueBookingRequestSchema().dump(shown) == {
        "id": 9,
        "event_id": 1,
        "venue_id": 3,
        "starts_at": "2026-11-01T17:00:00+08:00",
        "ends_at": "2026-11-01T20:00:00+08:00",
        "purpose": "Main hall",
        "expected_occupancy": 150,
        "required_layout": "theatre",
        "justification": None,
        "status": "pending",
        "event_proposed_date": "2026-11-01",
        "event_end_date": "2026-11-02",
        "event_start_time": "09:00:00",
        "event_end_time": "17:30:00",
        "accessibility_needs": "Step-free entrance",
    }
