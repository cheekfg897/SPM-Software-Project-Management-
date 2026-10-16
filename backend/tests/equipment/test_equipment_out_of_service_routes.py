"""Unit tests for the routes of SCRUM-47, and who may call them.

Only Technical Support Staff take units out of service, put them back, or list them
(SCRUM-47: the story is theirs). Everyone else is refused with a 403 before any service
runs. The *registered* view functions are called inside a request context, so the real
decorators run; the services are replaced with mocks.
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
from app.modules.equipment.models import OutOfServiceReason

pytestmark = pytest.mark.scrum_47

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

#: ``token_for`` mints the user id 999, which a token carries as text.
CALLER_ID = "999"
TYPES_PATH = "/api/equipment/types/2/out-of-service"
ENTRY_PATH = "/api/equipment/out-of-service/12/return"

# (endpoint, method, path, route arguments, service it calls, success status)
ROUTES = [
    (
        "equipment.mark_out_of_service",
        "POST",
        TYPES_PATH,
        {"equipment_type_id": 2},
        "mark_out_of_service",
        201,
    ),
    (
        "equipment.list_out_of_service",
        "GET",
        TYPES_PATH,
        {"equipment_type_id": 2},
        "list_out_of_service",
        200,
    ),
    (
        "equipment.return_to_service",
        "POST",
        ENTRY_PATH,
        {"entry_id": 12},
        "return_to_service",
        200,
    ),
]
ROUTE_PARAMS = ("endpoint", "method", "path", "arguments", "service", "status")
ROUTE_IDS = [route[0] for route in ROUTES]

OTHER_ROLES = [
    pytest.param(*route, role, id=f"{route[0]}-{role.value}")
    for route in ROUTES
    for role in sorted(ALL_ROLES - {Role.TECHNICAL_SUPPORT_STAFF}, key=lambda role: role.value)
]

SHOWN_ENTRY = services.OutOfServiceAsShown(
    id=12,
    equipment_type_id=2,
    quantity=3,
    reason=OutOfServiceReason.UNDER_MAINTENANCE,
    recorded_by="Alice Example",
    recorded_at=datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc),
    resolved_by=None,
    resolved_at=None,
)
ENTRY_JSON = {
    "id": 12,
    "equipment_type_id": 2,
    "quantity": 3,
    "reason": "under_maintenance",
    "recorded_by": "Alice Example",
    "recorded_at": "2026-10-10T10:00:00+08:00",
    "resolved_by": None,
    "resolved_at": None,
}


@pytest.fixture()
def mock_services(replace_services: ReplaceServices) -> dict[str, MagicMock]:
    """Replace every service these routes call with a mock."""
    return replace_services(
        services,
        {
            "mark_out_of_service": SHOWN_ENTRY,
            "list_out_of_service": [SHOWN_ENTRY],
            "return_to_service": SHOWN_ENTRY,
        },
    )


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_technical_support_gets_through_to_the_service(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    arguments: dict[str, int],
    service: str,
    status: int,
) -> None:
    _, response_status = call_route(
        endpoint, method, path, arguments, token_for(role=Role.TECHNICAL_SUPPORT_STAFF)
    )

    assert response_status == status
    mock_services[service].assert_called_once()


@pytest.mark.parametrize((*ROUTE_PARAMS, "role"), OTHER_ROLES, ids=[p.id for p in OTHER_ROLES])
def test_any_other_role_is_403_before_any_service(
    call_route: CallRoute,
    token_for: TokenFor,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    arguments: dict[str, int],
    service: str,
    status: int,
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(endpoint, method, path, arguments, token_for(role=role))

    assert exc_info.value.status_code == 403
    for mock in mock_services.values():
        mock.assert_not_called()


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_a_request_without_a_token_is_401_before_any_service(
    call_route: CallRoute,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    path: str,
    arguments: dict[str, int],
    service: str,
    status: int,
) -> None:
    with pytest.raises(AuthenticationError):
        call_route(endpoint, method, path, arguments, token=None)

    for mock in mock_services.values():
        mock.assert_not_called()


@pytest.mark.parametrize(ROUTE_PARAMS, ROUTES, ids=ROUTE_IDS)
def test_a_route_allows_exactly_technical_support(
    app: Flask,
    endpoint: str,
    method: str,
    path: str,
    arguments: dict[str, int],
    service: str,
    status: int,
) -> None:
    allowed = app.view_functions[endpoint].allowed_roles

    assert allowed == frozenset({Role.TECHNICAL_SUPPORT_STAFF.value})


def test_marking_passes_the_type_the_body_and_the_caller_and_returns_the_entry(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.mark_out_of_service",
        "POST",
        TYPES_PATH,
        {"equipment_type_id": 2},
        token_for(role=Role.TECHNICAL_SUPPORT_STAFF),
    )

    assert response.get_json() == ENTRY_JSON
    # The body is always {} in the helper; the caller is the token's user.
    mock_services["mark_out_of_service"].assert_called_once_with(2, {}, recorded_by=CALLER_ID)


def test_returning_passes_the_entry_and_the_caller_and_returns_it(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.return_to_service",
        "POST",
        ENTRY_PATH,
        {"entry_id": 12},
        token_for(role=Role.TECHNICAL_SUPPORT_STAFF),
    )

    assert response.get_json() == ENTRY_JSON
    mock_services["return_to_service"].assert_called_once_with(12, resolved_by=CALLER_ID)


def test_the_list_route_returns_each_entry_the_service_found(
    call_route: CallRoute, token_for: TokenFor, mock_services: dict[str, MagicMock]
) -> None:
    response, _ = call_route(
        "equipment.list_out_of_service",
        "GET",
        TYPES_PATH,
        {"equipment_type_id": 2},
        token_for(role=Role.TECHNICAL_SUPPORT_STAFF),
    )

    assert response.get_json() == [ENTRY_JSON]
    mock_services["list_out_of_service"].assert_called_once_with(2)
