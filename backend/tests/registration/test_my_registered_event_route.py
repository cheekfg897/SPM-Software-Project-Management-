"""Unit tests for ``GET /api/events/registrations/<reference>`` (SCRUM-24 AC11).

Only an Attendee calls it, for an event they registered for; every other role is
refused before the service runs, and the caller is the one in the token (ADR-0109). The
body is the catalogue's public event fields, the venues, the registration and whether
Withdraw is offered, and nothing internal.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
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
from app.modules.registration.services import MyRegisteredEvent
from app.modules.venue.services import BookedVenue
from tests.registration.conftest import NON_ATTENDEE_ROLES

pytestmark = pytest.mark.scrum_24

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

ENDPOINT = "registration.view_my_registered_event"
REFERENCE = "EVR-7K2M9Q4A"
PATH = f"/api/events/registrations/{REFERENCE}"
KWARGS = {"reference": REFERENCE}

STARTS_AT = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)


@pytest.fixture()
def attendee_token(token_for: Callable[..., str], make_user: Callable[..., User]) -> str:
    """A token for attendee 21."""
    return token_for(make_user(role=Role.ATTENDEE, user_id=21))


@pytest.fixture()
def page_service(replace_services: ReplaceServices, now: datetime) -> MagicMock:
    """Replace ``get_my_registered_event`` with a mock answering one event."""
    shown = MyRegisteredEvent(
        id=41,
        reference=REFERENCE,
        name="Jazz by the Bay",
        description="An evening of music.",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        event_status="confirmed",
        venues=[BookedVenue(name="Main Hall", location="Building A, Level 1")],
        status=RegistrationStatus.REGISTERED,
        registered_at=now,
        withdrawn_at=None,
        withdrawals_close_at=STARTS_AT - timedelta(days=1),
        can_withdraw=True,
        is_being_reviewed=False,
    )
    return replace_services(routes, {"get_my_registered_event": shown})["get_my_registered_event"]


def test_the_event_is_shown_with_its_venues_registration_and_withdrawal(
    call_route: CallRoute, page_service: MagicMock, attendee_token: str
) -> None:
    response = call_route(ENDPOINT, "GET", PATH, KWARGS, attendee_token)

    assert response.status_code == 200
    assert response.get_json() == {
        "id": 41,
        "reference": REFERENCE,
        "name": "Jazz by the Bay",
        "description": "An evening of music.",
        "starts_at": "2026-10-20T19:30:00+08:00",
        "ends_at": "2026-10-20T22:00:00+08:00",
        "event_status": "confirmed",
        "venues": [{"name": "Main Hall", "location": "Building A, Level 1"}],
        "status": "registered",
        "registered_at": "2026-10-14T12:00:00+08:00",
        "withdrawn_at": None,
        "withdrawals_close_at": "2026-10-19T19:30:00+08:00",
        "can_withdraw": True,
        "is_being_reviewed": False,
    }


def test_the_event_is_looked_up_for_the_attendee_in_the_token(
    call_route: CallRoute, page_service: MagicMock, attendee_token: str
) -> None:
    call_route(ENDPOINT, "GET", PATH, KWARGS, attendee_token)

    page_service.assert_called_once_with("21", REFERENCE)


def test_the_route_allows_only_attendees(app: Flask) -> None:
    assert app.view_functions[ENDPOINT].allowed_roles == frozenset({"attendee"})


def test_the_refused_roles_and_the_attendee_are_every_role() -> None:
    assert {*NON_ATTENDEE_ROLES, Role.ATTENDEE} == ALL_ROLES


def test_every_other_role_is_refused_before_the_service_runs(
    call_route: CallRoute,
    token_for: Callable[..., str],
    page_service: MagicMock,
    non_attendee_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, KWARGS, token_for(role=non_attendee_role))

    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "You do not have permission to perform this action."
    page_service.assert_not_called()


def test_a_visitor_is_asked_to_sign_in_before_the_service_runs(
    call_route: CallRoute, page_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, KWARGS, None)

    assert exc_info.value.status_code == 401
    page_service.assert_not_called()
