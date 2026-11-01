"""Unit tests for SCRUM-56 "Request a change after submitting my event": the routes.

``POST /api/events/requests/<reference>/change-requests`` raises a change request
(AC1, AC2), answering ``201``; ``POST .../change-requests/<id>/withdraw`` withdraws one
(AC8), answering ``200``. Both are for Event Organisers only, so every other role is
refused before the service runs (AC6); the service checks the caller is the event's
own Organiser. The Organiser still can't edit the event directly (AC3): the edit route
is the coordinator's.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused request must be stopped
before it is called.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import ChangeRequestStatus, EventRequest
from app.modules.events.services import ChangeRequestAsShown, EventEdit, RequestedChange

pytestmark = pytest.mark.scrum_56

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
CHANGE_REQUEST_ID = 4
BODY = {"expected_attendance": 300, "reason": "More partners are coming."}

SHOWN = ChangeRequestAsShown(
    id=CHANGE_REQUEST_ID,
    status=ChangeRequestStatus.PENDING,
    changes=(RequestedChange("expected_attendance", 250, 300),),
    reason="More partners are coming.",
    raised_by="Alice Example",
    raised_at=datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc),
    withdrawn_at=None,
    withdrawal_note=None,
)
SHOWN_BODY = {
    "id": CHANGE_REQUEST_ID,
    "status": "pending",
    "changes": [{"field": "expected_attendance", "previous_value": 250, "requested_value": 300}],
    "reason": "More partners are coming.",
    "raised_by": "Alice Example",
    "raised_at": "2026-09-15T09:00:00+08:00",
    "withdrawn_at": None,
    "withdrawal_note": None,
}


class ChangeRequestRouteCase(NamedTuple):
    """One change request route: its path, the service it calls, and its status."""

    endpoint: str
    path: str
    view_kwargs: dict[str, Any]
    service_name: str
    #: What the service is called with after the caller's id.
    service_args: tuple[Any, ...]
    status: int


CHANGE_REQUEST_ROUTES = [
    pytest.param(
        ChangeRequestRouteCase(
            endpoint="events.raise_change",
            path=f"/api/events/requests/{REFERENCE}/change-requests",
            view_kwargs={"reference": REFERENCE},
            service_name="raise_change_request",
            service_args=(REFERENCE, BODY),
            status=201,
        ),
        id="raise",
    ),
    pytest.param(
        ChangeRequestRouteCase(
            endpoint="events.withdraw_change",
            path=f"/api/events/requests/{REFERENCE}/change-requests/{CHANGE_REQUEST_ID}/withdraw",
            view_kwargs={"reference": REFERENCE, "change_request_id": CHANGE_REQUEST_ID},
            service_name="withdraw_change_request",
            service_args=(REFERENCE, CHANGE_REQUEST_ID),
            status=200,
        ),
        id="withdraw",
    ),
]

change_request_route_case = pytest.mark.parametrize("case", CHANGE_REQUEST_ROUTES)


def _replace_service(replace_services: ReplaceServices, case: ChangeRequestRouteCase) -> MagicMock:
    return replace_services(routes, {case.service_name: SHOWN})[case.service_name]


def _call(call_route: CallRoute, case: ChangeRequestRouteCase, token: str | None) -> Any:
    return call_route(case.endpoint, "POST", case.path, case.view_kwargs, token, body=BODY)


@change_request_route_case
def test_each_route_allows_only_event_organisers(app: Flask, case: ChangeRequestRouteCase) -> None:
    allowed_roles = app.view_functions[case.endpoint].allowed_roles  # type: ignore[attr-defined]

    assert allowed_roles == frozenset({Role.EVENT_ORGANISER.value})


@change_request_route_case
def test_every_other_role_is_refused(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    case: ChangeRequestRouteCase,
) -> None:
    service = _replace_service(replace_services, case)

    for role in ALL_ROLES - {Role.EVENT_ORGANISER}:
        with pytest.raises(AuthorizationError) as exc_info:
            _call(call_route, case, token_for(role=role))

        assert exc_info.value.status_code == 403
    service.assert_not_called()


@change_request_route_case
def test_calling_a_route_without_a_token_is_401(
    call_route: CallRoute, replace_services: ReplaceServices, case: ChangeRequestRouteCase
) -> None:
    service = _replace_service(replace_services, case)

    with pytest.raises(AuthenticationError) as exc_info:
        _call(call_route, case, None)

    assert exc_info.value.status_code == 401
    service.assert_not_called()


@change_request_route_case
def test_a_route_passes_the_caller_on_and_returns_the_change_request(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    case: ChangeRequestRouteCase,
) -> None:
    service = _replace_service(replace_services, case)

    response, status = _call(call_route, case, token_for(role=Role.EVENT_ORGANISER))

    assert status == case.status
    # The caller comes from their token, never from the body.
    service.assert_called_once_with("999", *case.service_args)
    assert response.get_json() == SHOWN_BODY


def test_the_organiser_still_cannot_edit_the_event_directly(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
) -> None:
    """AC3: the event's own edit route is the coordinator's alone."""
    # A real edit to return, so letting the organiser in would answer 200 rather than
    # fail on the stub.
    edited = EventEdit(make_event_request(), [])
    edit = replace_services(routes, {"update_event_request": edited})["update_event_request"]

    with pytest.raises(AuthorizationError):
        call_route(
            "events.update_request",
            "PATCH",
            f"/api/events/requests/{REFERENCE}",
            {"reference": REFERENCE},
            token_for(role=Role.EVENT_ORGANISER),
            body={"expected_attendance": 300},
        )

    edit.assert_not_called()
