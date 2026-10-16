"""Unit tests for SCRUM-55's route, ``GET /requests/<reference>/registrations``.

Only Event Organisers and Event Coordinators may call it; the service decides which
events each may see (``test_registrant_list.py``). An Attendee is refused here, before
the service is reached, so they cannot see another Attendee's details (AC5).

The view function is called inside a request context, so the real decorators run. The
service is replaced with a mock: a refused request must be stopped before it is called.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.registration import routes
from app.modules.registration.models import RegistrationStatus
from app.modules.registration.services import Registrant, RegistrantList

pytestmark = pytest.mark.scrum_55

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

ENDPOINT = "registration.view_registrants"
PATH = "/api/events/requests/EVR-OPEN0001/registrations"
VIEW_KWARGS = {"reference": "EVR-OPEN0001"}

#: Every role that may not open the list, Attendee included, in a stable order.
REFUSED_ROLES = sorted(
    ALL_ROLES - {Role.EVENT_ORGANISER, Role.EVENT_COORDINATOR}, key=lambda role: role.value
)


@pytest.fixture()
def registrants_service(replace_services: ReplaceServices, now: datetime) -> MagicMock:
    """Replace ``list_registrants`` with a mock returning one registrant."""
    registrant = Registrant(
        name="Alice Tan",
        email="alice@example.com",
        registered_at=now,
        status=RegistrationStatus.REGISTERED,
    )
    listing = RegistrantList(capacity=5, registered_count=1, places_left=4, items=[registrant])
    return replace_services(routes, {"list_registrants": listing})["list_registrants"]


def test_the_route_allows_only_organisers_and_coordinators(app: Flask) -> None:
    assert app.view_functions[ENDPOINT].allowed_roles == frozenset(
        {"event_organiser", "event_coordinator"}
    )


def test_the_list_is_shown_with_the_count_against_the_capacity(
    call_route: CallRoute,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    registrants_service: MagicMock,
) -> None:
    token = token_for(make_user(role=Role.EVENT_ORGANISER, user_id=7))

    response = call_route(ENDPOINT, "GET", PATH, VIEW_KWARGS, token)

    assert response.status_code == 200
    assert response.get_json() == {
        "capacity": 5,
        "registered_count": 1,
        "places_left": 4,
        "items": [
            {
                "name": "Alice Tan",
                "email": "alice@example.com",
                "registered_at": "2026-10-14T12:00:00+08:00",
                "status": "registered",
            }
        ],
    }


@pytest.mark.parametrize("role", [Role.EVENT_ORGANISER, Role.EVENT_COORDINATOR])
def test_the_viewer_is_the_caller_in_the_token(
    call_route: CallRoute,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    registrants_service: MagicMock,
    role: Role,
) -> None:
    token = token_for(make_user(role=role, user_id=7))

    call_route(ENDPOINT, "GET", PATH, VIEW_KWARGS, token)

    registrants_service.assert_called_once_with("7", "EVR-OPEN0001", viewer_role=role)


@pytest.mark.parametrize("role", REFUSED_ROLES, ids=lambda role: role.value)
def test_every_other_role_including_attendees_is_refused(
    call_route: CallRoute,
    token_for: Callable[..., str],
    registrants_service: MagicMock,
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, VIEW_KWARGS, token_for(role=role))

    assert exc_info.value.status_code == 403
    registrants_service.assert_not_called()


def test_a_caller_with_no_token_is_401(
    call_route: CallRoute, registrants_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, VIEW_KWARGS, None)

    assert exc_info.value.status_code == 401
    registrants_service.assert_not_called()
