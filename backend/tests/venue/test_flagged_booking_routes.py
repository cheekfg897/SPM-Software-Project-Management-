"""Unit tests for SCRUM-59's routes: who may list, reconfirm and reject flagged ones.

Only Venue Staff may call them, any of them: staff are not assigned to particular
venues (ADR-0035 decision 1). The registered view functions run inside a request
context, so the real decorators decide; a refused caller never reaches the service.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.venue import services
from app.modules.venue.schemas import (
    BookingRequestAsShown,
    FlaggedBookingAsShown,
    Reconfirmation,
)
from tests.venue.conftest import VENUE_STAFF_ID

pytestmark = pytest.mark.scrum_59

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

#: Every role but Venue Staff, built from the enum so a role added later is refused too.
REFUSED_ROLES = sorted(set(Role) - {Role.VENUE_STAFF}, key=lambda role: role.value)

REQUEST_ID = 11
FLAGGED_PATH = "/api/venues/booking-requests/flagged"
RECONFIRM_PATH = f"/api/venues/booking-requests/{REQUEST_ID}/reconfirm"
REJECT_PATH = f"/api/venues/booking-requests/{REQUEST_ID}/reject"
# (endpoint, HTTP method, path, view kwargs, the service function it calls)
ROUTES = [
    ("venue.list_flagged_bookings", "GET", FLAGGED_PATH, {}, "list_flagged_bookings"),
    (
        "venue.reconfirm_flagged_booking",
        "POST",
        RECONFIRM_PATH,
        {"request_id": REQUEST_ID},
        "reconfirm_flagged_booking",
    ),
    (
        "venue.reject_flagged_booking",
        "POST",
        REJECT_PATH,
        {"request_id": REQUEST_ID},
        "reject_flagged_booking",
    ),
]
ROUTE_IDS = [route[0] for route in ROUTES]


@pytest.fixture()
def flagged(shown: BookingRequestAsShown) -> FlaggedBookingAsShown:
    """The ``shown`` request, listed as flagged, to be moved to 2 November."""
    reconfirmation = Reconfirmation(
        starts_at=datetime(2026, 11, 2, 1, 0, tzinfo=UTC),
        ends_at=datetime(2026, 11, 2, 4, 0, tzinfo=UTC),
        expected_occupancy=90,
    )
    return FlaggedBookingAsShown(shown=shown, reconfirm_with=reconfirmation)


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, flagged: FlaggedBookingAsShown
) -> dict[str, MagicMock]:
    return replace_services(
        services,
        {
            "list_flagged_bookings": [flagged],
            "reconfirm_flagged_booking": flagged.shown,
            "reject_flagged_booking": flagged.shown,
        },
    )


@pytest.fixture()
def venue_staff_token(token_for: Callable[..., str], make_user: Callable[..., User]) -> str:
    return token_for(make_user(role=Role.VENUE_STAFF, user_id=VENUE_STAFF_ID))


@pytest.mark.parametrize("endpoint", ROUTE_IDS)
def test_each_route_allows_only_venue_staff(app: Flask, endpoint: str) -> None:
    """Guards against a later edit widening the allow-list by accident."""
    assert app.view_functions[endpoint].allowed_roles == frozenset({Role.VENUE_STAFF.value})


def test_the_refused_roles_and_venue_staff_are_every_role() -> None:
    assert {*REFUSED_ROLES, Role.VENUE_STAFF} == set(Role)
    assert Role.VENUE_STAFF not in REFUSED_ROLES


@pytest.mark.parametrize("role", REFUSED_ROLES, ids=lambda role: role.value)
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


def test_the_flagged_list_returns_200_with_each_booking_and_its_reconfirmation(
    call_route: CallRoute, mock_services: dict[str, MagicMock], venue_staff_token: str
) -> None:
    response, status = call_route(
        "venue.list_flagged_bookings", "GET", FLAGGED_PATH, {}, venue_staff_token
    )

    body = response.get_json()
    assert status == 200
    assert [entry["booking"]["id"] for entry in body] == [REQUEST_ID]
    assert body[0]["reconfirm_with"] == {
        "starts_at": "2026-11-02T09:00:00+08:00",
        "ends_at": "2026-11-02T12:00:00+08:00",
        "expected_occupancy": 90,
    }
    mock_services["list_flagged_bookings"].assert_called_once_with()


def test_reconfirming_passes_the_body_and_the_caller_on_and_returns_200(
    call_route: CallRoute, mock_services: dict[str, MagicMock], venue_staff_token: str
) -> None:
    body = {"starts_at": "2026-11-02T09:00:00+08:00", "ends_at": "2026-11-02T12:00:00+08:00"}

    response, status = call_route(
        "venue.reconfirm_flagged_booking",
        "POST",
        RECONFIRM_PATH,
        {"request_id": REQUEST_ID},
        venue_staff_token,
        body=body,
    )

    assert status == 200
    assert response.get_json()["id"] == REQUEST_ID
    mock_services["reconfirm_flagged_booking"].assert_called_once_with(
        REQUEST_ID, body, reconfirmed_by=VENUE_STAFF_ID
    )


def test_rejecting_passes_the_body_and_the_caller_on_and_returns_200(
    call_route: CallRoute, mock_services: dict[str, MagicMock], venue_staff_token: str
) -> None:
    body = {"reason": "The hall is booked for exams that day."}

    response, status = call_route(
        "venue.reject_flagged_booking",
        "POST",
        REJECT_PATH,
        {"request_id": REQUEST_ID},
        venue_staff_token,
        body=body,
    )

    assert status == 200
    assert response.get_json()["id"] == REQUEST_ID
    mock_services["reject_flagged_booking"].assert_called_once_with(
        REQUEST_ID, body, rejected_by=VENUE_STAFF_ID
    )
