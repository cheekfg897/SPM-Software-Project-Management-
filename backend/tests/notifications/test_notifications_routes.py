"""Unit tests for SCRUM-28 "Receive notifications about my events": the routes.

Every user, whatever their role, lists (AC2), counts (AC5) and marks read (AC4) their
own notifications and nobody else's. The *registered* view functions
(``app.view_functions``) are called inside a ``test_request_context`` against
``db_session``, so the auth decorator, the service's query and the response shape are
all real (ADR-0015).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from flask import Flask
from sqlalchemy.orm import Session

from app.common.errors import AuthenticationError, NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.notifications.models import Notification
from app.modules.notifications.services import mark_notification_read

pytestmark = pytest.mark.scrum_28

Notify = Callable[..., list[Notification]]
ReloadNotification = Callable[[int], Notification]

#: (endpoint, HTTP method, path, view kwargs)
Route = tuple[str, str, str, dict[str, int]]

LIST_ROUTE: Route = ("notifications.list_my_notifications", "GET", "/api/notifications", {})
UNREAD_COUNT_ROUTE: Route = (
    "notifications.unread_count",
    "GET",
    "/api/notifications/unread-count",
    {},
)
#: Marks notification 2, the second one saved in a test, so a route that always marked
#: notification 1 is caught.
MARK_READ_ROUTE: Route = (
    "notifications.mark_read",
    "POST",
    "/api/notifications/2/read",
    {"notification_id": 2},
)
ROUTES = [LIST_ROUTE, UNREAD_COUNT_ROUTE, MARK_READ_ROUTE]
ROUTE_IDS = [route[0] for route in ROUTES]

#: The user the tests call the routes as.
CALLER_ID = 5


def _call(app: Flask, route: Route, token: str | None) -> Any:
    endpoint, method, path, view_kwargs = route
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    with app.test_request_context(path, method=method, headers=headers):
        return app.view_functions[endpoint](**view_kwargs)


def _shown(notification_id: int, created_at: str, read_at: str | None = None) -> dict[str, Any]:
    """A notification about the ``event_summary`` fixture, as the API shows it."""
    return {
        "id": notification_id,
        "kind": "event_request_submitted",
        "message": "A new event request was submitted.",
        "event_reference": "EVR-AAAAAAAA",
        "event_name": "Partner Summit",
        "link": "/events/EVR-AAAAAAAA",
        "created_at": created_at,
        "read_at": read_at,
        "detail": None,
    }


@pytest.fixture()
def caller_token(make_user: Callable[..., User], token_for: Callable[..., str]) -> str:
    """A token for user :data:`CALLER_ID`."""
    return token_for(make_user(user_id=CALLER_ID))


# --------------------------------------------------------------------------
# Access — any signed-in user, whatever their role
# --------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_every_route_needs_a_token(app: Flask, route: Route) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        _call(app, route, token=None)

    assert exc_info.value.status_code == 401


@pytest.mark.parametrize(
    "role", sorted(ALL_ROLES, key=lambda role: role.value), ids=lambda role: role.value
)
def test_every_role_may_read_its_own_notifications(
    app: Flask, db_session: Session, token_for: Callable[..., str], role: Role
) -> None:
    response, status = _call(app, LIST_ROUTE, token_for(role=role))

    assert status == 200
    assert response.get_json() == {"notifications": []}


# --------------------------------------------------------------------------
# AC1 + AC2 — the caller's own notifications, newest first, with every field
# --------------------------------------------------------------------------


def test_list_route_shows_the_callers_notifications_newest_first_with_every_field(
    app: Flask, notify: Notify, caller_token: str
) -> None:
    notify(CALLER_ID, now=datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc))
    notify(CALLER_ID, 6, now=datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc))

    response, status = _call(app, LIST_ROUTE, caller_token)

    assert status == 200
    assert response.get_json() == {
        "notifications": [
            _shown(2, created_at="2026-10-01T10:00:00+08:00"),
            _shown(1, created_at="2026-10-01T09:00:00+08:00"),
        ]
    }


# --------------------------------------------------------------------------
# AC4 — a notification that has been read stays in the list, marked as read
# --------------------------------------------------------------------------


def test_list_route_still_shows_a_notification_once_it_is_read(
    app: Flask, notify: Notify, caller_token: str
) -> None:
    notify(CALLER_ID)
    mark_notification_read(1, CALLER_ID, now=datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc))

    response, status = _call(app, LIST_ROUTE, caller_token)

    assert status == 200
    assert response.get_json() == {
        "notifications": [
            _shown(1, created_at="2026-10-01T09:00:00+08:00", read_at="2026-10-01T11:00:00+08:00")
        ]
    }


# --------------------------------------------------------------------------
# AC5 — the caller's unread count
# --------------------------------------------------------------------------


def test_unread_count_route_counts_the_callers_unread_notifications(
    app: Flask, notify: Notify, caller_token: str
) -> None:
    notify(CALLER_ID, CALLER_ID, 6)

    response, status = _call(app, UNREAD_COUNT_ROUTE, caller_token)

    assert status == 200
    assert response.get_json() == {"unread_count": 2}


# --------------------------------------------------------------------------
# AC4 — marking the caller's own notification read
# --------------------------------------------------------------------------


def test_mark_read_route_marks_the_callers_notification_and_returns_it(
    app: Flask,
    notify: Notify,
    reload_notification: ReloadNotification,
    caller_token: str,
) -> None:
    notify(CALLER_ID, CALLER_ID)

    response, status = _call(app, MARK_READ_ROUTE, caller_token)

    assert status == 200
    body = response.get_json()
    assert body["read_at"] is not None
    assert body == _shown(2, created_at="2026-10-01T09:00:00+08:00", read_at=body["read_at"])
    assert reload_notification(2).read_at is not None
    assert reload_notification(1).read_at is None


def test_mark_read_route_hides_another_users_notification(
    app: Flask,
    notify: Notify,
    reload_notification: ReloadNotification,
    caller_token: str,
) -> None:
    notify(CALLER_ID, 6)

    with pytest.raises(NotFoundError) as exc_info:
        _call(app, MARK_READ_ROUTE, caller_token)

    assert exc_info.value.status_code == 404
    assert reload_notification(2).read_at is None
