"""Unit tests for SCRUM-20 "Save and resume a draft event request" — the routes.

``POST /api/events/requests/drafts``, ``PATCH .../drafts/<reference>`` and
``POST .../drafts/<reference>/submit``: Event Organisers only, the caller always
taken from their token (``g.current_user_id``), never from the body. The
*registered* view function is called inside a request context, so the real
decorators run; the service is replaced with a mock, so a refused request never
reaches it.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_20

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
MakeEventRequest = Callable[..., EventRequest]

REFERENCE = "EVR-AAAAAAAA"


class DraftRouteCase(NamedTuple):
    """One draft route: how to call it, what it calls, and what it answers with."""

    endpoint: str
    service_name: str
    method: str
    path: str
    view_kwargs: dict[str, Any]
    call_args: tuple[Any, ...]
    response_status: int
    returned_status: EventRequestStatus


#: The three draft routes (SCRUM-20 AC1, AC3). ``call_args`` is what the caller's id
#: and the parsed body look like once they reach the service: ``submit`` reads no
#: body at all.
DRAFT_ROUTES = [
    pytest.param(
        DraftRouteCase(
            endpoint="events.save_draft",
            service_name="save_draft_event_request",
            method="POST",
            path="/api/events/requests/drafts",
            view_kwargs={},
            call_args=("999", {}),
            response_status=201,
            returned_status=EventRequestStatus.DRAFT,
        ),
        id="save",
    ),
    pytest.param(
        DraftRouteCase(
            endpoint="events.update_draft",
            service_name="update_draft_event_request",
            method="PATCH",
            path=f"/api/events/requests/drafts/{REFERENCE}",
            view_kwargs={"reference": REFERENCE},
            call_args=("999", REFERENCE, {}),
            response_status=200,
            returned_status=EventRequestStatus.DRAFT,
        ),
        id="update",
    ),
    pytest.param(
        DraftRouteCase(
            endpoint="events.submit_draft",
            service_name="submit_draft_event_request",
            method="POST",
            path=f"/api/events/requests/drafts/{REFERENCE}/submit",
            view_kwargs={"reference": REFERENCE},
            call_args=("999", REFERENCE),
            response_status=200,
            returned_status=EventRequestStatus.SUBMITTED,
        ),
        id="submit",
    ),
]

draft_route_case = pytest.mark.parametrize("case", DRAFT_ROUTES)


def _replace_draft_service(
    replace_services: ReplaceServices, case: DraftRouteCase, make_event_request: MakeEventRequest
) -> MagicMock:
    """Replace ``case``'s service on ``routes`` with a mock returning its request."""
    returned = make_event_request(reference=REFERENCE, status=case.returned_status)
    return replace_services(routes, {case.service_name: returned})[case.service_name]


@draft_route_case
def test_draft_route_allows_only_event_organisers(app: Flask, case: DraftRouteCase) -> None:
    assert app.view_functions[case.endpoint].allowed_roles == frozenset({"event_organiser"})  # type: ignore[attr-defined]


@draft_route_case
def test_other_roles_cannot_use_a_draft_route(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: MakeEventRequest,
    non_organiser_role: Role,
    case: DraftRouteCase,
) -> None:
    service = _replace_draft_service(replace_services, case, make_event_request)

    with pytest.raises(AuthorizationError) as exc_info:
        call_route(
            case.endpoint,
            case.method,
            case.path,
            case.view_kwargs,
            token_for(role=non_organiser_role),
        )

    assert exc_info.value.status_code == 403
    service.assert_not_called()


@draft_route_case
def test_a_draft_route_without_a_token_is_401(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    make_event_request: MakeEventRequest,
    case: DraftRouteCase,
) -> None:
    service = _replace_draft_service(replace_services, case, make_event_request)

    with pytest.raises(AuthenticationError) as exc_info:
        call_route(case.endpoint, case.method, case.path, case.view_kwargs, None)

    assert exc_info.value.status_code == 401
    service.assert_not_called()


@draft_route_case
def test_a_draft_route_calls_its_service_with_the_callers_id(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: MakeEventRequest,
    case: DraftRouteCase,
) -> None:
    service = _replace_draft_service(replace_services, case, make_event_request)

    token = token_for(role=Role.EVENT_ORGANISER)
    response, status = call_route(case.endpoint, case.method, case.path, case.view_kwargs, token)

    assert status == case.response_status
    service.assert_called_once_with(*case.call_args)
    body = response.get_json()
    assert body["reference"] == REFERENCE
    assert body["status"] == case.returned_status.value
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
