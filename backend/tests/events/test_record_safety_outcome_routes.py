"""Unit tests for SCRUM-98 "Record the operational safety check outcome": the route.

``POST /api/events/requests/<reference>/safety-outcome`` is for Safety Officers only
(AC9). It passes the body to the service and answers ``200`` with the request, never
showing a user id. The service is in ``test_record_safety_outcome.py``.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused caller must be stopped
before it is called.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_98

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.record_request_safety_outcome"
PATH = f"/api/events/requests/{REFERENCE}/safety-outcome"
VIEW_KWARGS = {"reference": REFERENCE}
BODY = {"outcome": "changes_requested", "reason": "Exit blocked.", "checklist": {}}
NON_SAFETY_OFFICER_ROLES = sorted(ALL_ROLES - {Role.SAFETY_OFFICER}, key=lambda role: role.value)


@pytest.fixture()
def outcome_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock returning a request back in planning."""
    returned = make_event_request(status=EventRequestStatus.APPROVED, coordinator_id=3)
    mocks = replace_services(routes, {"record_safety_outcome": returned})
    return mocks["record_safety_outcome"]


@pytest.mark.parametrize("role", NON_SAFETY_OFFICER_ROLES, ids=lambda role: role.value)
def test_other_roles_cannot_record_a_safety_outcome(
    call_route: CallRoute,
    token_for: Callable[..., str],
    outcome_service: MagicMock,
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=role), body=BODY)

    assert exc_info.value.status_code == 403
    outcome_service.assert_not_called()


def test_the_route_passes_the_body_on_and_returns_the_request(
    call_route: CallRoute, token_for: Callable[..., str], outcome_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=Role.SAFETY_OFFICER), body=BODY
    )

    assert status == 200
    outcome_service.assert_called_once_with("999", REFERENCE, BODY)
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "approved")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
