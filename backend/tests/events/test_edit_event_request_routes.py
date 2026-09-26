"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

``PATCH /api/events/requests/<reference>``: Event Coordinators only; the service
checks the caller is the event's own assigned coordinator (ADR-0025). Answers
``200`` with the edited request, including its programme and internal planning
notes, and the list of changes made, and never shows a user id.

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
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest
from app.modules.events.services import EventEdit, FieldChange

pytestmark = pytest.mark.scrum_33

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.update_request"
PATH = f"/api/events/requests/{REFERENCE}"
VIEW_KWARGS = {"reference": REFERENCE}


@pytest.fixture()
def edited_event(make_event_request: Callable[..., EventRequest]) -> EventRequest:
    """The event ``update_event_request`` is mocked to have edited."""
    event_request = make_event_request()
    event_request.programme_notes = "Doors open at 08:30."
    event_request.internal_planning_notes = "Reserve the loading dock."
    return event_request


@pytest.fixture()
def update_service(replace_services: ReplaceServices, edited_event: EventRequest) -> MagicMock:
    """Replace the service with a mock reporting one significant change."""
    change = FieldChange("expected_attendance", 250, 300, True)
    mocks = replace_services(routes, {"update_event_request": EventEdit(edited_event, [change])})
    return mocks["update_event_request"]


def test_update_route_allows_only_event_coordinators(app: Flask) -> None:
    assert app.view_functions[ENDPOINT].allowed_roles == frozenset({"event_coordinator"})


def test_other_roles_cannot_edit_the_event(
    call_route: CallRoute,
    token_for: TokenFor,
    update_service: MagicMock,
    non_coordinator_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "PATCH", PATH, VIEW_KWARGS, token_for(role=non_coordinator_role))

    assert exc_info.value.status_code == 403
    update_service.assert_not_called()


def test_editing_without_a_token_is_401(call_route: CallRoute, update_service: MagicMock) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "PATCH", PATH, VIEW_KWARGS, None)

    assert exc_info.value.status_code == 401
    update_service.assert_not_called()


def test_update_route_returns_the_event_and_its_changes(
    call_route: CallRoute, token_for: TokenFor, update_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "PATCH", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR)
    )

    assert status == 200
    # The caller is the coordinator, taken from their token; the body is passed on
    # exactly as sent.
    update_service.assert_called_once_with("999", REFERENCE, {})
    body = response.get_json()
    assert body["changes"] == [
        {
            "field": "expected_attendance",
            "previous_value": 250,
            "new_value": 300,
            "significant": True,
        }
    ]
    assert body["programme_notes"] == "Doors open at 08:30."
    assert body["internal_planning_notes"] == "Reserve the loading dock."
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
