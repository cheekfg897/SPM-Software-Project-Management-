"""Unit tests for SCRUM-43 and SCRUM-75 — who may read the queue, decide and hold.

Only Venue Staff may call any of these routes, any of them: staff are not assigned to
particular venues (ADR-0035 decision 1). The registered view functions run inside a
request context, so the real decorators decide; a refused caller must never reach the
service layer. ADR-0035 decision 13 left Venue Staff without a read route; these are
the routes that give them one. SCRUM-75 adds the two that place a hold and change its
expiry.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import VENUE_STAFF_ID

pytestmark = [pytest.mark.scrum_43, pytest.mark.scrum_75]

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

NON_VENUE_STAFF_ROLES = sorted(ALL_ROLES - {Role.VENUE_STAFF}, key=lambda role: role.value)

REQUEST_ID = 11
QUEUE_PATH = "/api/venues/booking-requests"
DECISION_PATH = f"{QUEUE_PATH}/{REQUEST_ID}/decision"
HOLD_PATH = f"{QUEUE_PATH}/{REQUEST_ID}/hold"
# (endpoint, HTTP method, path, view kwargs, the service function it calls)
HOLD_ROUTES = [
    (
        "venue.place_booking_hold",
        "POST",
        HOLD_PATH,
        {"request_id": REQUEST_ID},
        "place_booking_hold",
    ),
    (
        "venue.change_hold_expiry",
        "PATCH",
        HOLD_PATH,
        {"request_id": REQUEST_ID},
        "change_hold_expiry",
    ),
]
ROUTES = [
    ("venue.list_pending_booking_requests", "GET", QUEUE_PATH, {}, "list_pending_booking_requests"),
    (
        "venue.decide_booking_request",
        "POST",
        DECISION_PATH,
        {"request_id": REQUEST_ID},
        "decide_booking_request",
    ),
    *HOLD_ROUTES,
]
ROUTE_IDS = [route[0] for route in ROUTES]


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, shown: BookingRequestAsShown
) -> dict[str, MagicMock]:
    return replace_services(
        services,
        {
            "list_pending_booking_requests": [shown],
            "decide_booking_request": shown,
            "place_booking_hold": shown,
            "change_hold_expiry": shown,
        },
    )


@pytest.fixture()
def venue_staff_token(token_for: Callable[..., str], make_user: Callable[..., User]) -> str:
    return token_for(make_user(role=Role.VENUE_STAFF, user_id=VENUE_STAFF_ID))


@pytest.mark.parametrize("role", NON_VENUE_STAFF_ROLES, ids=lambda role: role.value)
@pytest.mark.parametrize(
    ("endpoint", "method", "path", "view_kwargs", "service"), ROUTES, ids=ROUTE_IDS
)
def test_a_role_other_than_venue_staff_is_refused_with_403(
    call_route: CallRoute,
    token_for: Callable[..., str],
    mock_services: dict[str, MagicMock],
    role: Role,
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
) -> None:
    with pytest.raises(AuthorizationError):
        call_route(endpoint, method, path, view_kwargs, token_for(role=role))

    mock_services[service].assert_not_called()


@pytest.mark.parametrize(
    ("endpoint", "method", "path", "view_kwargs", "service"), ROUTES, ids=ROUTE_IDS
)
def test_a_caller_without_a_token_is_refused_with_401(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
) -> None:
    with pytest.raises(AuthenticationError):
        call_route(endpoint, method, path, view_kwargs, None)

    mock_services[service].assert_not_called()


def test_the_queue_returns_200_with_each_waiting_request(
    call_route: CallRoute, mock_services: dict[str, MagicMock], venue_staff_token: str
) -> None:
    response, status = call_route(
        "venue.list_pending_booking_requests", "GET", QUEUE_PATH, {}, venue_staff_token
    )

    body = response.get_json()
    assert status == 200
    assert [entry["id"] for entry in body] == [REQUEST_ID]
    assert body[0]["accessibility_needs"] == "Step-free entrance"
    mock_services["list_pending_booking_requests"].assert_called_once_with()


def test_deciding_returns_200_with_the_decided_request(
    call_route: CallRoute, mock_services: dict[str, MagicMock], venue_staff_token: str
) -> None:
    """``call_route`` sends ``{}`` as the body; the service checks what is in it."""
    response, status = call_route(
        "venue.decide_booking_request",
        "POST",
        DECISION_PATH,
        {"request_id": REQUEST_ID},
        venue_staff_token,
    )

    assert status == 200
    assert response.get_json()["id"] == REQUEST_ID
    mock_services["decide_booking_request"].assert_called_once_with(
        REQUEST_ID, {}, decided_by=VENUE_STAFF_ID
    )


@pytest.mark.parametrize(
    ("endpoint", "method", "path", "view_kwargs", "service"),
    HOLD_ROUTES,
    ids=[route[0] for route in HOLD_ROUTES],
)
def test_venue_staff_placing_or_changing_a_hold_gets_200_with_the_request(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    venue_staff_token: str,
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
) -> None:
    response, status = call_route(endpoint, method, path, view_kwargs, venue_staff_token)

    assert status == 200
    assert response.get_json()["id"] == REQUEST_ID
    mock_services[service].assert_called_once_with(REQUEST_ID, {})
