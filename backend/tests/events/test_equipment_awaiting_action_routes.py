"""Unit tests for SCRUM-38 "See the equipment requests awaiting my action": the route.

``GET /api/events/requests/awaiting-equipment`` shows each event still awaiting
equipment with its date and times, the lines still requested and the days remaining
(AC2). Only Technical Support Staff can open it (AC6), and it is one list for all of
them (ADR-0022). The service is in ``test_equipment_awaiting_action.py``.

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
from app.modules.events.models import EventEquipmentLine, EventRequest
from app.modules.events.services import EquipmentAwaitingAction

pytestmark = pytest.mark.scrum_38

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

ENDPOINT = "events.list_equipment_awaiting_action"
PATH = "/api/events/requests/awaiting-equipment"
NON_TECHNICAL_SUPPORT_ROLES = sorted(
    ALL_ROLES - {Role.TECHNICAL_SUPPORT_STAFF}, key=lambda role: role.value
)


def _open_the_list(call_route: CallRoute, token: str | None) -> Any:
    return call_route(ENDPOINT, "GET", PATH, {}, token)


@pytest.fixture()
def list_service(
    replace_services: ReplaceServices, shown_event: EventRequest, shown_line: EventEquipmentLine
) -> MagicMock:
    """Replace the service with a mock listing ``shown_event``, 30 days away.

    Its line's reservation awaits reassessment (SCRUM-60 AC6).
    """
    awaiting = [
        EquipmentAwaitingAction(
            shown_event, [shown_line], days_remaining=30, equipment_type_ids_to_reassess=[1]
        )
    ]
    mocks = replace_services(routes, {"list_equipment_requests_awaiting_action": awaiting})
    return mocks["list_equipment_requests_awaiting_action"]


# --------------------------------------------------------------------------
# AC6 — only Technical Support Staff can open it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", NON_TECHNICAL_SUPPORT_ROLES, ids=lambda role: role.value)
def test_opening_the_list_as_anyone_but_technical_support_is_403(
    call_route: CallRoute, token_for: TokenFor, list_service: MagicMock, role: Role
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        _open_the_list(call_route, token_for(role=role))

    assert exc_info.value.status_code == 403
    list_service.assert_not_called()


def test_opening_the_list_without_a_token_is_401(
    call_route: CallRoute, list_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        _open_the_list(call_route, None)

    assert exc_info.value.status_code == 401
    list_service.assert_not_called()


def test_the_list_route_allows_only_technical_support(app: Flask) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[ENDPOINT].allowed_roles == frozenset(
        {Role.TECHNICAL_SUPPORT_STAFF.value}
    )


def test_the_awaiting_equipment_path_is_matched_before_a_reference(app: Flask) -> None:
    """``awaiting-equipment`` must not be read as the reference of an event request."""
    adapter = app.url_map.bind("localhost")

    assert adapter.match(PATH) == (ENDPOINT, {})


# --------------------------------------------------------------------------
# AC2 — each row: the event's name, date and times, its lines and the days remaining
# --------------------------------------------------------------------------


def test_the_list_route_shows_each_request_with_its_event_lines_and_days_remaining(
    call_route: CallRoute,
    token_for: TokenFor,
    list_service: MagicMock,
    event_as_shown: dict[str, Any],
    line_as_shown: dict[str, Any],
) -> None:
    response, status = _open_the_list(call_route, token_for(role=Role.TECHNICAL_SUPPORT_STAFF))

    assert status == 200
    assert response.get_json() == {
        "equipment_requests": [
            {
                "event": event_as_shown,
                "equipment_lines": [line_as_shown],
                "days_remaining": 30,
                "equipment_type_ids_to_reassess": [1],
            }
        ]
    }
    list_service.assert_called_once_with()
