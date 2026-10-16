"""Unit tests for SCRUM-33 "Update event information and flag significant changes".

``GET /api/events/requests/<reference>/history``: internal roles and Event
Organisers may open it; an Attendee gets ``403`` (ADR-0025). Passes the
caller's role on to the service, and shows ``occurred_at`` in business time
(ADR-0009). The service is replaced with a mock: a refused request must be stopped
before it is called.
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
from app.modules.events.models import EventHistoryKind
from app.modules.events.services import HistoryEntryAsShown

pytestmark = pytest.mark.scrum_33

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]

REFERENCE = "EVR-AAAAAAAA"
ENDPOINT = "events.list_history"
PATH = f"/api/events/requests/{REFERENCE}/history"
VIEW_KWARGS = {"reference": REFERENCE}
ALLOWED_ROLE_VALUES = frozenset(
    {
        "event_coordinator",
        "event_coordinator_lead",
        "venue_staff",
        "technical_support_staff",
        "safety_officer",
        "event_organiser",
    }
)


@pytest.fixture()
def history_service(replace_services: ReplaceServices) -> MagicMock:
    """Replace the service with a mock listing one ``field_changed`` entry."""
    entry = HistoryEntryAsShown(
        kind=EventHistoryKind.FIELD_CHANGED,
        occurred_at=datetime(2026, 9, 15, 2, 30, tzinfo=timezone.utc),
        actor_name="Coordinator Three",
        details={
            "field": "expected_attendance",
            "previous_value": 250,
            "new_value": 300,
            "significant": True,
        },
    )
    mocks = replace_services(routes, {"list_event_history": [entry]})
    return mocks["list_event_history"]


def test_history_route_allows_internal_roles_and_organisers(app: Flask) -> None:
    assert app.view_functions[ENDPOINT].allowed_roles == ALLOWED_ROLE_VALUES


def test_an_attendee_cannot_open_the_history(
    call_route: CallRoute, token_for: TokenFor, history_service: MagicMock
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, VIEW_KWARGS, token_for(role=Role.ATTENDEE))

    assert exc_info.value.status_code == 403
    history_service.assert_not_called()


def test_opening_the_history_without_a_token_is_401(
    call_route: CallRoute, history_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, VIEW_KWARGS, None)

    assert exc_info.value.status_code == 401
    history_service.assert_not_called()


def test_history_route_passes_the_callers_role_and_shows_business_time(
    call_route: CallRoute, token_for: TokenFor, history_service: MagicMock
) -> None:
    response, status = call_route(
        ENDPOINT, "GET", PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR)
    )

    assert status == 200
    history_service.assert_called_once_with("999", REFERENCE, viewer_role=Role.EVENT_COORDINATOR)
    assert response.get_json() == {
        "history": [
            {
                "kind": "field_changed",
                "occurred_at": "2026-09-15T10:30:00+08:00",
                "actor_name": "Coordinator Three",
                "details": {
                    "field": "expected_attendance",
                    "previous_value": 250,
                    "new_value": 300,
                    "significant": True,
                },
            }
        ]
    }
