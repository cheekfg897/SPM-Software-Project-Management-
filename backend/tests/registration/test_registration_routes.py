"""Unit tests for SCRUM-52's routes: the catalogue, registering and my registrations.

``GET /api/events/catalogue`` is public (a valid token only decides ``is_registered``).
``POST /api/events/catalogue/<id>/registrations`` and ``GET /api/events/registrations``
are for Attendees only. Each answers as ADR-0032 says, and the caller's identity comes
from the token, never from the request.

The *registered* view functions are called inside a request context, so the real
decorators run. The services are replaced with mocks: a refused request must be stopped
before they are called.
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
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.registration import routes
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import (
    CatalogueEntry,
    CataloguePage,
    MyRegistration,
)

pytestmark = pytest.mark.scrum_52

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

CATALOGUE_ENDPOINT = "registration.browse_catalogue"
REGISTER_ENDPOINT = "registration.register_for_catalogue_event"
MINE_ENDPOINT = "registration.view_my_registrations"

REGISTER_PATH = "/api/events/catalogue/41/registrations"
REGISTER_KWARGS = {"event_id": 41}
MINE_PATH = "/api/events/registrations"

STARTS_AT = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)


@pytest.fixture()
def attendee_token(token_for: Callable[..., str], make_user: Callable[..., User]) -> str:
    """A token for attendee 21."""
    return token_for(make_user(role=Role.ATTENDEE, user_id=21))


@pytest.fixture()
def catalogue_service(replace_services: ReplaceServices) -> MagicMock:
    """Replace ``list_catalogue`` with a mock answering one page with one event."""
    entry = CatalogueEntry(
        id=41,
        reference="EVR-7K2M9Q4A",
        name="Jazz by the Bay",
        description="An evening of music.",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        capacity=200,
        places_left=12,
        is_full=False,
        is_registered=True,
    )
    page = CataloguePage(items=[entry], page=2, page_size=1, total=3, total_pages=3)
    return replace_services(routes, {"list_catalogue": page})["list_catalogue"]


@pytest.fixture()
def register_service(replace_services: ReplaceServices, now: datetime) -> MagicMock:
    """Replace ``register_for_event`` with a mock returning a registration."""
    registration = Registration(
        id=7,
        event_request_id=41,
        attendee_id=21,
        status=RegistrationStatus.REGISTERED,
        registered_at=now,
    )
    return replace_services(routes, {"register_for_event": registration})["register_for_event"]


@pytest.fixture()
def my_registrations_service(replace_services: ReplaceServices, now: datetime) -> MagicMock:
    """Replace ``list_my_registrations`` with a mock returning one registration."""
    row = MyRegistration(
        event_id=41,
        name="Jazz by the Bay",
        starts_at=STARTS_AT,
        status=RegistrationStatus.REGISTERED,
        registered_at=now,
    )
    return replace_services(routes, {"list_my_registrations": [row]})["list_my_registrations"]


# --------------------------------------------------------------------------
# GET /api/events/catalogue — public
# --------------------------------------------------------------------------


def test_the_catalogue_is_shown_in_the_shape_adr_0032_gives(
    call_route: CallRoute, catalogue_service: MagicMock
) -> None:
    response = call_route(CATALOGUE_ENDPOINT, "GET", "/api/events/catalogue", {}, None)

    assert response.status_code == 200
    assert response.get_json() == {
        "items": [
            {
                "id": 41,
                "reference": "EVR-7K2M9Q4A",
                "name": "Jazz by the Bay",
                "description": "An evening of music.",
                "starts_at": "2026-10-20T19:30:00+08:00",
                "ends_at": "2026-10-20T22:00:00+08:00",
                "venue": None,
                "capacity": 200,
                "places_left": 12,
                "is_full": False,
                "is_registered": True,
            }
        ],
        "page": 2,
        "page_size": 1,
        "total": 3,
        "total_pages": 3,
    }


def test_a_visitor_with_no_token_sees_the_catalogue(
    call_route: CallRoute, catalogue_service: MagicMock
) -> None:
    call_route(CATALOGUE_ENDPOINT, "GET", "/api/events/catalogue", {}, None)

    catalogue_service.assert_called_once_with({}, None)


def test_a_signed_in_user_is_passed_so_is_registered_can_be_theirs(
    call_route: CallRoute, catalogue_service: MagicMock, attendee_token: str
) -> None:
    call_route(CATALOGUE_ENDPOINT, "GET", "/api/events/catalogue", {}, attendee_token)

    catalogue_service.assert_called_once_with({}, "21")


def test_a_token_that_is_not_valid_is_read_as_a_visitor(
    call_route: CallRoute, catalogue_service: MagicMock
) -> None:
    response = call_route(CATALOGUE_ENDPOINT, "GET", "/api/events/catalogue", {}, "not-a-token")

    assert response.status_code == 200
    catalogue_service.assert_called_once_with({}, None)


def test_the_query_string_is_handed_to_the_service(
    call_route: CallRoute, catalogue_service: MagicMock
) -> None:
    path = "/api/events/catalogue?q=jazz&when=this_week&page=2"

    call_route(CATALOGUE_ENDPOINT, "GET", path, {}, None)

    catalogue_service.assert_called_once_with({"q": "jazz", "when": "this_week", "page": "2"}, None)


# --------------------------------------------------------------------------
# POST /api/events/catalogue/<id>/registrations — attendees only
# --------------------------------------------------------------------------


def test_register_route_allows_only_attendees(app: Flask) -> None:
    assert app.view_functions[REGISTER_ENDPOINT].allowed_roles == frozenset({"attendee"})


def test_registering_answers_201_with_the_registration(
    call_route: CallRoute, register_service: MagicMock, attendee_token: str
) -> None:
    response, status = call_route(
        REGISTER_ENDPOINT, "POST", REGISTER_PATH, REGISTER_KWARGS, attendee_token
    )

    assert status == 201
    assert response.get_json() == {
        "id": 7,
        "event_id": 41,
        "status": "registered",
        "registered_at": "2026-10-14T12:00:00+08:00",
    }


def test_the_attendee_registered_is_the_one_in_the_token(
    call_route: CallRoute, register_service: MagicMock, attendee_token: str
) -> None:
    call_route(REGISTER_ENDPOINT, "POST", REGISTER_PATH, REGISTER_KWARGS, attendee_token)

    register_service.assert_called_once_with("21", 41)


def test_other_roles_cannot_register(
    call_route: CallRoute,
    token_for: Callable[..., str],
    register_service: MagicMock,
    non_attendee_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(
            REGISTER_ENDPOINT,
            "POST",
            REGISTER_PATH,
            REGISTER_KWARGS,
            token_for(role=non_attendee_role),
        )

    assert exc_info.value.status_code == 403
    register_service.assert_not_called()


def test_registering_without_a_token_is_401(
    call_route: CallRoute, register_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(REGISTER_ENDPOINT, "POST", REGISTER_PATH, REGISTER_KWARGS, None)

    assert exc_info.value.status_code == 401
    register_service.assert_not_called()


# --------------------------------------------------------------------------
# GET /api/events/registrations — attendees only, their own
# --------------------------------------------------------------------------


def test_my_registrations_route_allows_only_attendees(app: Flask) -> None:
    assert app.view_functions[MINE_ENDPOINT].allowed_roles == frozenset({"attendee"})


def test_my_registrations_are_listed_with_the_event_and_status(
    call_route: CallRoute, my_registrations_service: MagicMock, attendee_token: str
) -> None:
    response = call_route(MINE_ENDPOINT, "GET", MINE_PATH, {}, attendee_token)

    assert response.status_code == 200
    assert response.get_json() == {
        "registrations": [
            {
                "event_id": 41,
                "name": "Jazz by the Bay",
                "starts_at": "2026-10-20T19:30:00+08:00",
                "status": "registered",
                "registered_at": "2026-10-14T12:00:00+08:00",
            }
        ]
    }


def test_my_registrations_are_the_callers_own(
    call_route: CallRoute, my_registrations_service: MagicMock, attendee_token: str
) -> None:
    call_route(MINE_ENDPOINT, "GET", MINE_PATH, {}, attendee_token)

    my_registrations_service.assert_called_once_with("21")


def test_other_roles_cannot_list_registrations(
    call_route: CallRoute,
    token_for: Callable[..., str],
    my_registrations_service: MagicMock,
    non_attendee_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(MINE_ENDPOINT, "GET", MINE_PATH, {}, token_for(role=non_attendee_role))

    assert exc_info.value.status_code == 403
    my_registrations_service.assert_not_called()


def test_listing_registrations_without_a_token_is_401(
    call_route: CallRoute, my_registrations_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(MINE_ENDPOINT, "GET", MINE_PATH, {}, None)

    assert exc_info.value.status_code == 401
    my_registrations_service.assert_not_called()
