"""Unit tests for SCRUM-49 AC9, rejecting an event during planning: the route.

``POST /api/events/requests/<reference>/reject`` is for Event Coordinators only. It
takes the caller from their token, passes the body on as sent, and answers ``200`` with
the request, never showing a user id. The service is in
``test_reject_during_planning.py``.

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

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_49

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.reject_request"
PATH = f"/api/events/requests/{REFERENCE}/reject"
VIEW_KWARGS = {"reference": REFERENCE}
BODY = {"reason": "No venue large enough is free that week."}


@pytest.fixture()
def reject_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock returning coordinator 3's rejected request."""
    rejected = make_event_request(status=EventRequestStatus.REJECTED, coordinator_id=3)
    mocks = replace_services(routes, {"reject_event_during_planning": rejected})
    return mocks["reject_event_during_planning"]


def test_other_roles_cannot_reject_an_event(
    call_route: CallRoute,
    token_for: Callable[..., str],
    reject_service: MagicMock,
    non_coordinator_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(
            ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=non_coordinator_role), body=BODY
        )

    assert exc_info.value.status_code == 403
    reject_service.assert_not_called()


def test_rejecting_without_a_token_is_401(call_route: CallRoute, reject_service: MagicMock) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, None, body=BODY)

    assert exc_info.value.status_code == 401
    reject_service.assert_not_called()


def test_the_route_passes_the_reason_on_and_returns_the_rejected_request(
    call_route: CallRoute, token_for: Callable[..., str], reject_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR), body=BODY
    )

    assert status == 200
    # The caller is taken from their token, and the body is passed on as sent.
    reject_service.assert_called_once_with("999", REFERENCE, BODY)
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "rejected")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
