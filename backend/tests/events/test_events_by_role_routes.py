"""Route tests for SCRUM-24 "see the events my role is involved in".

AC6: every role's event list shows each event's name, date, time and status. AC8:
a list with no matching events says so, instead of an empty list looking the same
as "nothing loaded yet" (copying ``search_venues``'s precedent, SCRUM-35 AC4).

This commit covers the organiser's own list (``GET /api/events/requests``) and the
coordinator's assigned list (``GET /api/events/requests/assigned``); later commits
add the coordinator's unassigned list (AC2), Technical Support's equipment list
(AC4), and the event record opened to coordinators (AC7).
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest

from app.modules.auth.permissions import Role
from app.modules.events import routes
from app.modules.events.models import EventRequest

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
ROLE_LISTS = [ORGANISATION_LIST, ASSIGNED_LIST]

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
