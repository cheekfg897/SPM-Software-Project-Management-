"""Unit tests for SCRUM-61 AC1, an Event Organiser cancelling their event: the route.

``POST /api/events/requests/<reference>/cancel`` is for Event Organisers only. It
takes the caller from their token, passes the body on as sent, and answers ``200`` with
the request, now cancelled, never showing a user id. The service is in
``test_cancel_event.py``.

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

pytestmark = pytest.mark.scrum_61

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.cancel_request"
PATH = f"/api/events/requests/{REFERENCE}/cancel"
VIEW_KWARGS = {"reference": REFERENCE}
BODY = {"reason": "Our keynote speaker has withdrawn."}


@pytest.fixture()
def cancel_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock returning organiser 7's cancelled request."""
    cancelled = make_event_request(status=EventRequestStatus.CANCELLED, coordinator_id=3)
    mocks = replace_services(routes, {"cancel_event_request": cancelled})
    return mocks["cancel_event_request"]


def test_other_roles_cannot_cancel_an_event(
    call_route: CallRoute,
    token_for: Callable[..., str],
    cancel_service: MagicMock,
    non_organiser_role: Role,
) -> None:
    """Only the Organiser cancels; a coordinator rejects (Product Owner, 30 Oct)."""
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(
            ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=non_organiser_role), body=BODY
        )

    assert exc_info.value.status_code == 403
    cancel_service.assert_not_called()


def test_cancelling_without_a_token_is_401(
    call_route: CallRoute, cancel_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, None, body=BODY)

    assert exc_info.value.status_code == 401
    cancel_service.assert_not_called()


def test_the_route_passes_the_reason_on_and_returns_the_cancelled_request(
    call_route: CallRoute, token_for: Callable[..., str], cancel_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_ORGANISER), body=BODY
    )

    assert status == 200
    # The caller is taken from their token, and the body is passed on as sent.
    cancel_service.assert_called_once_with("999", REFERENCE, BODY)
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "cancelled")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
