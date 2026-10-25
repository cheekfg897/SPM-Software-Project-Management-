"""Unit tests for the venues an event is booked at, as an Attendee sees them.

SCRUM-24 AC11: an Attendee who registered for an event sees each venue's name and
location (as SCRUM-52 shows an event), and nothing about the bookings themselves
(ADR-0109). The registration module reads them through ``list_booked_venues``, never
the venue models.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from app.modules.venue.services import BookedVenue
from tests.venue.conftest import SECOND_PERIOD, SavedEvent, raise_booking

pytestmark = pytest.mark.scrum_24

#: Every status but approved: a venue that is not, or no longer, where the event is.
NOT_BOOKED_STATUSES = [
    status for status in BookingRequestStatus if status is not BookingRequestStatus.APPROVED
]


def _approve(*arrangements: VenueBookingRequest) -> None:
    """Mark arrangements approved by Venue Staff, as SCRUM-43 leaves them."""
    for arrangement in arrangements:
        arrangement.status = BookingRequestStatus.APPROVED


def test_each_booked_venue_shows_its_name_and_location_earliest_booking_first(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    event = saved_event()
    hall = make_venue(name="Main Hall", location="Building A, Level 1")
    garden = make_venue(name="Roof Garden", location="Building B, Level 9")
    save(hall, garden)
    afternoon = raise_booking(garden, event, db_session, **SECOND_PERIOD)
    morning = raise_booking(hall, event, db_session)
    _approve(afternoon, morning)
    db_session.commit()

    venues = services.list_booked_venues(event.id, session=db_session)

    assert venues == [
        BookedVenue(name="Main Hall", location="Building A, Level 1"),
        BookedVenue(name="Roof Garden", location="Building B, Level 9"),
    ]


@pytest.mark.parametrize("status", NOT_BOOKED_STATUSES, ids=lambda status: status.value)
def test_an_arrangement_venue_staff_have_not_approved_is_left_out(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    status: BookingRequestStatus,
) -> None:
    event = saved_event()
    booked = make_venue(name="Main Hall")
    not_booked = make_venue(name="Roof Garden")
    save(booked, not_booked)
    _approve(raise_booking(booked, event, db_session))
    other = raise_booking(not_booked, event, db_session, **SECOND_PERIOD)
    other.status = status
    db_session.commit()

    venues = services.list_booked_venues(event.id, session=db_session)

    assert [venue.name for venue in venues] == ["Main Hall"]


def test_a_venue_booked_for_two_periods_is_listed_once(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    _approve(
        raise_booking(venue, event, db_session),
        raise_booking(venue, event, db_session, **SECOND_PERIOD),
    )
    db_session.commit()

    venues = services.list_booked_venues(event.id, session=db_session)

    assert venues == [BookedVenue(name="Main Hall", location="Building A")]


def test_another_events_booked_venues_are_left_out(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = saved_event()
    other_event = saved_event()
    _approve(raise_booking(venue, other_event, db_session))
    db_session.commit()

    assert services.list_booked_venues(event.id, session=db_session) == []
