"""Unit tests for SCRUM-97 "Submit an event for operational safety check" (B): route.

``GET /api/events/requests/awaiting-safety-review`` is the Safety Officer's list of
events awaiting review, with each event's venues, accessibility needs and equipment
(AC5, AC6, ADR-0047). Only Safety Officers can open it. The service is in
``test_safety_review_list.py``.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused caller must be stopped
before it is called.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EquipmentLineStatus, EventRequest, EventRequestStatus
from app.modules.events.services import EventAwaitingSafetyReview, SafetyReviewEquipment
from app.modules.venue.services import ArrangedVenue

pytestmark = pytest.mark.scrum_97

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

ENDPOINT = "events.list_events_awaiting_review"
PATH = "/api/events/requests/awaiting-safety-review"
NON_SAFETY_OFFICER_ROLES = sorted(ALL_ROLES - {Role.SAFETY_OFFICER}, key=lambda role: role.value)


@pytest.fixture()
def list_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock listing one event with a venue and a request."""
    event_request = make_event_request(status=EventRequestStatus.SAFETY_REVIEW)
    event_request.accessibility_needs = "Step-free entrance"
    venue = ArrangedVenue(
        id=31,
        name="Main Hall",
        capacity=100,
        layouts=["theatre"],
        facilities=["projector"],
        accessibility_features=["wheelchair_access"],
        starts_at=datetime(2026, 10, 15, 1, tzinfo=timezone.utc),
        ends_at=datetime(2026, 10, 15, 9, tzinfo=timezone.utc),
    )
    equipment = SafetyReviewEquipment(
        id=41,
        equipment_type_name="Projector",
        quantity=2,
        notes="Needs HDMI",
        status=EquipmentLineStatus.PARTIALLY_FULFILLED,
        provided_quantity=1,
        outcome_note="One is faulty",
    )
    listed = [EventAwaitingSafetyReview(event_request, [venue], [equipment])]
    mocks = replace_services(routes, {"list_events_awaiting_safety_review": listed})
    return mocks["list_events_awaiting_safety_review"]


@pytest.mark.parametrize("role", NON_SAFETY_OFFICER_ROLES, ids=lambda role: role.value)
def test_other_roles_cannot_open_the_list(
    call_route: CallRoute, token_for: Callable[..., str], list_service: MagicMock, role: Role
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, {}, token_for(role=role))

    assert exc_info.value.status_code == 403
    list_service.assert_not_called()


def test_a_request_without_a_token_is_refused(
    call_route: CallRoute, list_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError):
        call_route(ENDPOINT, "GET", PATH, {}, None)

    list_service.assert_not_called()


def test_a_safety_officer_gets_each_event_with_its_venues_and_equipment(
    call_route: CallRoute, token_for: Callable[..., str], list_service: MagicMock
) -> None:
    response, status = call_route(ENDPOINT, "GET", PATH, {}, token_for(role=Role.SAFETY_OFFICER))

    assert status == 200
    assert response.get_json() == {
        "events": [
            {
                "event": {
                    "reference": "EVR-AAAAAAAA",
                    "name": "Partner Summit",
                    "proposed_date": "2026-10-15",
                    "end_date": "2026-10-15",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "status": "safety_review",
                    "expected_attendance": 250,
                    "accessibility_needs": "Step-free entrance",
                },
                "venues": [
                    {
                        "id": 31,
                        "name": "Main Hall",
                        "capacity": 100,
                        "layouts": ["theatre"],
                        "facilities": ["projector"],
                        "accessibility_features": ["wheelchair_access"],
                        "starts_at": "2026-10-15T09:00:00+08:00",
                        "ends_at": "2026-10-15T17:00:00+08:00",
                    }
                ],
                "equipment": [
                    {
                        "id": 41,
                        "equipment_type_name": "Projector",
                        "quantity": 2,
                        "notes": "Needs HDMI",
                        "status": "partially_fulfilled",
                        "provided_quantity": 1,
                        "outcome_note": "One is faulty",
                    }
                ],
            }
        ]
    }


def test_an_empty_list_says_no_events_are_waiting(
    call_route: CallRoute, token_for: Callable[..., str], replace_services: ReplaceServices
) -> None:
    replace_services(routes, {"list_events_awaiting_safety_review": []})

    response, status = call_route(ENDPOINT, "GET", PATH, {}, token_for(role=Role.SAFETY_OFFICER))

    assert status == 200
    assert response.get_json() == {
        "events": [],
        "message": "No events are waiting for a safety review.",
    }
