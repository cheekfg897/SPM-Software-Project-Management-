"""Unit tests for SCRUM-60's routes, and who may call them (ADR-0114).

An event's reservations awaiting reassessment are read as its reservations are: by
Technical Support Staff, and by Event Coordinators, whose events the services scope
(AC2; ADR-0019, ADR-0037). Only Technical Support Staff confirm one (AC3). Every other
role is refused. The *registered* view functions
are called inside a request context, so the real decorators run; the services are
replaced with mocks, so a refused request is shown to stop before any service call.
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

pytestmark = pytest.mark.scrum_60

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

#: The route passes the reference on as it came; the events module normalises it.
REFERENCE = "EVR-AAAAAAAA"
BASE_PATH = f"/api/equipment/events/{REFERENCE}/reassessments"
#: ``token_for`` mints the user id 999, which a token carries as text.
CALLER_ID = "999"

#: Who reads an event's equipment (ADR-0019, ADR-0037).
EQUIPMENT_READERS = {Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF}

# (endpoint, method, path, view arguments, service, success status, roles allowed)
ROUTES = [
    (
        "equipment.list_event_reassessments",
        "GET",
        BASE_PATH,
        {"reference": REFERENCE},
        "list_reassessments_for_event",
        200,
        EQUIPMENT_READERS,
    ),
    (
        "equipment.confirm_reassessment",
        "POST",
        f"{BASE_PATH}/2/confirm",
        {"reference": REFERENCE, "equipment_type_id": 2},
        "confirm_reservation_move",
        200,
        {Role.TECHNICAL_SUPPORT_STAFF},
    ),
]
ROUTE_PARAMS = ("endpoint", "method", "path", "view_kwargs", "service", "status", "allowed")
ROUTE_IDS = [route[0] for route in ROUTES]

ROLES_THAT_MAY = [
    pytest.param(*route, role, id=f"{route[0]}-{role.value}")
    for route in ROUTES
    for role in sorted(route[6], key=lambda role: role.value)
]
ROLES_THAT_MAY_NOT = [
    pytest.param(*route, role, id=f"{route[0]}-{role.value}")
    for route in ROUTES
    for role in sorted(ALL_ROLES - set(route[6]), key=lambda role: role.value)
]

SHOWN_RESERVATION = services.ReservationAsShown(
    id=12,
    equipment_type_id=2,
    equipment_type_name="Projector",
    quantity=3,
    starts_at=datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc),
    ends_at=datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc),
    reserved_by="Alice Example",
    created_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    needs_attention=False,
    preparation_status=PreparationStatus.IN_PROGRESS,
    preparation_notes="Bulbs checked",
)
RESERVATION_JSON = {
    "id": 12,
    "equipment_type_id": 2,
    "equipment_type_name": "Projector",
    "quantity": 3,
    "starts_at": "2026-10-15T09:00:00+08:00",
    "ends_at": "2026-10-15T17:00:00+08:00",
    "reserved_by": "Alice Example",
    "created_at": "2026-10-01T16:00:00+08:00",
    "needs_attention": False,
    "preparation_status": "in_progress",
    "preparation_notes": "Bulbs checked",
}
REASSESSMENT = services.ReservationReassessment(
    equipment_type_id=2,
    equipment_type_name="Projector",
    reservations=[SHOWN_RESERVATION],
    reserved_quantity=3,
    starts_at=datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc),
    ends_at=datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc),
    available=1,
    shortfall=2,
)
#: Times in business time, as every equipment route shows them (ADR-0009).
REASSESSMENT_JSON = {
    "equipment_type_id": 2,
    "equipment_type_name": "Projector",
    "reservations": [RESERVATION_JSON],
    "reserved_quantity": 3,
    "starts_at": "2026-10-17T09:00:00+08:00",
    "ends_at": "2026-10-17T17:00:00+08:00",
    "available": 1,
    "shortfall": 2,
}


@pytest.fixture()
def mock_services(replace_services: ReplaceServices) -> dict[str, MagicMock]:
    """Replace every equipment service these routes call with a mock."""
    return replace_services(
        services,
        {
            "list_reassessments_for_event": [REASSESSMENT],
            "confirm_reservation_move": [SHOWN_RESERVATION],
        },
    )


def _assert_no_service_called(mock_services: dict[str, MagicMock]) -> None:
    """A refused request must be stopped before it reaches any equipment service."""
    for mock in mock_services.values():
        mock.assert_not_called()


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
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
    allowed: set[Role],
    role: Role,
) -> None:
    _, response_status = call_route(endpoint, method, path, view_kwargs, token_for(role=role))

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
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
    allowed: set[Role],
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(endpoint, method, path, view_kwargs, token_for(role=role))

    assert exc_info.value.status_code == 403
    _assert_no_service_called(mock_services)


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_a_request_without_a_token_is_401_before_any_service(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
    allowed: set[Role],
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(endpoint, method, path, view_kwargs, token=None)

    assert exc_info.value.status_code == 401
    _assert_no_service_called(mock_services)


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_a_route_allows_exactly_its_roles(
    app: Flask,
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
    allowed: set[Role],
) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[endpoint].allowed_roles == frozenset(role.value for role in allowed)


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_the_roles_refused_and_allowed_make_up_every_role(
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
    allowed: set[Role],
) -> None:
    refused = set()
    for param in ROLES_THAT_MAY_NOT:
        if param.values[0] == endpoint:
            refused.add(param.values[-1])

    assert refused | allowed == set(Role)
    assert refused.isdisjoint(allowed)


def test_the_list_route_returns_each_type_to_reassess_for_the_caller(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.list_event_reassessments",
        "GET",
        BASE_PATH,
        {"reference": REFERENCE},
        token_for(role=Role.EVENT_COORDINATOR),
    )

    assert response.get_json() == [REASSESSMENT_JSON]
    mock_services["list_reassessments_for_event"].assert_called_once_with(
        CALLER_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR
    )


def test_the_confirm_route_confirms_the_type_for_the_caller_and_returns_its_reservations(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.confirm_reassessment",
        "POST",
        f"{BASE_PATH}/2/confirm",
        {"reference": REFERENCE, "equipment_type_id": 2},
        token_for(role=Role.TECHNICAL_SUPPORT_STAFF),
    )

    assert response.get_json() == [RESERVATION_JSON]
    mock_services["confirm_reservation_move"].assert_called_once_with(
        REFERENCE, 2, confirmed_by=CALLER_ID
    )
