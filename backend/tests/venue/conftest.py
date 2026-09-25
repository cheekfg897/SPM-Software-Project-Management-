"""Fixtures shared by the venue tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.venue.models import Booking, BookingStatus, Venue, VenueBlock


@pytest.fixture()
def save(db_session: Session) -> Callable[..., None]:
    """Persist objects to ``db_session`` and commit, as a service would."""

    def _save(*objects: object) -> None:
        db_session.add_all(objects)
        db_session.commit()

    return _save


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
def venue(make_venue: Callable[..., Venue], save: Callable[..., None]) -> Venue:
    """One saved, active venue with default details."""
    saved = make_venue()
    save(saved)
    return saved


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
