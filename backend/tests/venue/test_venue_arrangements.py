"""Unit tests for SCRUM-93 — several venue arrangements for one event.

An arrangement is a ``VenueBookingRequest``. This file covers retiring one and the
"active arrangement" seam that SCRUM-75 counts to decide whether an event is
multi-venue (AC5, AC6).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue
from tests.venue.conftest import SavedEvent, raise_booking

pytestmark = pytest.mark.scrum_93

SECOND_PERIOD = {
    "starts_at": "2026-11-01T13:00:00+08:00",
    "ends_at": "2026-11-01T16:00:00+08:00",
}


def _two_venues(make_venue: Callable[..., Venue], save: Callable[..., None]) -> tuple[Venue, Venue]:
    """Save an auditorium and a breakout room."""
    auditorium = make_venue(name="Auditorium")
    breakout = make_venue(name="Breakout room")
    save(auditorium)
    save(breakout)
    return auditorium, breakout


def _two_arrangements(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    event: EventRequest,
) -> tuple[int, int]:
    """Raise one arrangement at each of two venues, earlier period first; return ids."""
    auditorium, breakout = _two_venues(make_venue, save)
    first = raise_booking(auditorium, event, db_session)
    second = raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    return first.id, second.id


def test_a_new_arrangement_is_active(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    raise_booking(venue, event, db_session)

    assert services.count_active_arrangements(event.id, session=db_session) == 1


def test_an_event_with_two_venues_has_two_active_arrangements(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """SCRUM-75 calls an event multi-venue when this count is more than one."""
    event = saved_event()
    _two_arrangements(db_session, make_venue, save, event)

    assert services.count_active_arrangements(event.id, session=db_session) == 2


def test_a_withdrawn_arrangement_stops_counting(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    event = saved_event()
    first_id, second_id = _two_arrangements(db_session, make_venue, save, event)
    withdrawn = db_session.get(services.VenueBookingRequest, first_id)
    assert withdrawn is not None
    withdrawn.status = BookingRequestStatus.WITHDRAWN
    db_session.commit()

    active = services.list_active_arrangements(event.id, session=db_session)

    assert [arrangement.id for arrangement in active] == [second_id]


def test_active_arrangements_are_listed_earliest_period_first(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """The later period is raised first, so id order and period order disagree."""
    event = saved_event()
    auditorium, breakout = _two_venues(make_venue, save)
    later = raise_booking(breakout, event, db_session, **SECOND_PERIOD)
    earlier = raise_booking(auditorium, event, db_session)

    active = services.list_active_arrangements(event.id, session=db_session)

    assert [arrangement.id for arrangement in active] == [earlier.id, later.id]


def test_another_events_arrangements_are_not_counted(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    mine = saved_event()
    theirs = saved_event()
    raise_booking(venue, theirs, db_session)

    assert services.count_active_arrangements(mine.id, session=db_session) == 0
