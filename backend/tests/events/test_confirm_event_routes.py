"""Unit tests for SCRUM-49, confirming an event: the route.

``POST /api/events/requests/<reference>/confirm`` is for Event Coordinators only. It
takes the caller from their token, passes no body on, and answers ``200`` with the
request, never showing a user id. The service is in ``test_confirm_event.py``.

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

pytestmark = pytest.mark.scrum_49

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.confirm_request"
PATH = f"/api/events/requests/{REFERENCE}/confirm"
VIEW_KWARGS = {"reference": REFERENCE}


@pytest.fixture()
def confirm_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock returning coordinator 3's confirmed request."""
    confirmed = make_event_request(status=EventRequestStatus.CONFIRMED, coordinator_id=3)
    mocks = replace_services(routes, {"confirm_event_request": confirmed})
    return mocks["confirm_event_request"]


def test_other_roles_cannot_confirm_an_event(
    call_route: CallRoute,
    token_for: Callable[..., str],
    confirm_service: MagicMock,
    non_coordinator_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=non_coordinator_role))

    assert exc_info.value.status_code == 403
    confirm_service.assert_not_called()


def test_the_route_returns_the_confirmed_request(
    call_route: CallRoute, token_for: Callable[..., str], confirm_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR)
    )

    assert status == 200
    # The caller is taken from their token; there is no body to pass on.
    confirm_service.assert_called_once_with("999", REFERENCE)
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "confirmed")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
