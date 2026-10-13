"""Unit tests for SCRUM-87 "Reassign an event to a different coordinator": the route.

``POST /api/events/requests/<reference>/reassign`` with ``{"coordinator_email"}``:
Event Coordinator Leads only since SCRUM-96 (ADR-0021 superseded): any Lead may
reassign any event, and an Event Coordinator is refused. It answers ``200`` with the
request and the new coordinator's name and email (AC6), and never shows a user id.

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
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EventRequest
from app.modules.events.services import CoordinatorContact

pytestmark = pytest.mark.scrum_87

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.reassign_request"
PATH = f"/api/events/requests/{REFERENCE}/reassign"
VIEW_KWARGS = {"reference": REFERENCE}

#: Every role but the Lead, so a role added later is refused unless a test says not.
NON_LEAD_ROLES = sorted(ALL_ROLES - {Role.EVENT_COORDINATOR_LEAD}, key=lambda role: role.value)


@pytest.fixture()
def reassign_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock that reassigns the request to coordinator 9."""
    reassigned = make_event_request(coordinator_id=9)
    contact = CoordinatorContact(full_name="Coordinator Nine", email="coordinator9@example.com")
    mocks = replace_services(routes, {"reassign_coordinator": (reassigned, contact)})
    return mocks["reassign_coordinator"]


def test_reassign_route_allows_only_the_event_coordinator_lead(app: Flask) -> None:
    allowed_roles = app.view_functions[ENDPOINT].allowed_roles

    assert allowed_roles == frozenset({Role.EVENT_COORDINATOR_LEAD.value})


@pytest.mark.parametrize("role", NON_LEAD_ROLES, ids=lambda role: role.value)
def test_every_other_role_cannot_reassign(
    call_route: CallRoute,
    token_for: Callable[..., str],
    reassign_service: MagicMock,
    role: Role,
) -> None:
    """Covers the Event Coordinator (SCRUM-96 AC3), once the only role let in."""
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=role))

    assert exc_info.value.status_code == 403
    reassign_service.assert_not_called()


def test_reassigning_without_a_token_is_401(
    call_route: CallRoute, reassign_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, None)

    assert exc_info.value.status_code == 401
    reassign_service.assert_not_called()


def test_reassign_route_returns_the_request_and_its_new_coordinator(
    call_route: CallRoute, token_for: Callable[..., str], reassign_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR_LEAD)
    )

    assert status == 200
    # The caller is the actor, taken from their token; the body is passed on as sent.
    reassign_service.assert_called_once_with("999", REFERENCE, {})
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "submitted")
    assert body["coordinator"] == {
        "full_name": "Coordinator Nine",
        "email": "coordinator9@example.com",
    }
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
