"""Unit tests for SCRUM-49 AC11 — the venue arrangements an event's organiser sees.

The venue module's read for the organiser's record (ADR-0099): the event's approved
arrangements, earliest period first, each with its venue's name and location, the
period, and what was arranged (purpose, layout, expected occupancy). Nothing internal:
no Venue Staff decision reason, preparation, justification or ids, and no arrangement in
any other status. When the organiser sees them is the events module's call.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    PreparationStatus,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import COORDINATOR_ID

pytestmark = pytest.mark.scrum_49

SaveArrangement = Callable[..., VenueBookingRequest]
#: Every status but approved: none of them is a confirmed arrangement.
NOT_APPROVED_STATUSES = [
    status for status in BookingRequestStatus if status is not BookingRequestStatus.APPROVED
]


@pytest.fixture()
def save_arrangement(save: Callable[..., None]) -> SaveArrangement:
    """Save an arrangement of ``event`` at ``venue`` from ``hour`` UTC for an hour."""

    def _save(
        event: EventRequest,
        venue: Venue,
        *,
        hour: int,
        status: BookingRequestStatus = BookingRequestStatus.APPROVED,
    ) -> VenueBookingRequest:
        arrangement = VenueBookingRequest(
            event_id=event.id,
            venue_id=venue.id,
            starts_at=datetime(2026, 11, 1, hour, tzinfo=UTC),
            ends_at=datetime(2026, 11, 1, hour + 1, tzinfo=UTC),
            purpose="Main session",
            expected_occupancy=80,
            required_layout="theatre",
            justification="Only hall free that week.",
            decision_reason="Approved for the main session.",
            status=status,
            requested_by=COORDINATOR_ID,
            preparation_status=PreparationStatus.READY,
            preparation_notes="Chairs set out.",
        )
        save(arrangement)
        return arrangement

    return _save


def test_the_organiser_sees_each_approved_arrangement_earliest_first_with_its_venue(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
) -> None:
    """The later period is saved first, so id order and period order disagree."""
    event = saved_event()
    hall = make_venue(name="Main Hall", location="Building A")
    breakout = make_venue(name="Breakout Room", location="Building B, Level 2")
    save(hall, breakout)
    save_arrangement(event, breakout, hour=5)
    save_arrangement(event, hall, hour=1)

    shown = services.list_organiser_venue_arrangements(event.id, session=db_session)

    assert shown == [
        services.OrganiserVenueArrangement(
            venue_name="Main Hall",
            venue_location="Building A",
            starts_at=datetime(2026, 11, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 11, 1, 2, tzinfo=UTC),
            purpose="Main session",
            layout="theatre",
            expected_occupancy=80,
        ),
        services.OrganiserVenueArrangement(
            venue_name="Breakout Room",
            venue_location="Building B, Level 2",
            starts_at=datetime(2026, 11, 1, 5, tzinfo=UTC),
            ends_at=datetime(2026, 11, 1, 6, tzinfo=UTC),
            purpose="Main session",
            layout="theatre",
            expected_occupancy=80,
        ),
    ]


@pytest.mark.parametrize("status", NOT_APPROVED_STATUSES, ids=lambda status: status.value)
def test_an_arrangement_in_any_other_status_is_left_out(
    db_session: Session,
    venue: Venue,
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
    status: BookingRequestStatus,
) -> None:
    event = saved_event()
    save_arrangement(event, venue, hour=1)
    save_arrangement(event, venue, hour=3, status=status)

    shown = services.list_organiser_venue_arrangements(event.id, session=db_session)

    assert [arrangement.starts_at.hour for arrangement in shown] == [1]


def test_another_events_arrangements_are_left_out(
    db_session: Session,
    venue: Venue,
    saved_event: Callable[..., EventRequest],
    save_arrangement: SaveArrangement,
) -> None:
    event = saved_event()
    other_event = saved_event()
    save_arrangement(other_event, venue, hour=1)

    assert services.list_organiser_venue_arrangements(event.id, session=db_session) == []
