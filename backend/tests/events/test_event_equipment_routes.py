"""Unit tests for SCRUM-37 "Record what equipment an event needs": the routes.

Event Coordinators add, edit and remove an event's equipment lines (AC1, AC2);
coordinators and Technical Support Staff read them, with the event's date and times
so Technical Support know by when it is needed, and the organiser sees them on
their own event record (AC4, ADR-0019). Each route passes the caller's id on, so the
services can limit a coordinator to the events assigned to them (ADR-0019).

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
from app.modules.equipment.models import EquipmentType
from app.modules.events import routes
from app.modules.events.models import EventEquipmentLine, EventRequest

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

#: The line every mocked service returns, as the API shows it.
SHOWN = {
    "id": 7,
    "equipment_type_id": 1,
    "quantity": 2,
    "notes": "Needs HDMI",
    "status": "requested",
}
#: The event the mocked services' lines belong to, as the equipment list shows it:
#: the same field names and formats as the event request itself.
SHOWN_EVENT = {
    "reference": "EVR-AAAAAAAA",
    "name": "Partner Summit",
    "proposed_date": "2026-10-15",
    "end_date": "2026-10-15",
    "start_time": "09:00:00",
    "end_time": "17:00:00",
}


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
def shown_event(make_event_request: Callable[..., EventRequest]) -> EventRequest:
    """An in-memory event request that the equipment list shows as SHOWN_EVENT."""
    return make_event_request()


@pytest.fixture()
def shown_line(
    shown_event: EventRequest,
    make_equipment_type: Callable[..., EquipmentType],
    make_equipment_line: Callable[..., EventEquipmentLine],
) -> EventEquipmentLine:
    """An in-memory line that serialises to SHOWN."""
    line = make_equipment_line(shown_event, make_equipment_type())
    # In-memory objects have no ids, so set the ones SHOWN expects.
    line.id = 7
    line.equipment_type_id = 1
    return line


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, shown_event: EventRequest, shown_line: EventEquipmentLine
) -> dict[str, MagicMock]:
    """Replace every equipment line service the routes call with a mock."""
    return replace_services(
        routes,
        {
            "add_equipment_line": shown_line,
            "list_equipment_lines": (shown_event, [shown_line]),
            "update_equipment_line": shown_line,
            "remove_equipment_line": None,
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
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, status = _call(call_route, ADD, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 201
    assert response.get_json() == SHOWN
    mock_services[ADD.service].assert_called_once_with(CALLER_ID, REFERENCE, {})


def test_the_edit_route_returns_the_changed_line(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, status = _call(call_route, EDIT, token_for(role=Role.EVENT_COORDINATOR))

    assert status == 200
    assert response.get_json() == SHOWN
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
    role: Role,
) -> None:
    response, status = _call(call_route, LIST, token_for(role=role))

    assert status == 200
    assert response.get_json() == {"event": SHOWN_EVENT, "equipment_lines": [SHOWN]}
    mock_services[LIST.service].assert_called_once_with(CALLER_ID, REFERENCE, viewer_role=role)


def test_the_organisers_detail_route_shows_the_equipment_lines(
    call_route: CallRoute,
    token_for: TokenFor,
    make_user: Callable[..., User],
    replace_services: ReplaceServices,
    make_event_request: Callable[..., EventRequest],
    shown_line: EventEquipmentLine,
) -> None:
    event_request = make_event_request()
    event_request.equipment_lines = [shown_line]
    replace_services(routes, {"get_event_record_for_organiser": (event_request, None)})
    organiser = make_user(role=Role.EVENT_ORGANISER, user_id=7)

    response, status = call_route(
        "events.get_my_request",
        "GET",
        f"/api/events/requests/{REFERENCE}",
        {"reference": REFERENCE},
        token_for(organiser),
    )

    assert status == 200
    assert response.get_json()["equipment_lines"] == [SHOWN]
