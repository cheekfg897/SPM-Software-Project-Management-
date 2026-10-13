"""Unit tests for SCRUM-96's two Lead-only list routes (AC1, AC2, AC3).

``GET /api/events/requests/active`` lists every active event with its coordinator and
status, and ``GET /api/events/coordinators/workload`` lists each coordinator with their
active events. Only the Event Coordinator Lead may call either: an Event Coordinator
is refused by ``@requires_role``, with the service never reached. As in
``test_lead_assignment_permissions.py``, the registered view runs inside a request
context with the service replaced by a mock.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import ActiveRequest, CoordinatorWorkload
from tests.events.conftest import NON_LEAD_ROLES

pytestmark = pytest.mark.scrum_96

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

#: Each route as ``(endpoint, path, service it calls)``.
ROUTES = {
    "active": ("events.list_active", "/api/events/requests/active", "list_active_requests"),
    "workload": (
        "events.list_coordinator_workload",
        "/api/events/coordinators/workload",
        "list_requests_for_each_coordinator",
    ),
}


@pytest.fixture(params=sorted(ROUTES), ids=str)
def lead_route(request: pytest.FixtureRequest) -> tuple[str, str, str]:
    """Each of the Lead's two list routes in turn."""
    return ROUTES[request.param]


@pytest.fixture()
def held_event(make_event_request: Callable[..., EventRequest]) -> EventRequest:
    """An approved event held by coordinator 3, as the services would return it."""
    return make_event_request(status=EventRequestStatus.APPROVED, coordinator_id=3)


@pytest.fixture()
def listing_services(
    replace_services: ReplaceServices, held_event: EventRequest
) -> dict[str, MagicMock]:
    """Replace both services so each returns the one held event."""
    return replace_services(
        routes,
        {
            "list_active_requests": [ActiveRequest(held_event, "Coordinator Three")],
            "list_requests_for_each_coordinator": [
                CoordinatorWorkload(3, "Coordinator Three", [held_event])
            ],
        },
    )


def test_both_routes_allow_only_the_event_coordinator_lead(app: Flask) -> None:
    allowed = {app.view_functions[endpoint].allowed_roles for endpoint, _, _ in ROUTES.values()}

    assert allowed == {frozenset({Role.EVENT_COORDINATOR_LEAD.value})}


@pytest.mark.parametrize("role", NON_LEAD_ROLES, ids=lambda role: role.value)
def test_every_other_role_is_refused_by_both_routes(
    call_route: CallRoute,
    token_for: Callable[..., str],
    listing_services: dict[str, MagicMock],
    lead_route: tuple[str, str, str],
    role: Role,
) -> None:
    """Covers the Event Coordinator (AC3), among the rest."""
    endpoint, path, _ = lead_route

    with pytest.raises(AuthorizationError) as exc_info:
        call_route(endpoint, "GET", path, {}, token_for(role=role))

    assert exc_info.value.status_code == 403
    for service in listing_services.values():
        service.assert_not_called()


def test_a_call_without_a_token_is_401(
    call_route: CallRoute, listing_services: dict[str, MagicMock], lead_route: tuple[str, str, str]
) -> None:
    endpoint, path, _ = lead_route

    with pytest.raises(AuthenticationError) as exc_info:
        call_route(endpoint, "GET", path, {}, None)

    assert exc_info.value.status_code == 401
    for service in listing_services.values():
        service.assert_not_called()


def test_the_new_paths_are_not_taken_for_a_reference(
    app: Flask, lead_route: tuple[str, str, str]
) -> None:
    """``/requests/active`` must reach its own view, not ``/requests/<reference>``."""
    endpoint, path, _ = lead_route
    adapter = app.url_map.bind("localhost")

    assert adapter.match(path) == (endpoint, {})


def test_the_lead_sees_each_active_event_with_its_status_and_coordinator(
    call_route: CallRoute, token_for: Callable[..., str], listing_services: dict[str, MagicMock]
) -> None:
    endpoint, path, _ = ROUTES["active"]

    response, status = call_route(
        endpoint, "GET", path, {}, token_for(role=Role.EVENT_COORDINATOR_LEAD)
    )

    assert status == 200
    listing_services["list_active_requests"].assert_called_once_with()
    assert response.get_json() == {
        "event_requests": [
            {
                "reference": "EVR-AAAAAAAA",
                "name": "Partner Summit",
                "proposed_date": "2026-10-15",
                "end_date": "2026-10-15",
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "status": "approved",
                "coordinator": "Coordinator Three",
            }
        ]
    }


def test_an_event_nobody_holds_yet_shows_no_coordinator(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
) -> None:
    replace_services(routes, {"list_active_requests": [ActiveRequest(make_event_request(), None)]})
    endpoint, path, _ = ROUTES["active"]

    response, _ = call_route(endpoint, "GET", path, {}, token_for(role=Role.EVENT_COORDINATOR_LEAD))

    assert response.get_json()["event_requests"][0]["coordinator"] is None


def test_the_lead_sees_each_coordinator_with_their_events_and_no_user_id(
    call_route: CallRoute, token_for: Callable[..., str], listing_services: dict[str, MagicMock]
) -> None:
    endpoint, path, _ = ROUTES["workload"]

    response, status = call_route(
        endpoint, "GET", path, {}, token_for(role=Role.EVENT_COORDINATOR_LEAD)
    )

    assert status == 200
    listing_services["list_requests_for_each_coordinator"].assert_called_once_with()
    (coordinator,) = response.get_json()["coordinators"]
    assert set(coordinator) == {"coordinator", "event_requests"}
    assert coordinator["coordinator"] == "Coordinator Three"
    assert [event["reference"] for event in coordinator["event_requests"]] == ["EVR-AAAAAAAA"]
    assert coordinator["event_requests"][0]["status"] == "approved"


@pytest.mark.parametrize(
    ("route", "list_name", "message"),
    [
        ("active", "event_requests", "There are no active event requests."),
        ("workload", "coordinators", "No coordinator has an active event request."),
    ],
)
def test_an_empty_list_says_so(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    route: str,
    list_name: str,
    message: str,
) -> None:
    endpoint, path, service = ROUTES[route]
    replace_services(routes, {service: []})

    response, status = call_route(
        endpoint, "GET", path, {}, token_for(role=Role.EVENT_COORDINATOR_LEAD)
    )

    assert status == 200
    assert response.get_json() == {list_name: [], "message": message}
