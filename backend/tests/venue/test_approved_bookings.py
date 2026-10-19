"""Unit tests for SCRUM-84 — Venue Staff list the approved bookings they prepare.

Preparation is recorded against an approved booking (AC1, ADR-0049), but Venue Staff
had no route that lists one: their queue holds only the requests still to decide. This
list is every approved booking, the earliest event first, with its preparation details
(ADR-0080). Only Venue Staff may read it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, PreparationStatus, Venue
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import (
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    decide,
    raise_booking,
    two_venues,
)

pytestmark = pytest.mark.scrum_84

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

NON_VENUE_STAFF_ROLES = sorted(ALL_ROLES - {Role.VENUE_STAFF}, key=lambda role: role.value)
#: Every status but Approved, from the enum, so a status added later is checked too.
NOT_APPROVED_STATUSES = sorted(
    set(BookingRequestStatus) - {BookingRequestStatus.APPROVED}, key=lambda status: status.value
)
PATH = "/api/venues/booking-requests/approved"
ENDPOINT = "venue.list_approved_booking_requests"


def _listed_ids(session: Session) -> list[int]:
    return [shown.request.id for shown in services.list_approved_booking_requests(session=session)]


# --------------------------------------------------------------------------
# The list
# --------------------------------------------------------------------------


def test_the_list_is_empty_when_no_booking_is_approved(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    raise_booking(venue, saved_event(), db_session)

    assert services.list_approved_booking_requests(session=db_session) == []


def test_only_approved_bookings_are_listed(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """A pending or rejected request has nothing to prepare."""
    auditorium, breakout = two_venues(make_venue, save)
    event = saved_event()
    approved = raise_booking(auditorium, event, db_session)
    decide(approved.id, "approved", db_session)
    rejected = raise_booking(breakout, event, db_session)
    decide(rejected.id, "rejected", db_session, reason="Closed for repairs")
    raise_booking(breakout, event, db_session, **SECOND_PERIOD)

    assert _listed_ids(db_session) == [approved.id]


@pytest.mark.parametrize("status", NOT_APPROVED_STATUSES, ids=lambda status: status.value)
def test_a_booking_in_any_other_status_is_left_out(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: BookingRequestStatus
) -> None:
    """Only an approved booking can be prepared, so nothing else is listed to prepare.

    The status is set directly: the list reads only the status, and reaching each one
    through its own route would need a different set-up per status.
    """
    request = raise_booking(venue, saved_event(), db_session)
    request.status = status
    db_session.flush()

    assert _listed_ids(db_session) == []


def test_the_earliest_event_comes_first_whatever_order_they_were_approved_in(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    auditorium, breakout = two_venues(make_venue, save)
    later_event = saved_event(proposed_date=datetime(2026, 11, 5, tzinfo=UTC).date())
    earlier_event = saved_event(proposed_date=datetime(2026, 11, 1, tzinfo=UTC).date())
    for_later = raise_booking(
        auditorium,
        later_event,
        db_session,
        starts_at="2026-11-05T09:00:00+08:00",
        ends_at="2026-11-05T12:00:00+08:00",
    )
    for_earlier = raise_booking(breakout, earlier_event, db_session)
    decide(for_later.id, "approved", db_session)
    decide(for_earlier.id, "approved", db_session)

    assert _listed_ids(db_session) == [for_earlier.id, for_later.id]


def test_each_booking_carries_its_preparation_details_and_its_events_timing(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """What the Venue Staff page shows above the form, so they see what is recorded."""
    event = saved_event()
    booking = raise_booking(venue, event, db_session)
    decide(booking.id, "approved", db_session)
    approve_safety(event, db_session)
    services.update_preparation_details(
        booking.id,
        {"status": "in_progress", "notes": "Stage to do."},
        updated_by=VENUE_STAFF_ID,
        session=db_session,
    )

    [shown] = services.list_approved_booking_requests(session=db_session)

    assert shown.request.preparation_status is PreparationStatus.IN_PROGRESS
    assert shown.request.preparation_notes == "Stage to do."
    assert shown.proposed_date == event.proposed_date
    assert shown.start_time == event.start_time


# --------------------------------------------------------------------------
# The route
# --------------------------------------------------------------------------


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, shown: BookingRequestAsShown
) -> dict[str, MagicMock]:
    return replace_services(services, {"list_approved_booking_requests": [shown]})


@pytest.mark.parametrize("role", NON_VENUE_STAFF_ROLES, ids=lambda role: role.value)
def test_a_role_other_than_venue_staff_is_refused_with_403(
    call_route: CallRoute,
    token_for: Callable[..., str],
    mock_services: dict[str, MagicMock],
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError):
        call_route(ENDPOINT, "GET", PATH, {}, token_for(role=role))

    mock_services["list_approved_booking_requests"].assert_not_called()


def test_a_caller_without_a_token_is_refused_with_401(
    call_route: CallRoute, mock_services: dict[str, MagicMock]
) -> None:
    with pytest.raises(AuthenticationError):
        call_route(ENDPOINT, "GET", PATH, {}, None)

    mock_services["list_approved_booking_requests"].assert_not_called()


def test_venue_staff_get_200_with_each_approved_booking(
    call_route: CallRoute,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    mock_services: dict[str, MagicMock],
) -> None:
    token = token_for(make_user(role=Role.VENUE_STAFF, user_id=VENUE_STAFF_ID))

    response, status = call_route(ENDPOINT, "GET", PATH, {}, token)

    body = response.get_json()
    assert status == 200
    assert [entry["id"] for entry in body] == [11]
    assert body[0]["accessibility_needs"] == "Step-free entrance"
    mock_services["list_approved_booking_requests"].assert_called_once_with()
