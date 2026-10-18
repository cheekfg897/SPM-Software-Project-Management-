"""Unit tests for SCRUM-85 — only Technical Support record preparation details (AC1).

The registered view runs inside a request context, so the real decorators decide; a
refused caller must never reach the service layer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.equipment import services
from app.modules.equipment.models import PreparationStatus

pytestmark = pytest.mark.scrum_85

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

NON_TECHNICAL_SUPPORT_ROLES = sorted(
    ALL_ROLES - {Role.TECHNICAL_SUPPORT_STAFF}, key=lambda role: role.value
)

#: An id no fixture uses, so a route that hard-codes its user can't pass by chance.
TECHNICAL_SUPPORT_ID = 42
RESERVATION_ID = 12
PATH = f"/api/equipment/reservations/{RESERVATION_ID}/preparation"
ENDPOINT = "equipment.update_preparation_details"
VIEW_KWARGS = {"reservation_id": RESERVATION_ID}

PREPARED = services.ReservationAsShown(
    id=RESERVATION_ID,
    equipment_type_id=2,
    equipment_type_name="Projector",
    quantity=4,
    starts_at=datetime(2026, 10, 15, 1, 0, tzinfo=UTC),
    ends_at=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
    reserved_by="Alice Example",
    created_at=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
    needs_attention=False,
    preparation_status=PreparationStatus.READY,
    preparation_notes="All tested.",
)


@pytest.fixture()
def mock_services(replace_services: ReplaceServices) -> dict[str, MagicMock]:
    return replace_services(services, {"update_preparation_details": PREPARED})


@pytest.mark.parametrize("role", NON_TECHNICAL_SUPPORT_ROLES, ids=lambda role: role.value)
def test_a_role_other_than_technical_support_is_refused_with_403(
    call_route: CallRoute,
    token_for: Callable[..., str],
    mock_services: dict[str, MagicMock],
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError):
        call_route(ENDPOINT, "PUT", PATH, VIEW_KWARGS, token_for(role=role))

    mock_services["update_preparation_details"].assert_not_called()


def test_a_caller_without_a_token_is_refused_with_401(
    call_route: CallRoute, mock_services: dict[str, MagicMock]
) -> None:
    with pytest.raises(AuthenticationError):
        call_route(ENDPOINT, "PUT", PATH, VIEW_KWARGS, None)

    mock_services["update_preparation_details"].assert_not_called()


def test_technical_support_get_200_with_the_updated_reservation(
    call_route: CallRoute,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    mock_services: dict[str, MagicMock],
) -> None:
    token = token_for(make_user(role=Role.TECHNICAL_SUPPORT_STAFF, user_id=TECHNICAL_SUPPORT_ID))

    response, status = call_route(
        ENDPOINT, "PUT", PATH, VIEW_KWARGS, token, body={"status": "ready"}
    )

    body = response.get_json()
    assert status == 200
    assert (body["id"], body["preparation_status"], body["preparation_notes"]) == (
        RESERVATION_ID,
        "ready",
        "All tested.",
    )
    mock_services["update_preparation_details"].assert_called_once_with(
        RESERVATION_ID, {"status": "ready"}, updated_by=TECHNICAL_SUPPORT_ID
    )
