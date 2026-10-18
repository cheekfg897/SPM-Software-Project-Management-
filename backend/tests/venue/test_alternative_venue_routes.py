"""Unit tests for SCRUM-92's routes and responses (ADR-0053).

The deactivate route passes its body to the service, which needs the category and note
(AC9). A booking request shows whether it needs an alternative venue, each reason with
its period in business time, and the arrangement it replaces (AC1, AC6). Routes are
called through the registered view with the service mocked, as the other venue route
tests are.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.auth.permissions import Role
from app.modules.venue import services
from app.modules.venue.models import (
    AlternativeVenueFlag,
    BookingRequestStatus,
    UnavailabilityCategory,
    Venue,
)
from app.modules.venue.schemas import BookingRequestAsShown, VenueBookingRequestSchema
from tests.venue.conftest import DEACTIVATION

pytestmark = pytest.mark.scrum_92

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]


def _flag(
    category: UnavailabilityCategory, starts_at: datetime, ends_at: datetime | None
) -> AlternativeVenueFlag:
    return AlternativeVenueFlag(
        category=category, reason="Lift broken.", starts_at=starts_at, ends_at=ends_at
    )


def test_the_deactivate_route_passes_the_category_and_note_to_the_service(
    call_route: CallRoute,
    token_for: Callable[..., str],
    replace_services: ReplaceServices,
    make_venue: Callable[..., Venue],
) -> None:
    mocks = replace_services(services, {"deactivate_venue": make_venue(is_active=False)})

    response, status = call_route(
        "venue.deactivate_venue",
        "POST",
        "/api/venues/42/deactivate",
        {"venue_id": 42},
        token_for(role=Role.VENUE_STAFF),
        body=DEACTIVATION,
    )

    assert status == 200
    mocks["deactivate_venue"].assert_called_once_with(42, DEACTIVATION)
    assert response.get_json()["is_active"] is False


def test_a_flagged_request_shows_each_reason_and_period_in_business_time(
    shown: BookingRequestAsShown,
) -> None:
    shown.request.status = BookingRequestStatus.APPROVED
    shown.request.replaces_request_id = 7
    shown.request.flags = [
        _flag(
            UnavailabilityCategory.EQUIPMENT_FAILURE,
            datetime(2026, 11, 1, 2, 0, tzinfo=UTC),
            datetime(2026, 11, 1, 3, 0, tzinfo=UTC),
        ),
        _flag(UnavailabilityCategory.RENOVATION, datetime(2026, 10, 20, 4, 0, tzinfo=UTC), None),
    ]

    body = VenueBookingRequestSchema().dump(shown)

    assert body["needs_alternative_venue"] is True
    assert body["replaces_request_id"] == 7
    assert body["unavailability"] == [
        {
            "category": "equipment_failure",
            "reason": "Lift broken.",
            "starts_at": "2026-11-01T10:00:00+08:00",
            "ends_at": "2026-11-01T11:00:00+08:00",
        },
        {
            "category": "renovation",
            "reason": "Lift broken.",
            "starts_at": "2026-10-20T12:00:00+08:00",
            "ends_at": None,
        },
    ]


def test_a_released_request_keeps_its_reasons_but_needs_nothing(
    shown: BookingRequestAsShown,
) -> None:
    shown.request.status = BookingRequestStatus.RELEASED
    shown.request.flags = [
        _flag(UnavailabilityCategory.OTHER, datetime(2026, 11, 1, 2, 0, tzinfo=UTC), None)
    ]

    body = VenueBookingRequestSchema().dump(shown)

    assert body["status"] == "released"
    assert body["needs_alternative_venue"] is False
    assert len(body["unavailability"]) == 1
