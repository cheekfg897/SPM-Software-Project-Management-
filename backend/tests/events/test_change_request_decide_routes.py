"""Unit tests for SCRUM-57 "Review and decide a change request": the route.

``POST /api/events/requests/<reference>/change-requests/<id>/decide`` approves or
rejects a change request, answering ``200`` with it. It is for Event Coordinators only,
so every other role is refused before the service runs; the service checks the caller
is the event's assigned coordinator (ADR-0127).

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused request must be stopped
before it is called.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import ChangeRequestStatus
from app.modules.events.services import ChangeRequestAsShown, RequestedChange

pytestmark = pytest.mark.scrum_57

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

ENDPOINT = "events.decide_change"
REFERENCE = "EVR-AAAAAAAA"
CHANGE_REQUEST_ID = 4
PATH = f"/api/events/requests/{REFERENCE}/change-requests/{CHANGE_REQUEST_ID}/decide"
VIEW_KWARGS = {"reference": REFERENCE, "change_request_id": CHANGE_REQUEST_ID}
BODY = {"outcome": "approved", "reason": "The hall holds 300."}

DECIDED = ChangeRequestAsShown(
    id=CHANGE_REQUEST_ID,
    status=ChangeRequestStatus.APPROVED,
    changes=(RequestedChange("expected_attendance", 250, 300),),
    reason="More partners are coming.",
    raised_by="Alice Example",
    raised_at=datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc),
    withdrawn_at=None,
    withdrawal_note=None,
    decided_by="Coordinator Three",
    decided_at=datetime(2026, 9, 16, 2, 30, tzinfo=timezone.utc),
    decision_reason="The hall holds 300.",
)
DECIDED_BODY = {
    "id": CHANGE_REQUEST_ID,
    "status": "approved",
    "changes": [{"field": "expected_attendance", "previous_value": 250, "requested_value": 300}],
    "reason": "More partners are coming.",
    "raised_by": "Alice Example",
    "raised_at": "2026-09-15T09:00:00+08:00",
    "withdrawn_at": None,
    "withdrawal_note": None,
    "decided_by": "Coordinator Three",
    "decided_at": "2026-09-16T10:30:00+08:00",
    "decision_reason": "The hall holds 300.",
}


def _replace_service(replace_services: ReplaceServices) -> MagicMock:
    return replace_services(routes, {"decide_change_request": DECIDED})["decide_change_request"]


def _call(call_route: CallRoute, token: str | None) -> Any:
    return call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, token, body=BODY)


def test_the_route_allows_only_event_coordinators(app: Flask) -> None:
    allowed_roles = app.view_functions[ENDPOINT].allowed_roles  # type: ignore[attr-defined]

    assert allowed_roles == frozenset({Role.EVENT_COORDINATOR.value})


def test_every_other_role_is_refused(
    call_route: CallRoute, token_for: Callable[..., str], replace_services: ReplaceServices
) -> None:
    service = _replace_service(replace_services)

    for role in ALL_ROLES - {Role.EVENT_COORDINATOR}:
        with pytest.raises(AuthorizationError) as exc_info:
            _call(call_route, token_for(role=role))

        assert exc_info.value.status_code == 403
    service.assert_not_called()


def test_calling_the_route_without_a_token_is_401(
    call_route: CallRoute, replace_services: ReplaceServices
) -> None:
    service = _replace_service(replace_services)

    with pytest.raises(AuthenticationError) as exc_info:
        _call(call_route, None)

    assert exc_info.value.status_code == 401
    service.assert_not_called()


def test_the_route_passes_the_caller_and_body_on_and_returns_the_decided_request(
    call_route: CallRoute, token_for: Callable[..., str], replace_services: ReplaceServices
) -> None:
    service = _replace_service(replace_services)

    response, status = _call(call_route, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 200
    # The caller comes from their token, never from the body.
    service.assert_called_once_with("999", REFERENCE, CHANGE_REQUEST_ID, BODY)
    assert response.get_json() == DECIDED_BODY
