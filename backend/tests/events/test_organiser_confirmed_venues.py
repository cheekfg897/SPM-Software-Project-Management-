"""Unit tests for SCRUM-49 AC11 — a confirmed event's venues on its organiser's record.

"Given the event is confirmed, Then every venue, the date, time and confirmed
arrangements are visible to the Event Organiser." Once the event is Confirmed, and
still once it is Completed, the organiser's record lists each approved venue
arrangement with its venue, period and what was arranged (ADR-0099). Before the event
is Confirmed it lists none: the AC's literal reading, a default pending the Product
Owner (ADR-0051 question 2). The coordinator's record has no such list: they read the
arrangements from the venue requests page.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    EventRecord,
    OrganiserEventRecord,
    get_event_record_for_organiser,
)
from app.modules.venue.models import BookingRequestStatus, VenueBookingRequest
from app.modules.venue.services import OrganiserVenueArrangement

pytestmark = pytest.mark.scrum_49

ORGANISER_ID = 7
REFERENCE = "EVR-AAAAAAAA"
#: The statuses in which the organiser sees the venues: once the event is confirmed.
VENUES_SHOWN_STATUSES = [EventRequestStatus.CONFIRMED, EventRequestStatus.COMPLETED]
#: Every other status, built from the enum so a new status is checked too.
VENUES_HIDDEN_STATUSES = [
    status for status in EventRequestStatus if status not in VENUES_SHOWN_STATUSES
]
MAIN_HALL_AT_NINE = OrganiserVenueArrangement(
    venue_name="Main Hall",
    venue_location="Building A",
    starts_at=datetime(2026, 11, 1, 9, tzinfo=UTC),
    ends_at=datetime(2026, 11, 1, 9, 30, tzinfo=UTC),
    purpose="Main session",
    layout=None,
    expected_occupancy=80,
)

Arrange = Callable[[BookingRequestStatus], VenueBookingRequest]


# --------------------------------------------------------------------------
# The organiser's record, by the event's status
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", VENUES_SHOWN_STATUSES, ids=lambda status: status.value)
def test_once_confirmed_the_organisers_record_lists_each_approved_venue(
    saved_users: list[User],
    set_status: Callable[[EventRequestStatus], None],
    arrange: Arrange,
    status: EventRequestStatus,
) -> None:
    """A replacement still pending isn't a confirmed arrangement, so it isn't listed."""
    arrange(BookingRequestStatus.APPROVED)
    arrange(BookingRequestStatus.PENDING)
    set_status(status)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)

    assert record.venue_arrangements == (MAIN_HALL_AT_NINE,)


@pytest.mark.parametrize("status", VENUES_HIDDEN_STATUSES, ids=lambda status: status.value)
def test_before_it_is_confirmed_the_organisers_record_lists_no_venues(
    saved_users: list[User],
    set_status: Callable[[EventRequestStatus], None],
    arrange: Arrange,
    status: EventRequestStatus,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    set_status(status)

    record = get_event_record_for_organiser(ORGANISER_ID, REFERENCE)

    assert record.venue_arrangements == ()


# --------------------------------------------------------------------------
# How the record route shows them
# --------------------------------------------------------------------------


def test_the_organisers_record_route_shows_each_venue_in_business_time(
    open_record_route: Callable[[OrganiserEventRecord], dict[str, Any]],
    make_event_request: Callable[..., EventRequest],
) -> None:
    record = OrganiserEventRecord(
        event_request=make_event_request(status=EventRequestStatus.CONFIRMED),
        coordinator=None,
        venue_arrangements=(MAIN_HALL_AT_NINE,),
    )

    body = open_record_route(record)

    assert body["venue_arrangements"] == [
        {
            "venue_name": "Main Hall",
            "venue_location": "Building A",
            "starts_at": "2026-11-01T17:00:00+08:00",
            "ends_at": "2026-11-01T17:30:00+08:00",
            "purpose": "Main session",
            "layout": None,
            "expected_occupancy": 80,
        }
    ]


def test_the_coordinators_record_route_has_no_venue_list(
    call_route: Callable[..., Any],
    replace_services: Callable[..., Any],
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    make_event_request: Callable[..., EventRequest],
) -> None:
    """The coordinator reads every arrangement from the venue requests page instead."""
    record = EventRecord(
        event_request=make_event_request(status=EventRequestStatus.CONFIRMED), coordinator=None
    )
    replace_services(routes, {"get_event_record_for_coordinator": record})
    coordinator = make_user(role=Role.EVENT_COORDINATOR, user_id=3)

    response, status = call_route(
        "events.get_my_request",
        "GET",
        f"/api/events/requests/{REFERENCE}",
        {"reference": REFERENCE},
        token_for(coordinator),
    )

    assert status == 200
    assert "venue_arrangements" not in response.get_json()
