"""Fixtures shared by the venue tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.venue.models import Booking, BookingStatus, Venue, VenueBlock


@pytest.fixture()
def reload_venue(db_session: Session) -> Callable[[int], Venue]:
    """Read a venue back from the database rather than from the session's cache."""

    def _reload(venue_id: int) -> Venue:
        db_session.expire_all()
        venue = db_session.get(Venue, venue_id)
        assert venue is not None
        return venue

    return _reload


@pytest.fixture()
def make_booking() -> Callable[..., Booking]:
    """Factory for bookings against a venue; add one to ``db_session`` to persist it."""

    def _make(
        venue: Venue,
        start: datetime,
        end: datetime,
        *,
        status: BookingStatus = BookingStatus.CONFIRMED,
        event_id: int | None = None,
    ) -> Booking:
        return Booking(
            venue_id=venue.id, start_time=start, end_time=end, status=status, event_id=event_id
        )

    return _make


@pytest.fixture()
def make_block() -> Callable[..., VenueBlock]:
    """Factory for blocked periods; add one to ``db_session`` to persist it."""

    def _make(
        venue: Venue, start: datetime, end: datetime, *, reason: str = "Maintenance"
    ) -> VenueBlock:
        return VenueBlock(venue_id=venue.id, start_time=start, end_time=end, reason=reason)

    return _make


@pytest.fixture()
def saved_event(db_session: Session) -> Callable[..., EventRequest]:
    """Factory for a saved event: approved, coordinated by user 3, 250 attending.

    The event has no layout of its own, only free-text venue requirements.
    """
    counter = {"n": 0}

    def _save(status: EventRequestStatus = EventRequestStatus.APPROVED) -> EventRequest:
        counter["n"] += 1
        event = EventRequest(
            reference=f"EVR-{counter['n']:08d}",
            status=status,
            organiser_id=7,
            coordinator_id=3,
            name="Partner Summit",
            proposed_date=date(2026, 11, 1),
            end_date=date(2026, 11, 2),
            start_time=time(9, 0),
            end_time=time(17, 30),
            expected_attendance=80,
            accessibility_needs="Step-free entrance",
            registration_required=False,
        )
        db_session.add(event)
        db_session.commit()
        return event

    return _save
