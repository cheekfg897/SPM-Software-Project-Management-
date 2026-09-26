"""Route tests for SCRUM-24 "see the events my role is involved in".

AC2: Event Coordinators can open the list of submitted requests no coordinator has
yet, separate from their own assigned list. AC4: Technical Support can open the list
of events that have an equipment request. AC6: every role's event list shows each
event's name, date, time and status. AC7: the event record widens to Event
Coordinators, the same sections as the organiser's. AC8: a list with no matching
events says so, instead of an empty list looking the same as "nothing loaded yet"
(copying ``search_venues``'s precedent, SCRUM-35 AC4).

Covers the organiser's own list, the coordinator's assigned and unassigned lists,
Technical Support's equipment list, and the event record opened to coordinators.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.events import routes
from app.modules.events.models import EventEquipmentLine, EventRequest
from app.modules.events.services import CoordinatorContact

pytestmark = pytest.mark.scrum_24

CallRoute = Callable[..., Any]
ReplaceServices = Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]]
TokenFor = Callable[..., str]


class EventList(NamedTuple):
    """One role's event list route: enough to open it and check what it says."""

    endpoint: str
    path: str
    service: str
    role: Role
    empty_message: str


ORGANISATION_LIST = EventList(
    "events.list_my_requests",
    "/api/events/requests",
    "list_event_requests_for_organiser",
    Role.EVENT_ORGANISER,
    "Your organisation has no event requests yet.",
)
ASSIGNED_LIST = EventList(
    "events.list_assigned_requests",
    "/api/events/requests/assigned",
    "list_event_requests_for_coordinator",
    Role.EVENT_COORDINATOR,
    "No event requests are assigned to you yet.",
)
UNASSIGNED_LIST = EventList(
    "events.list_unassigned_requests",
    "/api/events/requests/unassigned",
    "list_unassigned_event_requests",
    Role.EVENT_COORDINATOR,
    "No submitted event requests are waiting for a coordinator.",
)
EQUIPMENT_LIST = EventList(
    "events.list_requests_with_equipment",
    "/api/events/requests/with-equipment",
    "list_event_requests_with_equipment",
    Role.TECHNICAL_SUPPORT_STAFF,
    "No events have an equipment request yet.",
)
ROLE_LISTS = [ORGANISATION_LIST, ASSIGNED_LIST, UNASSIGNED_LIST, EQUIPMENT_LIST]
NEW_LISTS = [UNASSIGNED_LIST, EQUIPMENT_LIST]

OpenList = Callable[[EventList, list[EventRequest]], tuple[dict[str, Any], int, MagicMock]]


@pytest.fixture()
def open_list(
    call_route: CallRoute, replace_services: ReplaceServices, token_for: TokenFor
) -> OpenList:
    """Replace an event list's service and open it as its role.

    Returns the decoded body, the status code and the mock, so a test can also
    check how the service was called.
    """

    def _open(
        event_list: EventList, listed: list[EventRequest]
    ) -> tuple[dict[str, Any], int, MagicMock]:
        mocks = replace_services(routes, {event_list.service: listed})
        response, status = call_route(
            event_list.endpoint, "GET", event_list.path, {}, token_for(role=event_list.role)
        )
        return response.get_json(), status, mocks[event_list.service]

    return _open


# --------------------------------------------------------------------------
# AC6 — every list shows each event's name, date, time and status
# --------------------------------------------------------------------------


@pytest.mark.parametrize("event_list", ROLE_LISTS, ids=lambda event_list: event_list.endpoint)
def test_every_list_shows_each_events_name_date_time_and_status(
    open_list: OpenList, shown_event: EventRequest, event_list: EventList
) -> None:
    body, status, _ = open_list(event_list, [shown_event])

    assert status == 200
    [row] = body["event_requests"]
    shown_field_names = ("name", "proposed_date", "end_date", "start_time", "end_time", "status")
    shown_fields = {}
    for field_name in shown_field_names:
        shown_fields[field_name] = row[field_name]
    assert shown_fields == {
        "name": "Partner Summit",
        "proposed_date": "2026-10-15",
        "end_date": "2026-10-15",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "status": "submitted",
    }


@pytest.mark.parametrize("event_list", ROLE_LISTS, ids=lambda event_list: event_list.endpoint)
def test_a_list_with_events_carries_no_message(
    open_list: OpenList, shown_event: EventRequest, event_list: EventList
) -> None:
    body, _, _ = open_list(event_list, [shown_event])

    assert "message" not in body


# --------------------------------------------------------------------------
# AC8 — an empty list says there are none, rather than looking blank
# --------------------------------------------------------------------------


@pytest.mark.parametrize("event_list", ROLE_LISTS, ids=lambda event_list: event_list.endpoint)
def test_an_empty_list_says_there_are_none(open_list: OpenList, event_list: EventList) -> None:
    body, status, _ = open_list(event_list, [])

    assert status == 200
    assert body == {"event_requests": [], "message": event_list.empty_message}


# --------------------------------------------------------------------------
# Access — each new list opens to its own role only
# --------------------------------------------------------------------------


def _refused_cases() -> list[tuple[EventList, Role]]:
    """Every new list crossed with every role that may not open it."""
    cases = []
    for event_list in NEW_LISTS:
        other_roles = sorted(ALL_ROLES - {event_list.role}, key=lambda role: role.value)
        for role in other_roles:
            cases.append((event_list, role))
    return cases


def _case_id(case: tuple[EventList, Role]) -> str:
    event_list, role = case
    return f"{event_list.endpoint}-{role.value}"


@pytest.mark.parametrize("event_list", NEW_LISTS, ids=lambda event_list: event_list.endpoint)
def test_each_new_list_allows_only_its_role(app: Flask, event_list: EventList) -> None:
    allowed_roles = app.view_functions[event_list.endpoint].allowed_roles  # type: ignore[attr-defined]

    assert allowed_roles == frozenset({event_list.role.value})


@pytest.mark.parametrize("case", _refused_cases(), ids=_case_id)
def test_other_roles_cannot_open_a_new_list(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: TokenFor,
    case: tuple[EventList, Role],
) -> None:
    event_list, role = case
    mocks = replace_services(routes, {event_list.service: []})

    with pytest.raises(AuthorizationError) as exc_info:
        call_route(event_list.endpoint, "GET", event_list.path, {}, token_for(role=role))

    assert exc_info.value.status_code == 403
    mocks[event_list.service].assert_not_called()


@pytest.mark.parametrize("event_list", NEW_LISTS, ids=lambda event_list: event_list.endpoint)
def test_opening_a_new_list_without_a_token_is_401(
    call_route: CallRoute, replace_services: ReplaceServices, event_list: EventList
) -> None:
    mocks = replace_services(routes, {event_list.service: []})

    with pytest.raises(AuthenticationError) as exc_info:
        call_route(event_list.endpoint, "GET", event_list.path, {}, None)

    assert exc_info.value.status_code == 401
    mocks[event_list.service].assert_not_called()


@pytest.mark.parametrize("event_list", NEW_LISTS, ids=lambda event_list: event_list.endpoint)
def test_a_new_list_path_is_not_taken_for_a_reference(app: Flask, event_list: EventList) -> None:
    """A new list's path, e.g. ``unassigned``, must not be read as a reference."""
    adapter = app.url_map.bind("localhost")

    assert adapter.match(event_list.path) == (event_list.endpoint, {})


# --------------------------------------------------------------------------
# AC2 — the unassigned list shows each whole request
# --------------------------------------------------------------------------


def test_the_unassigned_list_shows_each_whole_request_without_internal_ids(
    open_list: OpenList, shown_event: EventRequest
) -> None:
    body, status, mock = open_list(UNASSIGNED_LIST, [shown_event])

    assert status == 200
    [row] = body["event_requests"]
    assert row["expected_attendance"] == 250
    assert "coordinator_id" not in row
    assert "organiser_id" not in row
    mock.assert_called_once_with()


# --------------------------------------------------------------------------
# AC4 — Technical Support can open the list of events with an equipment request
# --------------------------------------------------------------------------


def test_the_equipment_list_shows_only_each_events_summary(
    open_list: OpenList, shown_event: EventRequest, event_as_shown: dict[str, Any]
) -> None:
    body, status, mock = open_list(EQUIPMENT_LIST, [shown_event])

    assert status == 200
    assert body == {"event_requests": [{**event_as_shown, "status": "submitted"}]}
    mock.assert_called_once_with()


# --------------------------------------------------------------------------
# AC7 — the event record opens to organisers and coordinators
# --------------------------------------------------------------------------

RECORD_ENDPOINT = "events.get_my_request"
RECORD_PATH = "/api/events/requests/EVR-AAAAAAAA"
NON_RECORD_ROLES = sorted(
    ALL_ROLES - {Role.EVENT_ORGANISER, Role.EVENT_COORDINATOR}, key=lambda role: role.value
)


def test_the_event_record_opens_to_organisers_and_coordinators(app: Flask) -> None:
    allowed_roles = app.view_functions[RECORD_ENDPOINT].allowed_roles  # type: ignore[attr-defined]

    assert allowed_roles == frozenset({Role.EVENT_ORGANISER.value, Role.EVENT_COORDINATOR.value})


@pytest.mark.parametrize("role", NON_RECORD_ROLES, ids=lambda role: role.value)
def test_other_roles_cannot_open_an_event_record(
    call_route: CallRoute, replace_services: ReplaceServices, token_for: TokenFor, role: Role
) -> None:
    mocks = replace_services(
        routes,
        {
            "get_event_record_for_organiser": (None, None),
            "get_event_record_for_coordinator": (None, None),
        },
    )

    with pytest.raises(AuthorizationError) as exc_info:
        call_route(
            RECORD_ENDPOINT, "GET", RECORD_PATH, {"reference": "EVR-AAAAAAAA"}, token_for(role=role)
        )

    assert exc_info.value.status_code == 403
    mocks["get_event_record_for_organiser"].assert_not_called()
    mocks["get_event_record_for_coordinator"].assert_not_called()


def test_a_coordinator_opening_a_record_sees_the_request_its_equipment_and_its_coordinator(
    call_route: CallRoute,
    replace_services: ReplaceServices,
    token_for: TokenFor,
    make_user: Callable[..., User],
    make_event_request: Callable[..., EventRequest],
    shown_line: EventEquipmentLine,
    line_as_shown: dict[str, Any],
    coordinator_three: CoordinatorContact,
) -> None:
    event_request = make_event_request(coordinator_id=3)
    event_request.equipment_lines = [shown_line]
    mocks = replace_services(
        routes,
        {
            "get_event_record_for_coordinator": (event_request, coordinator_three),
            "get_event_record_for_organiser": (event_request, None),
        },
    )
    coordinator = make_user(role=Role.EVENT_COORDINATOR, user_id=3)

    response, status = call_route(
        RECORD_ENDPOINT, "GET", RECORD_PATH, {"reference": "EVR-AAAAAAAA"}, token_for(coordinator)
    )

    assert status == 200
    mocks["get_event_record_for_coordinator"].assert_called_once_with("3", "EVR-AAAAAAAA")
    mocks["get_event_record_for_organiser"].assert_not_called()
    body = response.get_json()
    assert body["expected_attendance"] == 250
    assert body["equipment_lines"] == [line_as_shown]
    assert body["coordinator"] == {
        "full_name": "Coordinator Three",
        "email": "coordinator3@example.com",
    }
    assert "coordinator_id" not in body
