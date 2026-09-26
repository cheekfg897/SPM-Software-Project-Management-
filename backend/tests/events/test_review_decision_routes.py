"""Unit tests for SCRUM-31 "Review and decide a submitted request": the routes.

``POST /api/events/requests/<reference>/review`` moves a submitted request to under
review (AC3); ``POST /api/events/requests/<reference>/decide`` with ``{"outcome",
"reason"}`` approves or rejects it (AC1, AC4). Both are for Event Coordinators only;
the service checks the caller is the request's own coordinator (AC5, ADR-0028). Both
answer ``200`` with the request, and never show a user id.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused request must be
stopped before it is called.
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

pytestmark = pytest.mark.scrum_31

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
#: A route under test: its endpoint, its path, and the service it calls.
Route = tuple[str, str, str]

REFERENCE = "EVR-AAAAAAAA"
VIEW_KWARGS = {"reference": REFERENCE}
REVIEW: Route = (
    "events.review_request",
    f"/api/events/requests/{REFERENCE}/review",
    "start_event_request_review",
)
DECIDE: Route = (
    "events.decide_request",
    f"/api/events/requests/{REFERENCE}/decide",
    "decide_event_request",
)
ROUTES = [REVIEW, DECIDE]
ROUTE_IDS = ["review", "decide"]


def _replace_service(
    replace_services: ReplaceServices, route: Route, returned: EventRequest
) -> MagicMock:
    """Replace the route's service with a mock returning ``returned``."""
    _, _, service = route
    return replace_services(routes, {service: returned})[service]


def _call_as(call_route: CallRoute, route: Route, token: str | None) -> Any:
    endpoint, path, _ = route
    return call_route(endpoint, "POST", path, VIEW_KWARGS, token)


# --------------------------------------------------------------------------
# AC5 — Event Coordinators only, identified by their token
# --------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_the_routes_allow_only_event_coordinators(app: Flask, route: Route) -> None:
    endpoint, _, _ = route

    assert app.view_functions[endpoint].allowed_roles == frozenset({"event_coordinator"})


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_other_roles_cannot_review_or_decide(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
    non_coordinator_role: Role,
    route: Route,
) -> None:
    service = _replace_service(replace_services, route, make_event_request())

    with pytest.raises(AuthorizationError) as exc_info:
        _call_as(call_route, route, token_for(role=non_coordinator_role))

    assert exc_info.value.status_code == 403
    service.assert_not_called()


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_reviewing_or_deciding_without_a_token_is_401(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
    route: Route,
) -> None:
    service = _replace_service(replace_services, route, make_event_request())

    with pytest.raises(AuthenticationError) as exc_info:
        _call_as(call_route, route, None)

    assert exc_info.value.status_code == 401
    service.assert_not_called()


# --------------------------------------------------------------------------
# AC3, AC4 — each answers with the request in its new status
# --------------------------------------------------------------------------


def test_review_route_returns_the_request_under_review(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
) -> None:
    reviewed = make_event_request(status=EventRequestStatus.UNDER_REVIEW, coordinator_id=3)
    service = _replace_service(replace_services, REVIEW, reviewed)

    response, status = _call_as(call_route, REVIEW, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 200
    # The caller is the coordinator, taken from their token; the body is not read.
    service.assert_called_once_with("999", REFERENCE)
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "under_review")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)


def test_decide_route_returns_the_decided_request(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
) -> None:
    decided = make_event_request(status=EventRequestStatus.APPROVED, coordinator_id=3)
    service = _replace_service(replace_services, DECIDE, decided)

    response, status = _call_as(call_route, DECIDE, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 200
    # The caller is the coordinator, taken from their token; the body is passed on.
    service.assert_called_once_with("999", REFERENCE, {})
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "approved")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
