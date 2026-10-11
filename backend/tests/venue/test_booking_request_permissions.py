"""Unit tests for SCRUM-42 — who may raise and list venue booking requests.

Only the Event Coordinator may call either route. The registered view functions run
inside a request context, so the real decorators decide; a refused caller must never
reach the service layer. A coordinator who isn't assigned to the event is refused by
the real service, which the listing route passes on as a 404.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, VenueBookingRequest
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import COORDINATOR_ID

pytestmark = pytest.mark.scrum_42

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

NON_COORDINATOR_ROLES = sorted(ALL_ROLES - {Role.EVENT_COORDINATOR}, key=lambda r: r.value)

PATH = "/api/venues/events/5/booking-requests"
# (endpoint, HTTP method, the service function it calls)
ROUTES = [
    ("venue.raise_booking_request", "POST", "raise_booking_request"),
    ("venue.list_booking_requests", "GET", "list_booking_requests_for_event"),
]
ROUTE_IDS = [route[0] for route in ROUTES]


@pytest.fixture()
def shown() -> BookingRequestAsShown:
    """A Pending request as Venue Staff see it, beside its event's details."""
    request = VenueBookingRequest(
        event_id=5,
        venue_id=2,
        requested_by=COORDINATOR_ID,
        starts_at=datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
        ends_at=datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        purpose="Main hall",
        expected_occupancy=80,
        required_layout=None,
        status=BookingRequestStatus.PENDING,
    )
    request.id = 11
    return BookingRequestAsShown(
        request=request,
        proposed_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
        start_time=time(9, 0),
        end_time=time(17, 30),
        accessibility_needs="Step-free entrance",
    )


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, shown: BookingRequestAsShown
) -> dict[str, MagicMock]:
    return replace_services(
        services,
        {"raise_booking_request": shown, "list_booking_requests_for_event": [shown]},
    )


def _call(call_route: CallRoute, endpoint: str, method: str, token: str | None) -> Any:
    return call_route(endpoint, method, PATH, {"event_id": 5}, token)


@pytest.mark.parametrize("role", NON_COORDINATOR_ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize(("endpoint", "method", "service"), ROUTES, ids=ROUTE_IDS)
def test_a_role_other_than_the_coordinator_is_refused_with_403(
    call_route: CallRoute,
    token_for: Callable[..., str],
    mock_services: dict[str, MagicMock],
    role: Role,
    endpoint: str,
    method: str,
    service: str,
) -> None:
    with pytest.raises(AuthorizationError):
        _call(call_route, endpoint, method, token_for(role=role))

    mock_services[service].assert_not_called()


@pytest.mark.parametrize(("endpoint", "method", "service"), ROUTES, ids=ROUTE_IDS)
def test_a_caller_without_a_token_is_refused_with_401(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    service: str,
) -> None:
    with pytest.raises(AuthenticationError):
        _call(call_route, endpoint, method, None)

    mock_services[service].assert_not_called()


@pytest.fixture()
def coordinator_token(token_for: Callable[..., str], make_user: Callable[..., User]) -> str:
    return token_for(make_user(role=Role.EVENT_COORDINATOR, user_id=COORDINATOR_ID))


def test_raising_a_request_returns_201_with_the_request_and_the_events_details(
    call_route: CallRoute, mock_services: dict[str, MagicMock], coordinator_token: str
) -> None:
    response, status = _call(call_route, "venue.raise_booking_request", "POST", coordinator_token)

    assert status == 201
    assert response.get_json() == {
        "id": 11,
        "event_id": 5,
        "venue_id": 2,
        "starts_at": "2026-11-01T09:00:00+08:00",
        "ends_at": "2026-11-01T12:00:00+08:00",
        "purpose": "Main hall",
        "expected_occupancy": 80,
        "required_layout": None,
        "justification": None,
        "status": "pending",
        "event_proposed_date": "2026-11-01",
        "event_end_date": "2026-11-02",
        "event_start_time": "09:00:00",
        "event_end_time": "17:30:00",
        "accessibility_needs": "Step-free entrance",
    }
    mock_services["raise_booking_request"].assert_called_once_with(
        5, {}, requested_by=COORDINATOR_ID
    )


def test_listing_requests_returns_200_with_each_request_and_the_events_details(
    call_route: CallRoute, mock_services: dict[str, MagicMock], coordinator_token: str
) -> None:
    response, status = _call(call_route, "venue.list_booking_requests", "GET", coordinator_token)

    body = response.get_json()
    assert status == 200
    assert [entry["id"] for entry in body] == [11]
    assert body[0]["accessibility_needs"] == "Step-free entrance"
    mock_services["list_booking_requests_for_event"].assert_called_once_with(
        5, coordinator_id=COORDINATOR_ID
    )


def test_a_coordinator_who_is_not_the_events_coordinator_gets_404_when_listing(
    call_route: CallRoute,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    saved_event: Callable[..., EventRequest],
) -> None:
    event = saved_event()  # assigned to coordinator 3
    other_coordinator = make_user(role=Role.EVENT_COORDINATOR, user_id=9)

    with pytest.raises(NotFoundError):
        call_route(
            "venue.list_booking_requests",
            "GET",
            f"/api/venues/events/{event.id}/booking-requests",
            {"event_id": event.id},
            token_for(other_coordinator),
        )
