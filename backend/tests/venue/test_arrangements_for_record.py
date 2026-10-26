"""Unit tests for an event's venue arrangements as its read-only record shows them.

SCRUM-84 AC2: venue preparation details are visible to other internal users, not only
to the assigned coordinator. SCRUM-24 AC9: Venue Staff, Technical Support, the Safety
Officer and the Event Coordinator Lead open any submitted event's record, which holds
its venue arrangements (ADR-0095). The events module reads them through
``list_arrangements_for_record``, never the venue models.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, PreparationStatus, Venue
from app.modules.venue.services import ArrangementForRecord
from tests.venue.conftest import SECOND_PERIOD, SavedEvent, raise_booking, two_venues

pytestmark = pytest.mark.scrum_84


def test_each_arrangement_shows_its_venue_period_status_and_preparation(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    event = saved_event()
    auditorium, breakout = two_venues(make_venue, save)
    prepared = raise_booking(auditorium, event, db_session)
    prepared.status = BookingRequestStatus.APPROVED
    prepared.preparation_status = PreparationStatus.IN_PROGRESS
    prepared.preparation_notes = "Chairs set out; stage still to build."
    raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    db_session.commit()

    arrangements = services.list_arrangements_for_record(event.id, session=db_session)

    assert arrangements == [
        ArrangementForRecord(
            venue_name="Auditorium",
            venue_location="Building A",
            venue_capacity=100,
            venue_facilities=["projector", "wifi"],
            venue_accessibility_features=["wheelchair_access"],
            starts_at=datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc),
            purpose="Main hall",
            expected_occupancy=80,
            required_layout=None,
            justification=None,
            status=BookingRequestStatus.APPROVED,
            decision_reason=None,
            hold_expires_at=None,
            needs_alternative_venue=False,
            unavailability=[],
            flagged_after_change=False,
            reassessment_flags=[],
            preparation_status=PreparationStatus.IN_PROGRESS,
            preparation_notes="Chairs set out; stage still to build.",
        ),
        ArrangementForRecord(
            venue_name="Breakout room",
            venue_location="Building A",
            venue_capacity=100,
            venue_facilities=["projector", "wifi"],
            venue_accessibility_features=["wheelchair_access"],
            starts_at=datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
            purpose="Main hall",
            expected_occupancy=80,
            required_layout=None,
            justification=None,
            status=BookingRequestStatus.PENDING,
            decision_reason=None,
            hold_expires_at=None,
            needs_alternative_venue=False,
            unavailability=[],
            flagged_after_change=False,
            reassessment_flags=[],
            preparation_status=PreparationStatus.NOT_STARTED,
            preparation_notes=None,
        ),
    ]


@pytest.mark.parametrize(
    "retired_status",
    [BookingRequestStatus.WITHDRAWN, BookingRequestStatus.RELEASED],
    ids=lambda status: status.value,
)
def test_a_retired_arrangement_is_left_out(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    retired_status: BookingRequestStatus,
) -> None:
    """Only the arrangements that still count are the event's (ADR-0039, ADR-0085)."""
    event = saved_event()
    auditorium, breakout = two_venues(make_venue, save)
    retired = raise_booking(auditorium, event, db_session)
    retired.status = retired_status
    raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    db_session.commit()

    arrangements = services.list_arrangements_for_record(event.id, session=db_session)

    assert [arrangement.venue_name for arrangement in arrangements] == ["Breakout room"]


def test_another_events_arrangements_are_left_out(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    other_event = saved_event()
    raise_booking(venue, other_event, db_session)

    assert services.list_arrangements_for_record(event.id, session=db_session) == []
