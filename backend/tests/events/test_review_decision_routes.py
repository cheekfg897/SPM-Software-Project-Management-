"""Unit tests for SCRUM-31 "Review and decide a submitted request": the routes.

``POST /api/events/requests/<reference>/review`` moves a submitted request to under
review (AC3). Event Coordinators only; the service checks the caller is the request's
own coordinator (AC5, ADR-0028). It answers ``200`` with the request, and never shows
a user id.

The *registered* view function is called inside a request context, so the real
decorators run. The service is replaced with a mock: a refused request must be
stopped before it is called.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest, EventRequestStatus

pytestmark = pytest.mark.scrum_31

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

REFERENCE = "EVR-AAAAAAAA"
VIEW_KWARGS = {"reference": REFERENCE}
REVIEW_ENDPOINT = "events.review_request"
REVIEW_PATH = f"/api/events/requests/{REFERENCE}/review"


@pytest.fixture()
def review_service(
    replace_services: ReplaceServices, make_event_request: Callable[..., EventRequest]
) -> MagicMock:
    """Replace the service with a mock that moves the request to under review."""
    reviewed = make_event_request(status=EventRequestStatus.UNDER_REVIEW, coordinator_id=3)
    mocks = replace_services(routes, {"start_event_request_review": reviewed})
    return mocks["start_event_request_review"]


# --------------------------------------------------------------------------
# AC3, AC5 — POST .../review
# --------------------------------------------------------------------------


def test_review_route_allows_only_event_coordinators(app: Flask) -> None:
    assert app.view_functions[REVIEW_ENDPOINT].allowed_roles == frozenset({"event_coordinator"})


def test_other_roles_cannot_start_a_review(
    call_route: CallRoute,
    token_for: Callable[..., str],
    review_service: MagicMock,
    non_coordinator_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(
            REVIEW_ENDPOINT, "POST", REVIEW_PATH, VIEW_KWARGS, token_for(role=non_coordinator_role)
        )

    assert exc_info.value.status_code == 403
    review_service.assert_not_called()


def test_starting_a_review_without_a_token_is_401(
    call_route: CallRoute, review_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(REVIEW_ENDPOINT, "POST", REVIEW_PATH, VIEW_KWARGS, None)

    assert exc_info.value.status_code == 401
    review_service.assert_not_called()


def test_review_route_returns_the_request_under_review(
    call_route: CallRoute, token_for: Callable[..., str], review_service: MagicMock
) -> None:
    response, status = call_route(
        REVIEW_ENDPOINT, "POST", REVIEW_PATH, VIEW_KWARGS, token_for(role=Role.EVENT_COORDINATOR)
    )

    assert status == 200
    # The caller is the coordinator, taken from their token; the body is not read.
    review_service.assert_called_once_with("999", REFERENCE)
    body = response.get_json()
    assert (body["reference"], body["status"]) == (REFERENCE, "under_review")
    assert {"id", "organiser_id", "coordinator_id"}.isdisjoint(body)
