"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": the routes.

``POST /api/events/requests/<reference>/request-clarification`` with ``{"message"}``
sends a request under review back to its organiser (AC1): Event Coordinators only,
and the service checks the caller is the request's own coordinator.
``POST /api/events/requests/<reference>/resubmit`` with ``{"response", ...}`` answers
and resubmits it (AC2): Event Organisers only, and the service checks the request is
their organisation's (ADR-0029). Both answer ``200`` with the request, and never show
a user id.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused request must be
stopped before it is called.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_32

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
MakeEventRequest = Callable[..., EventRequest]

REFERENCE = "EVR-AAAAAAAA"
VIEW_KWARGS = {"reference": REFERENCE}


class ClarificationRouteCase(NamedTuple):
    """One clarification route: who may call it, what it calls, and what it returns."""

    endpoint: str
    path: str
    service_name: str
    allowed_role: Role
    returned_status: EventRequestStatus


#: The clarification routes (SCRUM-32 AC1, AC2). Each passes the caller's id from their
#: token, the reference and the body to its service.
CLARIFICATION_ROUTES = [
    pytest.param(
        ClarificationRouteCase(
            endpoint="events.ask_for_clarification",
            path=f"/api/events/requests/{REFERENCE}/request-clarification",
            service_name="request_clarification",
            allowed_role=Role.EVENT_COORDINATOR,
            returned_status=EventRequestStatus.AWAITING_CLARIFICATION,
        ),
        id="request-clarification",
    ),
    pytest.param(
        ClarificationRouteCase(
            endpoint="events.resubmit_request",
            path=f"/api/events/requests/{REFERENCE}/resubmit",
            service_name="resubmit_event_request",
            allowed_role=Role.EVENT_ORGANISER,
            returned_status=EventRequestStatus.UNDER_REVIEW,
        ),
        id="resubmit",
    ),
]

clarification_route_case = pytest.mark.parametrize("case", CLARIFICATION_ROUTES)


def _replace_service(
    replace_services: ReplaceServices,
    case: ClarificationRouteCase,
    make_event_request: MakeEventRequest,
) -> MagicMock:
    """Replace ``case``'s service on ``routes`` with a mock returning its request."""
    returned = make_event_request(status=case.returned_status, coordinator_id=3)
    return replace_services(routes, {case.service_name: returned})[case.service_name]


def _call(call_route: CallRoute, case: ClarificationRouteCase, token: str | None) -> Any:
    return call_route(case.endpoint, "POST", case.path, VIEW_KWARGS, token)


@clarification_route_case
def test_each_route_allows_only_its_role(app: Flask, case: ClarificationRouteCase) -> None:
    allowed_roles = app.view_functions[case.endpoint].allowed_roles  # type: ignore[attr-defined]

    assert allowed_roles == frozenset({case.allowed_role.value})


@clarification_route_case
def test_every_other_role_is_refused(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: MakeEventRequest,
    case: ClarificationRouteCase,
) -> None:
    service = _replace_service(replace_services, case, make_event_request)

    for role in ALL_ROLES - {case.allowed_role}:
        with pytest.raises(AuthorizationError) as exc_info:
            _call(call_route, case, token_for(role=role))

        assert exc_info.value.status_code == 403
    service.assert_not_called()


@clarification_route_case
def test_calling_a_route_without_a_token_is_401(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    make_event_request: MakeEventRequest,
    case: ClarificationRouteCase,
) -> None:
    service = _replace_service(replace_services, case, make_event_request)

    with pytest.raises(AuthenticationError) as exc_info:
        _call(call_route, case, None)

    assert exc_info.value.status_code == 401
    service.assert_not_called()


@clarification_route_case
def test_a_route_returns_the_request_in_its_new_status(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: MakeEventRequest,
    case: ClarificationRouteCase,
) -> None:
    service = _replace_service(replace_services, case, make_event_request)

    response, status = _call(call_route, case, token_for(role=case.allowed_role))

    assert status == 200
    # The caller comes from their token; the body is passed on as it arrived.
    service.assert_called_once_with("999", REFERENCE, {})
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, case.returned_status.value)
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
