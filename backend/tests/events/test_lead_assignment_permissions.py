"""Unit tests for SCRUM-95's two routes and who may call them: the Lead only (AC2, AC6).

``GET /api/events/requests/unassigned`` is the Lead's queue and
``POST /api/events/requests/<reference>/coordinator`` is the Lead giving a request to
a coordinator (ADR-0036). AC6 is a permission rule, not a presentation one: an Event
Coordinator who calls either endpoint directly is refused by ``@requires_role``, not
merely shown no button. So these tests call the *registered* view function inside a
request context, where the real decorator runs, with the service replaced by a mock
that a refused call must never reach.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EventRequest
from app.modules.events.services import CoordinatorContact

pytestmark = pytest.mark.scrum_95

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
LIST_ENDPOINT = "events.list_unassigned"
LIST_PATH = "/api/events/requests/unassigned"
ASSIGN_ENDPOINT = "events.assign_coordinator"
ASSIGN_PATH = f"/api/events/requests/{REFERENCE}/coordinator"
ASSIGN_KWARGS = {"reference": REFERENCE}

#: Every role but the Lead, so a role added later is refused unless a test says not.
NON_LEAD_ROLES = sorted(ALL_ROLES - {Role.EVENT_COORDINATOR_LEAD}, key=lambda role: role.value)

#: Each route as ``(endpoint, method, path, view kwargs)``.
ROUTES = {
    "list": (LIST_ENDPOINT, "GET", LIST_PATH, {}),
    "assign": (ASSIGN_ENDPOINT, "POST", ASSIGN_PATH, ASSIGN_KWARGS),
}


@pytest.fixture(params=sorted(ROUTES), ids=str)
def lead_route(request: pytest.FixtureRequest) -> tuple[str, str, str, dict[str, Any]]:
    """Each of the Lead's two routes in turn."""
    return ROUTES[request.param]


@pytest.fixture()
def lead_services(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> dict[str, MagicMock]:
    """Replace both services: the queue holds one request; assigning gives it to 9."""
    assigned = make_event_request(coordinator_id=9)
    contact = CoordinatorContact(full_name="Coordinator Nine", email="coordinator9@example.com")
    return replace_services(
        routes,
        {
            "list_unassigned_requests": [make_event_request()],
            "assign_coordinator_to_request": (assigned, contact),
        },
    )


def test_both_routes_allow_only_the_event_coordinator_lead(app: Flask) -> None:
    allowed = {app.view_functions[endpoint].allowed_roles for endpoint, *_ in ROUTES.values()}

    assert allowed == {frozenset({"event_coordinator_lead"})}


@pytest.mark.parametrize("role", NON_LEAD_ROLES, ids=lambda role: role.value)
def test_every_other_role_is_refused_by_both_routes(
    call_route: CallRoute,
    token_for: Callable[..., str],
    lead_services: dict[str, MagicMock],
    lead_route: tuple[str, str, str, dict[str, Any]],
    role: Role,
) -> None:
    """Covers the Event Coordinator (AC6) and the Event Organiser, among the rest."""
    endpoint, method, path, view_kwargs = lead_route

    with pytest.raises(AuthorizationError) as exc_info:
        call_route(endpoint, method, path, view_kwargs, token_for(role=role))

    assert exc_info.value.status_code == 403
    for service in lead_services.values():
        service.assert_not_called()


def test_a_call_without_a_token_is_401(
    call_route: CallRoute,
    lead_services: dict[str, MagicMock],
    lead_route: tuple[str, str, str, dict[str, Any]],
) -> None:
    endpoint, method, path, view_kwargs = lead_route

    with pytest.raises(AuthenticationError) as exc_info:
        call_route(endpoint, method, path, view_kwargs, None)

    assert exc_info.value.status_code == 401
    for service in lead_services.values():
        service.assert_not_called()


def test_the_lead_sees_the_queue_as_the_ac2_fields_only(
    call_route: CallRoute, token_for: Callable[..., str], lead_services: dict[str, MagicMock]
) -> None:
    response, status = call_route(
        LIST_ENDPOINT, "GET", LIST_PATH, {}, token_for(role=Role.EVENT_COORDINATOR_LEAD)
    )

    assert status == 200
    lead_services["list_unassigned_requests"].assert_called_once_with()
    queue = response.get_json()["event_requests"]
    assert len(queue) == 1
    assert set(queue[0]) == {
        "name",
        "proposed_date",
        "start_time",
        "end_time",
        "expected_attendance",
        "submitted_at",
    }
    assert queue[0]["name"] == "Partner Summit"


def test_an_empty_queue_says_so(
    call_route: CallRoute, token_for: Callable[..., str], replace_services: ReplaceServices
) -> None:
    replace_services(routes, {"list_unassigned_requests": []})

    response, status = call_route(
        LIST_ENDPOINT, "GET", LIST_PATH, {}, token_for(role=Role.EVENT_COORDINATOR_LEAD)
    )

    assert status == 200
    assert response.get_json() == {
        "event_requests": [],
        "message": "No event requests are waiting to be assigned.",
    }


def test_the_lead_assigns_and_is_recorded_from_their_token(
    call_route: CallRoute, token_for: Callable[..., str], lead_services: dict[str, MagicMock]
) -> None:
    response, status = call_route(
        ASSIGN_ENDPOINT,
        "POST",
        ASSIGN_PATH,
        ASSIGN_KWARGS,
        token_for(role=Role.EVENT_COORDINATOR_LEAD),
    )

    assert status == 200
    # The Lead is the caller, from their token, as an int; the body goes on as sent.
    lead_services["assign_coordinator_to_request"].assert_called_once_with(
        REFERENCE, {}, assigned_by=999
    )
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "submitted")
    assert body["coordinator"] == {
        "full_name": "Coordinator Nine",
        "email": "coordinator9@example.com",
    }
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
