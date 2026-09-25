"""Unit tests for SCRUM-25 AC3 — only Venue Staff may write to the catalogue.

The *registered* view functions (``app.view_functions``) are invoked inside a
``test_request_context`` so the tests exercise the real decorator wiring on
each venue route, not a stand-in. The service layer is replaced with mocks:
an unauthorized write must be rejected before any service call happens.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import Venue

pytestmark = pytest.mark.scrum_25

# (endpoint, HTTP method, path, view kwargs, service function it calls)
WRITE_ROUTES = [
    ("venue.create_venue", "POST", "/api/venues", {}, "create_venue"),
    ("venue.update_venue", "PATCH", "/api/venues/1", {"venue_id": 1}, "update_venue"),
    (
        "venue.deactivate_venue",
        "POST",
        "/api/venues/1/deactivate",
        {"venue_id": 1},
        "deactivate_venue",
    ),
    (
        "venue.reactivate_venue",
        "POST",
        "/api/venues/1/reactivate",
        {"venue_id": 1},
        "reactivate_venue",
    ),
]
WRITE_ROUTE_IDS = [route[0] for route in WRITE_ROUTES]

NON_VENUE_STAFF_ROLES = sorted(ALL_ROLES - {Role.VENUE_STAFF}, key=lambda r: r.value)

VALID_PAYLOAD = {"name": "Hall", "location": "A", "capacity": 10}


@pytest.fixture()
def mock_services(
    monkeypatch: pytest.MonkeyPatch, make_venue: Callable[..., Venue]
) -> dict[str, MagicMock]:
    """Replace every venue service the routes call with a mock returning a venue."""
    mocks = {}
    for name in (
        "create_venue",
        "update_venue",
        "deactivate_venue",
        "reactivate_venue",
        "list_venues",
        "get_venue",
    ):
        mock = MagicMock(return_value=[make_venue()] if name == "list_venues" else make_venue())
        monkeypatch.setattr(services, name, mock)
        mocks[name] = mock
    return mocks


def _call_route(
    app: Flask,
    endpoint: str,
    method: str,
    path: str,
    view_kwargs: dict[str, Any],
    token: str | None,
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    with app.test_request_context(path, method=method, headers=headers, json=VALID_PAYLOAD):
        return app.view_functions[endpoint](**view_kwargs)


# --------------------------------------------------------------------------
# Unauthorized writes are rejected and never reach the service layer
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", NON_VENUE_STAFF_ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize(
    ("endpoint", "method", "path", "view_kwargs", "service"), WRITE_ROUTES, ids=WRITE_ROUTE_IDS
)
def test_write_by_non_venue_staff_is_403(
    app: Flask, token_for, mock_services, role: Role, endpoint, method, path, view_kwargs, service
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        _call_route(app, endpoint, method, path, view_kwargs, token_for(role=role))

    assert exc_info.value.status_code == 403
    mock_services[service].assert_not_called()


@pytest.mark.parametrize(
    ("endpoint", "method", "path", "view_kwargs", "service"), WRITE_ROUTES, ids=WRITE_ROUTE_IDS
)
def test_write_without_token_is_401(
    app: Flask, mock_services, endpoint, method, path, view_kwargs, service
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        _call_route(app, endpoint, method, path, view_kwargs, token=None)

    assert exc_info.value.status_code == 401
    mock_services[service].assert_not_called()


@pytest.mark.parametrize(
    ("endpoint", "method", "path", "view_kwargs", "service"), WRITE_ROUTES, ids=WRITE_ROUTE_IDS
)
def test_write_route_allows_only_venue_staff(
    app: Flask, endpoint, method, path, view_kwargs, service
) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[endpoint].allowed_roles == frozenset({Role.VENUE_STAFF.value})


# --------------------------------------------------------------------------
# Venue Staff can write; everyone authenticated can read
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "method", "path", "view_kwargs", "service"), WRITE_ROUTES, ids=WRITE_ROUTE_IDS
)
def test_write_by_venue_staff_reaches_service(
    app: Flask, token_for, mock_services, endpoint, method, path, view_kwargs, service
) -> None:
    _call_route(app, endpoint, method, path, view_kwargs, token_for(role=Role.VENUE_STAFF))

    mock_services[service].assert_called_once()


@pytest.mark.parametrize("role", NON_VENUE_STAFF_ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize(
    ("endpoint", "path", "view_kwargs"),
    [
        ("venue.list_venues", "/api/venues", {}),
        ("venue.get_venue", "/api/venues/1", {"venue_id": 1}),
    ],
    ids=["list_venues", "get_venue"],
)
def test_read_is_allowed_for_non_venue_staff(
    app: Flask, token_for, mock_services, role: Role, endpoint, path, view_kwargs
) -> None:
    _, status = _call_route(app, endpoint, "GET", path, view_kwargs, token_for(role=role))

    assert status == 200
