"""Unit tests for SCRUM-97 "Submit an event for operational safety check" (part A).

The route: ``POST /api/events/requests/<reference>/safety-review``, with no body, is
for Event Coordinators only; the service checks the caller is the event's own
coordinator and that the event is ready (ADR-0047). It answers ``200`` with the
request, now in Safety Review, and never shows a user id.

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
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_97

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.submit_request_for_safety_review"
PATH = f"/api/events/requests/{REFERENCE}/safety-review"
VIEW_KWARGS = {"reference": REFERENCE}


@pytest.fixture()
def submit_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock returning coordinator 3's request in review."""
    in_review = make_event_request(status=EventRequestStatus.SAFETY_REVIEW, coordinator_id=3)
    mocks = replace_services(routes, {"submit_for_safety_review": in_review})
    return mocks["submit_for_safety_review"]


def test_other_roles_cannot_submit_an_event_for_safety_review(
    call_route: CallRoute,
    token_for: Callable[..., str],
    submit_service: MagicMock,
    non_coordinator_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=non_coordinator_role))

    assert exc_info.value.status_code == 403
    submit_service.assert_not_called()


def test_the_route_returns_the_request_in_safety_review(
    call_route: CallRoute, token_for: Callable[..., str], submit_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR)
    )

    assert status == 200
    # The caller is taken from their token; there is no body to pass on.
    submit_service.assert_called_once_with("999", REFERENCE)
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "safety_review")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
