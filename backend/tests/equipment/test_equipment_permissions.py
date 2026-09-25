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
        "/api/equipment/types/1",
        {"equipment_type_id": 1},
        "update_equipment_type",
        200,
    ),
]
WRITE_ROUTE_IDS = [route[0] for route in WRITE_ROUTES]
WRITE_PARAMS = ("endpoint", "method", "path", "view_kwargs", "service", "status")

# (endpoint, path, view kwargs)
READ_ROUTES = [
    ("equipment.list_equipment_types", "/api/equipment/types", {}),
    ("equipment.get_equipment_type", "/api/equipment/types/1", {"equipment_type_id": 1}),
]
READ_ROUTE_IDS = [route[0] for route in READ_ROUTES]

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

    _, response_status = call_route(endpoint, method, path, view_kwargs, token)

    assert response_status == status
    mock_services[service].assert_called_once()


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
    with pytest.raises(AuthorizationError):
        call_route(endpoint, "GET", path, view_kwargs, token_for(role=role))

    for mock in mock_services.values():
        mock.assert_not_called()


@pytest.mark.parametrize("endpoint", READ_ROUTE_IDS)
def test_read_route_allows_only_internal_roles(app: Flask, endpoint: str) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    internal_role_values = frozenset(role.value for role in INTERNAL_ROLES)

    assert app.view_functions[endpoint].allowed_roles == internal_role_values
