"""Unit tests for who may record an equipment outcome: Technical Support (SCRUM-48).

The route is a permission rule, not a presentation one. The tests call the registered
view inside a request context, where the real decorator runs, with the service replaced
by a mock that a refused call must never reach.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EquipmentLineStatus, EventEquipmentLine
from app.modules.events.services import EquipmentLineAsShown

pytestmark = pytest.mark.scrum_48

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
LINE_ID = 12
ENDPOINT = "events.record_outcome"
PATH = f"/api/events/requests/{REFERENCE}/equipment/{LINE_ID}/outcome"
VIEW_KWARGS = {"reference": REFERENCE, "line_id": LINE_ID}

#: Every role but Technical Support, so a new role is refused unless a test says not.
OTHER_ROLES = sorted(ALL_ROLES - {Role.TECHNICAL_SUPPORT_STAFF}, key=lambda role: role.value)


@pytest.fixture()
def outcome_service(replace_services: ReplaceServices) -> MagicMock:
    """Replace the service with one answering a fulfilled line and its reviewer."""
    line = EventEquipmentLine(
        id=LINE_ID,
        equipment_type_id=1,
        quantity=10,
        status=EquipmentLineStatus.FULFILLED,
    )
    shown = EquipmentLineAsShown(
        id=LINE_ID,
        equipment_type_id=1,
        quantity=10,
        notes=None,
        status=EquipmentLineStatus.FULFILLED,
        provided_quantity=10,
        shortfall=0,
        outcome_note=None,
        reviewed_by="Alice Example",
        reviewed_at=datetime(2026, 10, 13, 9, 30, tzinfo=UTC),
    )
    mocks = replace_services(
        routes, {"record_equipment_outcome": line, "equipment_lines_as_shown": [shown]}
    )
    return mocks["record_equipment_outcome"]


def test_the_route_allows_only_technical_support_staff(app: Flask) -> None:
    allowed = app.view_functions[ENDPOINT].allowed_roles

    assert allowed == frozenset({Role.TECHNICAL_SUPPORT_STAFF.value})


@pytest.mark.parametrize("role", OTHER_ROLES, ids=lambda role: role.value)
def test_every_other_role_is_refused(
    call_route: CallRoute, token_for: Callable[..., str], outcome_service: MagicMock, role: Role
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=role))

    assert exc_info.value.status_code == 403
    outcome_service.assert_not_called()


def test_a_call_without_a_token_is_401(call_route: CallRoute, outcome_service: MagicMock) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "POST", PATH, VIEW_KWARGS, None)

    assert exc_info.value.status_code == 401
    outcome_service.assert_not_called()


def test_technical_support_records_the_outcome_as_themselves(
    call_route: CallRoute, token_for: Callable[..., str], outcome_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "POST", PATH, VIEW_KWARGS, token_for(role=Role.TECHNICAL_SUPPORT_STAFF)
    )

    assert status == 200
    outcome_service.assert_called_once_with("999", REFERENCE, LINE_ID, {})
    body = response.get_json()
    assert body["id"] == LINE_ID
    assert (body["provided_quantity"], body["shortfall"], body["reviewed_by"]) == (
        10,
        0,
        "Alice Example",
    )
