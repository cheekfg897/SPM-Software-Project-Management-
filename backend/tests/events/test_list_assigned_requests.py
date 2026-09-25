"""Unit tests for SCRUM-30 AC5: the event appears in the assigned coordinator's list.

``GET /api/events/requests/assigned`` lists the requests assigned to the calling Event
Coordinator, newest first, in the same shape as the organiser's own list (ADR-0018).
Only Event Coordinators may call it, and only ever for themselves.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest
from app.modules.events.services import list_event_requests_for_coordinator

pytestmark = pytest.mark.scrum_30

MakeEventRequest = Callable[..., EventRequest]
SubmitValidRequest = Callable[..., EventRequest]
CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]

ENDPOINT = "events.list_assigned_requests"
PATH = "/api/events/requests/assigned"


@pytest.fixture()
def list_service(
    replace_services: ReplaceServices, make_event_request: MakeEventRequest
) -> MagicMock:
    """Replace the listing service with a mock returning one request assigned to 3."""
    mocks = replace_services(
        routes,
        {"list_event_requests_for_coordinator": [make_event_request(coordinator_id=3)]},
    )
    return mocks["list_event_requests_for_coordinator"]


# --------------------------------------------------------------------------
# AC5 — the request is in its coordinator's list, and only theirs
# --------------------------------------------------------------------------


def test_a_submitted_request_appears_in_the_assigned_coordinators_list(
    saved_users: list[User], submit_valid_request: SubmitValidRequest
) -> None:
    submit_valid_request()

    assigned_to_3 = list_event_requests_for_coordinator(3)

    assert [event_request.reference for event_request in assigned_to_3] == ["EVR-AAAAAAAA"]
    assert list_event_requests_for_coordinator("9") == []


def test_the_list_holds_only_the_callers_assigned_requests(
    save: Callable[..., None], make_event_request: MakeEventRequest
) -> None:
    save(
        make_event_request(reference="EVR-AAAAAAAA", coordinator_id=3),
        make_event_request(reference="EVR-BBBBBBBB", coordinator_id=9),
        make_event_request(reference="EVR-CCCCCCCC", coordinator_id=3),
    )

    assigned_to_3 = list_event_requests_for_coordinator(3)

    # Saved in one commit, so created_at ties and the later id comes first.
    assert [event_request.reference for event_request in assigned_to_3] == [
        "EVR-CCCCCCCC",
        "EVR-AAAAAAAA",
    ]


def test_list_only_queries_the_callers_assigned_requests_newest_first(
    mock_session: MagicMock,
) -> None:
    mock_session.scalars.return_value = []

    list_event_requests_for_coordinator("3", session=mock_session)

    stmt = mock_session.scalars.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE event_requests.coordinator_id = 3" in compiled
    assert "ORDER BY event_requests.created_at DESC, event_requests.id DESC" in compiled


# --------------------------------------------------------------------------
# AC5 — the route: Event Coordinators only, always the caller's own list
# --------------------------------------------------------------------------


def test_the_assigned_path_is_matched_before_a_reference(app: Flask) -> None:
    """``assigned`` must not be read as the reference of an event request."""
    adapter = app.url_map.bind("localhost")

    assert adapter.match(PATH) == (ENDPOINT, {})


def test_list_route_allows_only_event_coordinators(app: Flask) -> None:
    assert app.view_functions[ENDPOINT].allowed_roles == frozenset({"event_coordinator"})


def test_other_roles_cannot_list_assigned_requests(
    call_route: CallRoute,
    token_for: Callable[..., str],
    list_service: MagicMock,
    non_coordinator_role: Role,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, {}, token_for(role=non_coordinator_role))

    assert exc_info.value.status_code == 403
    list_service.assert_not_called()


def test_listing_without_a_token_is_401(call_route: CallRoute, list_service: MagicMock) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        call_route(ENDPOINT, "GET", PATH, {}, None)

    assert exc_info.value.status_code == 401
    list_service.assert_not_called()


def test_list_route_returns_the_callers_assigned_requests(
    call_route: CallRoute,
    token_for: Callable[..., str],
    make_user: Callable[..., User],
    list_service: MagicMock,
) -> None:
    coordinator = make_user(role=Role.EVENT_COORDINATOR, user_id=3)

    response, status = call_route(ENDPOINT, "GET", PATH, {}, token_for(coordinator))

    assert status == 200
    list_service.assert_called_once_with("3")
    [listed] = response.get_json()["event_requests"]
    assert (listed["reference"], listed["status"]) == ("EVR-AAAAAAAA", "submitted")
    assert "coordinator_id" not in listed
