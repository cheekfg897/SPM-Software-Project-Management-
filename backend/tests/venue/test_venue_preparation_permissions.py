"""Unit tests for SCRUM-84 — only Venue Staff may record preparation details (AC1).

The registered view runs inside a request context, so the real decorators decide; a
refused caller must never reach the service layer.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.schemas import BookingRequestAsShown

pytestmark = pytest.mark.scrum_84

#: An id no fixture uses, so a route that hard-codes its user can't pass by chance.
VENUE_STAFF_ID = 42

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

NON_VENUE_STAFF_ROLES = sorted(ALL_ROLES - {Role.VENUE_STAFF}, key=lambda role: role.value)

REQUEST_ID = 11
PATH = f"/api/venues/booking-requests/{REQUEST_ID}/preparation"
ENDPOINT = "venue.update_preparation_details"
VIEW_KWARGS = {"request_id": REQUEST_ID}


@pytest.fixture()
def mock_services(
    replace_services: ReplaceServices, shown: BookingRequestAsShown
) -> dict[str, MagicMock]:
    return replace_services(services, {"update_preparation_details": shown})


@pytest.mark.parametrize("role", NON_VENUE_STAFF_ROLES, ids=lambda role: role.value)
def test_a_role_other_than_venue_staff_is_refused_with_403(
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


def test_venue_staff_get_200_with_the_updated_booking(
    call_route: CallRoute,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    mock_services: dict[str, MagicMock],
) -> None:
    token = token_for(make_user(role=Role.VENUE_STAFF, user_id=VENUE_STAFF_ID))

    response, status = call_route(
        ENDPOINT, "PUT", PATH, VIEW_KWARGS, token, body={"status": "ready"}
    )

    assert status == 200
    assert response.get_json()["id"] == REQUEST_ID
    mock_services["update_preparation_details"].assert_called_once_with(
        REQUEST_ID, {"status": "ready"}, updated_by=VENUE_STAFF_ID
    )
