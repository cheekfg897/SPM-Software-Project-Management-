"""Unit tests for the routes of SCRUM-45 and SCRUM-46, and who may call them.

An event's availability and reservations are read by Technical Support Staff and Event
Coordinators, as the event's equipment lines are (SCRUM-45; SCRUM-46 AC4, the
reservation is visible on the event record; ADR-0019, ADR-0037). Venue Staff and
external roles are refused. Which events a coordinator may read is the services' job
(``test_equipment_read_scoping.py``). Only Technical Support Staff reserve (SCRUM-46
AC1). The *registered* view functions are called inside a
request context, so the real decorators run; the services are replaced with mocks, so a
refused request is shown to stop before any service call.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.equipment import services
from app.modules.equipment.models import PreparationStatus

pytestmark = pytest.mark.scrum_46

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

#: The route passes the reference on as it came; the events module normalises it.
REFERENCE = "EVR-AAAAAAAA"
BASE_PATH = f"/api/equipment/events/{REFERENCE}"

#: ``token_for`` mints the user id 999, which a token carries as text.
CALLER_ID = "999"

#: Who reads an event's equipment (ADR-0019, ADR-0037).
EQUIPMENT_READERS = {Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF}

# (endpoint, method, path, service it calls, success status, roles allowed)
ROUTES = [
    (
        "equipment.get_event_availability",
        "GET",
        f"{BASE_PATH}/availability",
        "equipment_availability_for_event",
        200,
        EQUIPMENT_READERS,
    ),
    (
        "equipment.reserve_equipment",
        "POST",
        f"{BASE_PATH}/reservations",
        "reserve_equipment",
        201,
        {Role.TECHNICAL_SUPPORT_STAFF},
    ),
    (
        "equipment.list_event_reservations",
        "GET",
        f"{BASE_PATH}/reservations",
        "list_reservations_for_event",
        200,
        EQUIPMENT_READERS,
    ),
]
ROUTE_PARAMS = ("endpoint", "method", "path", "service", "status", "allowed_roles")
ROUTE_IDS = [route[0] for route in ROUTES]

ROLES_THAT_MAY = [
    pytest.param(*route, role, id=f"{route[0]}-{role.value}")
    for route in ROUTES
    for role in sorted(route[5], key=lambda role: role.value)
]
ROLES_THAT_MAY_NOT = [
    pytest.param(*route, role, id=f"{route[0]}-{role.value}")
    for route in ROUTES
    for role in sorted(ALL_ROLES - set(route[5]), key=lambda role: role.value)
]

SHOWN_RESERVATION = services.ReservationAsShown(
    id=12,
    equipment_type_id=2,
    equipment_type_name="Projector",
    quantity=4,
    starts_at=datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc),
    ends_at=datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc),
    reserved_by="Alice Example",
    created_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    needs_attention=False,
    preparation_status=PreparationStatus.NOT_STARTED,
    preparation_notes=None,
)
RESERVATION_JSON = {
    "id": 12,
    "equipment_type_id": 2,
    "equipment_type_name": "Projector",
    "quantity": 4,
    "starts_at": "2026-10-15T09:00:00+08:00",
    "ends_at": "2026-10-15T17:00:00+08:00",
    "reserved_by": "Alice Example",
    "created_at": "2026-10-01T16:00:00+08:00",
    "needs_attention": False,
    "preparation_status": "not_started",
    "preparation_notes": None,
}
AVAILABILITY = services.EquipmentAvailability(
    equipment_type_id=2,
    equipment_type_name="Projector",
    available=6,
    requested=8,
    shortfall=2,
)
AVAILABILITY_JSON = {
    "equipment_type_id": 2,
    "equipment_type_name": "Projector",
    "available": 6,
    "requested": 8,
    "shortfall": 2,
}


@pytest.fixture()
def mock_services(replace_services: ReplaceServices) -> dict[str, MagicMock]:
    """Replace every equipment service these routes call with a mock."""
    return replace_services(
        services,
        {
            "equipment_availability_for_event": [AVAILABILITY],
            "reserve_equipment": SHOWN_RESERVATION,
            "list_reservations_for_event": [SHOWN_RESERVATION],
        },
    )


def _assert_no_service_called(mock_services: dict[str, MagicMock]) -> None:
    """A refused request must be stopped before it reaches any equipment service."""
    for mock in mock_services.values():
        mock.assert_not_called()


@pytest.mark.scrum_45
@pytest.mark.parametrize(
    (*ROUTE_PARAMS, "role"), ROLES_THAT_MAY, ids=[p.id for p in ROLES_THAT_MAY]
)
def test_a_role_the_route_allows_gets_through_to_the_service(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    service: str,
    status: int,
    allowed_roles: set[Role],
    role: Role,
) -> None:
    _, response_status = call_route(
        endpoint, method, path, {"reference": REFERENCE}, token_for(role=role)
    )

    assert response_status == status
    mock_services[service].assert_called_once()


@pytest.mark.parametrize(
    (*ROUTE_PARAMS, "role"), ROLES_THAT_MAY_NOT, ids=[p.id for p in ROLES_THAT_MAY_NOT]
)
def test_a_role_the_route_does_not_allow_is_403_before_any_service(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    service: str,
    status: int,
    allowed_roles: set[Role],
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(endpoint, method, path, {"reference": REFERENCE}, token_for(role=role))

    assert exc_info.value.status_code == 403
    _assert_no_service_called(mock_services)


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_a_request_without_a_token_is_401_before_any_service(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    service: str,
    status: int,
    allowed_roles: set[Role],
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(endpoint, method, path, {"reference": REFERENCE}, token=None)

    assert exc_info.value.status_code == 401
    _assert_no_service_called(mock_services)


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_a_route_allows_exactly_its_roles(
    app: Flask,
    endpoint: str,
    method: str,
    path: str,
    service: str,
    status: int,
    allowed_roles: set[Role],
) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[endpoint].allowed_roles == frozenset(
        role.value for role in allowed_roles
    )


@pytest.mark.scrum_45
def test_the_availability_route_returns_a_row_for_each_equipment_type(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.get_event_availability",
        "GET",
        f"{BASE_PATH}/availability",
        {"reference": REFERENCE},
        token_for(role=Role.TECHNICAL_SUPPORT_STAFF),
    )

    assert response.get_json() == [AVAILABILITY_JSON]
    mock_services["equipment_availability_for_event"].assert_called_once_with(
        CALLER_ID, REFERENCE, viewer_role=Role.TECHNICAL_SUPPORT_STAFF
    )


def test_the_reserve_route_passes_the_body_and_the_caller_and_returns_the_reservation(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.reserve_equipment",
        "POST",
        f"{BASE_PATH}/reservations",
        {"reference": REFERENCE},
        token_for(role=Role.TECHNICAL_SUPPORT_STAFF),
    )

    assert response.get_json() == RESERVATION_JSON
    # The body is always {} in the helper; the caller is the token's user.
    mock_services["reserve_equipment"].assert_called_once_with(REFERENCE, {}, reserved_by=CALLER_ID)


def test_the_list_route_returns_each_reservation_the_service_found(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.list_event_reservations",
        "GET",
        f"{BASE_PATH}/reservations",
        {"reference": REFERENCE},
        token_for(role=Role.EVENT_COORDINATOR),
    )

    assert response.get_json() == [RESERVATION_JSON]
    mock_services["list_reservations_for_event"].assert_called_once_with(
        CALLER_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR
    )
