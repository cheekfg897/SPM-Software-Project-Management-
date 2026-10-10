"""Unit tests for SCRUM-42 — Request a venue booking for an approved event.

This file covers the stored request: a new one is Pending (AC5) and keeps the purpose,
occupancy, layout and period it was raised with (AC3).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.venue.models import BookingRequestStatus, VenueBookingRequest

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
