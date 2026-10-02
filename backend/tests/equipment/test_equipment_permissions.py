"""Unit tests for SCRUM-27 AC3 — only Technical Support Staff change the catalogue.

Other internal users can view it; external users can't. The *registered* view
functions are called inside a request context, so the real decorators on each
equipment route run. The services are replaced with mocks: a refused request must
be stopped before any service call happens.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, EXTERNAL_ROLES, INTERNAL_ROLES, Role
from app.modules.equipment import services
from app.modules.equipment.models import EquipmentType

pytestmark = pytest.mark.scrum_27

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

#: Not 1, so a route that passes the wrong id to its service is caught.
EQUIPMENT_TYPE_ID = 7

# (endpoint, HTTP method, path, view kwargs, service function it calls, success status)
WRITE_ROUTES = [
    (
        "equipment.create_equipment_type",
        "POST",
        "/api/equipment/types",
        {},
        "create_equipment_type",
        201,
    ),
    (
        "equipment.update_equipment_type",
        "PATCH",
        f"/api/equipment/types/{EQUIPMENT_TYPE_ID}",
        {"equipment_type_id": EQUIPMENT_TYPE_ID},
        "update_equipment_type",
        200,
    ),
]
WRITE_ROUTE_IDS = [route[0] for route in WRITE_ROUTES]
WRITE_PARAMS = ("endpoint", "method", "path", "view_kwargs", "service", "status")

# (endpoint, path, view kwargs)
READ_ROUTES = [
    ("equipment.list_equipment_types", "/api/equipment/types", {}),
    (
        "equipment.get_equipment_type",
        f"/api/equipment/types/{EQUIPMENT_TYPE_ID}",
        {"equipment_type_id": EQUIPMENT_TYPE_ID},
    ),
]
READ_ROUTE_IDS = [route[0] for route in READ_ROUTES]

#: What a route returns for the equipment type ``mock_services`` hands it.
PROJECTOR_JSON = {
    "id": None,
    "name": "Projector",
    "description": None,
    "total_quantity": 10,
    "venue_id": None,
    "store_name": "Central AV store",
}

NON_TECHNICAL_SUPPORT_ROLES = sorted(
    ALL_ROLES - {Role.TECHNICAL_SUPPORT_STAFF}, key=lambda role: role.value
)
SORTED_INTERNAL_ROLES = sorted(INTERNAL_ROLES, key=lambda role: role.value)
SORTED_EXTERNAL_ROLES = sorted(EXTERNAL_ROLES, key=lambda role: role.value)


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, make_equipment_type: Callable[..., EquipmentType]
) -> dict[str, MagicMock]:
    """Replace every equipment service the routes call with a mock."""
    return replace_services(
        services,
        {
            "create_equipment_type": make_equipment_type(),
            "update_equipment_type": make_equipment_type(),
            "list_equipment_types": [make_equipment_type()],
            "get_equipment_type": make_equipment_type(),
        },
    )


def _assert_no_service_called(mock_services: dict[str, MagicMock]) -> None:
    """A refused request must be stopped before it reaches any equipment service."""
    for mock in mock_services.values():
        mock.assert_not_called()


# --------------------------------------------------------------------------
# AC3 — only Technical Support Staff can create or change equipment records
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", NON_TECHNICAL_SUPPORT_ROLES, ids=lambda role: role.value)
@pytest.mark.parametrize(WRITE_PARAMS, WRITE_ROUTES, ids=WRITE_ROUTE_IDS)
def test_write_by_anyone_but_technical_support_is_403(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    role: Role,
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(endpoint, method, path, view_kwargs, token_for(role=role))

    assert exc_info.value.status_code == 403
    mock_services[service].assert_not_called()


@pytest.mark.parametrize(WRITE_PARAMS, WRITE_ROUTES, ids=WRITE_ROUTE_IDS)
def test_write_without_token_is_401(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(endpoint, method, path, view_kwargs, token=None)

    assert exc_info.value.status_code == 401
    mock_services[service].assert_not_called()


@pytest.mark.parametrize("endpoint", WRITE_ROUTE_IDS)
def test_write_route_allows_only_technical_support(app: Flask, endpoint: str) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[endpoint].allowed_roles == frozenset(
        {Role.TECHNICAL_SUPPORT_STAFF.value}
    )


@pytest.mark.parametrize(WRITE_PARAMS, WRITE_ROUTES, ids=WRITE_ROUTE_IDS)
def test_write_by_technical_support_reaches_the_service(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    service: str,
    status: int,
) -> None:
    token = token_for(role=Role.TECHNICAL_SUPPORT_STAFF)

    response, response_status = call_route(endpoint, method, path, view_kwargs, token)

    assert response_status == status
    assert response.get_json() == PROJECTOR_JSON
    # The service gets the URL's id, if there is one, then the body (always {} here).
    mock_services[service].assert_called_once_with(*view_kwargs.values(), {})


# --------------------------------------------------------------------------
# AC3 — other internal users can view equipment records
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", SORTED_INTERNAL_ROLES, ids=lambda role: role.value)
@pytest.mark.parametrize(("endpoint", "path", "view_kwargs"), READ_ROUTES, ids=READ_ROUTE_IDS)
def test_read_is_allowed_for_every_internal_role(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    role: Role,
    endpoint: str,
    path: str,
    view_kwargs: dict[str, Any],
) -> None:
    _, status = call_route(endpoint, "GET", path, view_kwargs, token_for(role=role))

    assert status == 200


def test_list_returns_every_type_the_service_found(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    token = token_for(role=Role.VENUE_STAFF)

    response, _ = call_route(
        "equipment.list_equipment_types", "GET", "/api/equipment/types", {}, token
    )

    assert response.get_json() == [PROJECTOR_JSON]
    mock_services["list_equipment_types"].assert_called_once_with()


def test_get_returns_the_type_the_service_found(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    token = token_for(role=Role.VENUE_STAFF)
    path = f"/api/equipment/types/{EQUIPMENT_TYPE_ID}"

    response, _ = call_route(
        "equipment.get_equipment_type", "GET", path, {"equipment_type_id": EQUIPMENT_TYPE_ID}, token
    )

    assert response.get_json() == PROJECTOR_JSON
    mock_services["get_equipment_type"].assert_called_once_with(EQUIPMENT_TYPE_ID)


@pytest.mark.parametrize(("endpoint", "path", "view_kwargs"), READ_ROUTES, ids=READ_ROUTE_IDS)
def test_read_without_token_is_401(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    path: str,
    view_kwargs: dict[str, Any],
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(endpoint, "GET", path, view_kwargs, token=None)

    assert exc_info.value.status_code == 401
    _assert_no_service_called(mock_services)


@pytest.mark.parametrize("role", SORTED_EXTERNAL_ROLES, ids=lambda role: role.value)
@pytest.mark.parametrize(("endpoint", "path", "view_kwargs"), READ_ROUTES, ids=READ_ROUTE_IDS)
def test_read_by_an_external_role_is_403(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    role: Role,
    endpoint: str,
    path: str,
    view_kwargs: dict[str, Any],
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(endpoint, "GET", path, view_kwargs, token_for(role=role))

    assert exc_info.value.status_code == 403
    _assert_no_service_called(mock_services)


@pytest.mark.parametrize("endpoint", READ_ROUTE_IDS)
def test_read_route_allows_only_internal_roles(app: Flask, endpoint: str) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    internal_role_values = frozenset(role.value for role in INTERNAL_ROLES)

    assert app.view_functions[endpoint].allowed_roles == internal_role_values
