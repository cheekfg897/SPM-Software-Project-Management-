"""Unit tests for SCRUM-69 "Enable registration for an event and set its capacity".

The route: ``PATCH /api/events/requests/<reference>/registration`` is for Event
Coordinators only; the service checks the caller is the event's own coordinator and
every rule on the settings (ADR-0043, ADR-0086). It answers ``200`` with the settings,
the withdrawal cut-off in business time, and never shows a user id.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused request must be
stopped before it is called.
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
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_69

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.update_registration"
PATH = f"/api/events/requests/{REFERENCE}/registration"
VIEW_KWARGS = {"reference": REFERENCE}


@pytest.fixture()
def update_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock returning an event open for 100 places.

    Withdrawals close at 18:00 in Singapore the evening before it starts.
    """
    event_request = make_event_request(status=EventRequestStatus.CONFIRMED, coordinator_id=3)
    event_request.registration_enabled = True
    event_request.registration_capacity = 100
    event_request.withdrawal_cut_off = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
    mocks = replace_services(routes, {"update_registration_settings": event_request})
    return mocks["update_registration_settings"]


def test_registration_route_allows_only_event_coordinators(app: Flask) -> None:
    assert app.view_functions[ENDPOINT].allowed_roles == frozenset({"event_coordinator"})


def test_other_roles_cannot_change_the_settings(
    call_route: CallRoute,
    token_for: Callable[..., str],
    update_service: MagicMock,
    non_coordinator_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "PATCH", PATH, VIEW_KWARGS, token_for(role=non_coordinator_role))

    assert exc_info.value.status_code == 403
    update_service.assert_not_called()


def test_changing_the_settings_without_a_token_is_401(
    call_route: CallRoute, update_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "PATCH", PATH, VIEW_KWARGS, None)

    assert exc_info.value.status_code == 401
    update_service.assert_not_called()


def test_registration_route_returns_the_settings(
    call_route: CallRoute, token_for: Callable[..., str], update_service: MagicMock
) -> None:
    body = {
        "registration_enabled": True,
        "registration_capacity": 100,
        "withdrawal_cut_off": "2026-10-14T18:00:00+08:00",
    }

    response, status = call_route(
        ENDPOINT, "PATCH", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR), body=body
    )

    assert status == 200
    # The caller is the actor, taken from their token; the body is passed on as sent.
    update_service.assert_called_once_with("999", REFERENCE, body)
    assert response.get_json() == {
        "reference": REFERENCE,
        "registration_required": False,
        "registration_enabled": True,
        "registration_capacity": 100,
        "withdrawal_cut_off": "2026-10-14T18:00:00+08:00",
    }
