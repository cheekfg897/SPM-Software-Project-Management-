"""Unit tests for SCRUM-37 "Record what equipment an event needs": the routes.

Event Coordinators add, edit and remove an event's equipment lines (AC1, AC2);
coordinators and Technical Support Staff read them, with the event's date and times
so Technical Support know by when it is needed, and the coordinator sees them on
the event record (AC4, ADR-0019). The organiser's own view of them is in
``test_organiser_equipment_view.py`` (AC5, ADR-0098). Each route passes the caller's
id on, so the services can limit a coordinator to the events assigned to them
(ADR-0019).

The *registered* view functions are called inside a request context, so the real
decorators run. The services are replaced with mocks: a refused request must be
stopped before any service call happens.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EventEquipmentLine, EventRequest
from app.modules.events.services import CoordinatorEventRecord, EquipmentLineAsShown

pytestmark = pytest.mark.scrum_37

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

#: The user id ``token_for`` puts in a token minted for a role alone.
CALLER_ID = "999"
REFERENCE = "EVR-AAAAAAAA"
LINES_PATH = f"/api/events/requests/{REFERENCE}/equipment"
LINE_PATH = f"{LINES_PATH}/7"
LINE_KWARGS: dict[str, Any] = {"reference": REFERENCE, "line_id": 7}


class EquipmentRoute(NamedTuple):
    """An equipment line route, how to call its view, and the service it calls."""

    endpoint: str
    method: str
    path: str
    view_kwargs: dict[str, Any]
    service: str


ADD = EquipmentRoute(
    "events.add_equipment", "POST", LINES_PATH, {"reference": REFERENCE}, "add_equipment_line"
)
LIST = EquipmentRoute(
    "events.list_equipment", "GET", LINES_PATH, {"reference": REFERENCE}, "list_equipment_lines"
)
EDIT = EquipmentRoute(
    "events.update_equipment", "PATCH", LINE_PATH, LINE_KWARGS, "update_equipment_line"
)
REMOVE = EquipmentRoute(
    "events.remove_equipment", "DELETE", LINE_PATH, LINE_KWARGS, "remove_equipment_line"
)
WRITE_ROUTES = [ADD, EDIT, REMOVE]
ALL_ROUTES = [ADD, LIST, EDIT, REMOVE]

LINE_READERS = [Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF]
NON_READER_ROLES = sorted(ALL_ROLES - set(LINE_READERS), key=lambda role: role.value)


def _call(call_route: CallRoute, route: EquipmentRoute, token: str | None) -> Any:
    return call_route(route.endpoint, route.method, route.path, route.view_kwargs, token)


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices,
    shown_event: EventRequest,
    shown_line: EventEquipmentLine,
    reviewed_line: EquipmentLineAsShown,
) -> dict[str, MagicMock]:
    """Replace every equipment line service the routes call with a mock."""
    return replace_services(
        routes,
        {
            "add_equipment_line": shown_line,
            "list_equipment_lines": (shown_event, [shown_line]),
            "update_equipment_line": shown_line,
            "remove_equipment_line": None,
            "equipment_lines_as_shown": [reviewed_line],
        },
    )


# --------------------------------------------------------------------------
# AC1, AC2 — only Event Coordinators add, edit and remove lines
# --------------------------------------------------------------------------


@pytest.mark.parametrize("route", WRITE_ROUTES, ids=lambda route: route.endpoint)
def test_writing_lines_by_anyone_but_coordinators_is_403(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    non_coordinator_role: Role,
    route: EquipmentRoute,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        _call(call_route, route, token_for(role=non_coordinator_role))

    assert exc_info.value.status_code == 403
    mock_services[route.service].assert_not_called()


@pytest.mark.parametrize("role", NON_READER_ROLES, ids=lambda role: role.value)
def test_reading_lines_by_other_roles_is_403(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock], role: Role
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        _call(call_route, LIST, token_for(role=role))

    assert exc_info.value.status_code == 403
    mock_services[LIST.service].assert_not_called()


@pytest.mark.parametrize("route", ALL_ROUTES, ids=lambda route: route.endpoint)
def test_line_routes_without_a_token_are_401(
    call_route: CallRoute, mock_services: dict[str, MagicMock], route: EquipmentRoute
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        _call(call_route, route, None)

    assert exc_info.value.status_code == 401
    mock_services[route.service].assert_not_called()


@pytest.mark.parametrize("route", WRITE_ROUTES, ids=lambda route: route.endpoint)
def test_write_routes_allow_only_coordinators(app: Flask, route: EquipmentRoute) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[route.endpoint].allowed_roles == frozenset(
        {Role.EVENT_COORDINATOR.value}
    )


def test_the_list_route_allows_coordinators_and_technical_support(app: Flask) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[LIST.endpoint].allowed_roles == frozenset(
        {Role.EVENT_COORDINATOR.value, Role.TECHNICAL_SUPPORT_STAFF.value}
    )


# --------------------------------------------------------------------------
# AC1, AC2 — what each route returns
# --------------------------------------------------------------------------


def test_the_add_route_returns_the_new_line(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    line_as_shown: dict[str, Any],
) -> None:
    response, status = _call(call_route, ADD, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 201
    assert response.get_json() == line_as_shown
    mock_services[ADD.service].assert_called_once_with(CALLER_ID, REFERENCE, {})


def test_the_edit_route_returns_the_changed_line(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    line_as_shown: dict[str, Any],
) -> None:
    response, status = _call(call_route, EDIT, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 200
    assert response.get_json() == line_as_shown
    mock_services[EDIT.service].assert_called_once_with(CALLER_ID, REFERENCE, 7, {})


def test_the_remove_route_returns_no_content(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, status = _call(call_route, REMOVE, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 204
    assert response.get_data() == b""
    mock_services[REMOVE.service].assert_called_once_with(CALLER_ID, REFERENCE, 7)


# --------------------------------------------------------------------------
# AC4 — the lines and their state are visible on the event record
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", LINE_READERS, ids=lambda role: role.value)
def test_the_list_route_shows_the_lines_and_when_the_event_is(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    event_as_shown: dict[str, Any],
    shown_line: EventEquipmentLine,
    role: Role,
) -> None:
    response, status = _call(call_route, LIST, token_for(role=role))

    assert status == 200
    assert response.get_json() == {
        "event": event_as_shown,
        "equipment_lines": [
            {
                "id": 7,
                "equipment_type_id": 1,
                "quantity": 10,
                "notes": None,
                "status": "partially_fulfilled",
                "provided_quantity": 6,
                "shortfall": 4,
                "outcome_note": "Only six in stock",
                "reviewed_by": "Alice Example",
                "reviewed_at": "2026-10-13T17:30:00+08:00",
            }
        ],
    }
    mock_services[LIST.service].assert_called_once_with(CALLER_ID, REFERENCE, viewer_role=role)
    mock_services["equipment_lines_as_shown"].assert_called_once_with([shown_line])


def test_the_coordinators_detail_route_shows_the_equipment_lines_with_their_notes(
    call_route: CallRoute,
    token_for: TokenFor,
    make_user: Callable[..., User],
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
    shown_line: EventEquipmentLine,
    line_as_shown: dict[str, Any],
) -> None:
    """The organiser's record shows its own view instead (ADR-0098)."""
    event_request = make_event_request()
    event_request.equipment_lines = [shown_line]
    record = CoordinatorEventRecord(event_request=event_request, coordinator=None)
    replace_services(routes, {"get_event_record_for_coordinator": record})
    coordinator = make_user(role=Role.EVENT_COORDINATOR, user_id=3)

    response, status = call_route(
        "events.get_my_request",
        "GET",
        f"/api/events/requests/{REFERENCE}",
        {"reference": REFERENCE},
        token_for(coordinator),
    )

    assert status == 200
    assert response.get_json()["equipment_lines"] == [line_as_shown]
