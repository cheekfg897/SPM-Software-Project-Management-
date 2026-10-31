"""Unit tests for SCRUM-42 — who may raise and list venue booking requests.

Only the Event Coordinator may call either route. The registered view functions run
inside a request context, so the real decorators decide; a refused caller must never
reach the service layer. A coordinator who isn't assigned to the event is refused by
the real service, which the listing route passes on as a 404.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events.models import EventRequest
from app.modules.venue import services
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import COORDINATOR_ID

pytestmark = pytest.mark.scrum_42

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

NON_COORDINATOR_ROLES = sorted(ALL_ROLES - {Role.EVENT_COORDINATOR}, key=lambda r: r.value)

REFERENCE = "EVR-ABCD2345"
PATH = f"/api/venues/events/{REFERENCE}/booking-requests"
# (endpoint, HTTP method, the service function it calls)
ROUTES = [
    ("venue.raise_booking_request", "POST", "raise_booking_request"),
    ("venue.list_booking_requests", "GET", "list_booking_requests_for_event"),
    ("venue.withdraw_arrangement", "POST", "withdraw_arrangement"),
    ("venue.cancel_all_arrangements", "POST", "cancel_all_arrangements"),
    ("venue.change_arrangement", "PATCH", "change_arrangement"),
]
ROUTE_IDS = [route[0] for route in ROUTES]


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, shown: BookingRequestAsShown
) -> dict[str, MagicMock]:
    return replace_services(
        services,
        {
            "raise_booking_request": shown,
            "list_booking_requests_for_event": [shown],
            "withdraw_arrangement": shown,
            "cancel_all_arrangements": [shown],
            "change_arrangement": shown,
        },
    )


def _call(call_route: CallRoute, endpoint: str, method: str, token: str | None) -> Any:
    return call_route(endpoint, method, PATH, {"reference": REFERENCE}, token)


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
        "decision_reason": None,
        "suggested_venue_id": None,
        "suggested_starts_at": None,
        "suggested_ends_at": None,
        "preparation_status": None,
        "preparation_notes": None,
        "hold_expires_at": None,
        "needs_alternative_venue": False,
        "unavailability": [],
        "replaces_request_id": None,
        "flagged_after_change": False,
        "reassessment_flags": [],
        "event_proposed_date": "2026-11-01",
        "event_end_date": "2026-11-02",
        "event_start_time": "09:00:00",
        "event_end_time": "17:30:00",
        "accessibility_needs": "Step-free entrance",
    }
    mock_services["raise_booking_request"].assert_called_once_with(
        REFERENCE, {}, requested_by=COORDINATOR_ID
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
        REFERENCE, coordinator_id=COORDINATOR_ID
    )


@pytest.mark.scrum_93
def test_withdrawing_an_arrangement_returns_200_with_the_withdrawn_request(
    call_route: CallRoute, mock_services: dict[str, MagicMock], coordinator_token: str
) -> None:
    response, status = call_route(
        "venue.withdraw_arrangement",
        "POST",
        f"{PATH}/11/withdraw",
        {"reference": REFERENCE, "arrangement_id": 11},
        coordinator_token,
    )

    assert status == 200
    assert response.get_json()["id"] == 11
    mock_services["withdraw_arrangement"].assert_called_once_with(
        REFERENCE, 11, coordinator_id=COORDINATOR_ID
    )


@pytest.mark.scrum_93
def test_cancelling_all_arrangements_returns_200_with_each_retired_request(
    call_route: CallRoute, mock_services: dict[str, MagicMock], coordinator_token: str
) -> None:
    response, status = _call(call_route, "venue.cancel_all_arrangements", "POST", coordinator_token)

    assert status == 200
    assert [entry["id"] for entry in response.get_json()] == [11]
    mock_services["cancel_all_arrangements"].assert_called_once_with(
        REFERENCE, coordinator_id=COORDINATOR_ID
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
            f"/api/venues/events/{event.reference}/booking-requests",
            {"reference": event.reference},
            token_for(other_coordinator),
        )


@pytest.mark.scrum_93
def test_changing_an_arrangement_returns_200_with_the_changed_request(
    call_route: CallRoute, mock_services: dict[str, MagicMock], coordinator_token: str
) -> None:
    response, status = call_route(
        "venue.change_arrangement",
        "PATCH",
        f"{PATH}/11",
        {"reference": REFERENCE, "arrangement_id": 11},
        coordinator_token,
    )

    assert status == 200
    assert response.get_json()["id"] == 11
    mock_services["change_arrangement"].assert_called_once_with(
        REFERENCE, 11, {}, coordinator_id=COORDINATOR_ID
    )
