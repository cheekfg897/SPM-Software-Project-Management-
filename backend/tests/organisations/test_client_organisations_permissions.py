"""Unit tests for SCRUM-66 AC5 — client organisation details are hidden from Attendees.

Only internal users record and list client organisations (ADR-0013), so Attendees and
Event Organisers are both refused. The *registered* view functions
(``app.view_functions``) are called inside a ``test_request_context``, so the real
decorator wiring is exercised; the services are mocks, and a refused call must never
reach them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.common.errors import AuthenticationError, AuthorizationError
from app.modules.auth.permissions import EXTERNAL_ROLES, INTERNAL_ROLES, Role
from app.modules.organisations import services
from app.modules.organisations.models import ClientOrganisation

pytestmark = pytest.mark.scrum_66

# (endpoint, HTTP method, service function it calls)
ROUTES = [
    ("organisations.create_organisation", "POST", "create_organisation"),
    ("organisations.list_organisations", "GET", "list_organisations"),
]
ROUTE_IDS = [route[0] for route in ROUTES]

ORGANISATIONS_PATH = "/api/organisations"

EXTERNAL = sorted(EXTERNAL_ROLES, key=lambda r: r.value)
INTERNAL = sorted(INTERNAL_ROLES, key=lambda r: r.value)

PHONE = "+65 6123 4567"


@pytest.fixture()
def organisation(
    make_organisation: Callable[..., ClientOrganisation], valid_organisation_payload: dict[str, Any]
) -> ClientOrganisation:
    """The organisation the mocked services hand back (id 1)."""
    return make_organisation(**valid_organisation_payload, contact_phone=PHONE)


@pytest.fixture()
def expected_body(valid_organisation_payload: dict[str, Any]) -> dict[str, Any]:
    """How :func:`organisation` is serialised in a response."""
    return {"id": 1, **valid_organisation_payload, "contact_phone": PHONE, "created_at": None}


@pytest.fixture()
def mock_services(
    monkeypatch: pytest.MonkeyPatch, organisation: ClientOrganisation
) -> dict[str, MagicMock]:
    """Replace the services the routes call with mocks of the right shape."""
    returns: dict[str, Any] = {
        "create_organisation": organisation,
        "list_organisations": [organisation],
    }
    mocks = {}
    for name, value in returns.items():
        mock = MagicMock(return_value=value)
        monkeypatch.setattr(services, name, mock)
        mocks[name] = mock
    return mocks


def _call_route(
    app: Flask, endpoint: str, method: str, token: str | None, body: dict[str, Any] | None = None
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    with app.test_request_context(ORGANISATIONS_PATH, method=method, headers=headers, json=body):
        return app.view_functions[endpoint]()


# --------------------------------------------------------------------------
# AC5 — Attendees (and Event Organisers) can't see or record organisations
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", EXTERNAL, ids=lambda r: r.value)
@pytest.mark.parametrize(("endpoint", "method", "service"), ROUTES, ids=ROUTE_IDS)
def test_external_roles_cannot_see_or_record_organisations(
    app: Flask,
    token_for: Callable[..., str],
    mock_services: dict[str, MagicMock],
    role: Role,
    endpoint: str,
    method: str,
    service: str,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        _call_route(app, endpoint, method, token_for(role=role))

    assert exc_info.value.status_code == 403
    mock_services[service].assert_not_called()


@pytest.mark.parametrize(("endpoint", "method", "service"), ROUTES, ids=ROUTE_IDS)
def test_without_token_is_401(
    app: Flask,
    mock_services: dict[str, MagicMock],
    endpoint: str,
    method: str,
    service: str,
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        _call_route(app, endpoint, method, token=None)

    assert exc_info.value.status_code == 401
    mock_services[service].assert_not_called()


@pytest.mark.parametrize(("endpoint", "method", "service"), ROUTES, ids=ROUTE_IDS)
def test_routes_allow_exactly_the_internal_roles(
    app: Flask, endpoint: str, method: str, service: str
) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    expected = frozenset(role.value for role in INTERNAL_ROLES)

    assert app.view_functions[endpoint].allowed_roles == expected


# --------------------------------------------------------------------------
# AC1 — internal users record and list organisations
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", INTERNAL, ids=lambda r: r.value)
def test_internal_user_records_an_organisation(
    app: Flask,
    token_for: Callable[..., str],
    mock_services: dict[str, MagicMock],
    valid_organisation_payload: dict[str, Any],
    expected_body: dict[str, Any],
    role: Role,
) -> None:
    response, status = _call_route(
        app,
        "organisations.create_organisation",
        "POST",
        token_for(role=role),
        valid_organisation_payload,
    )

    assert status == 201
    mock_services["create_organisation"].assert_called_once_with(valid_organisation_payload)
    assert response.get_json() == expected_body


@pytest.mark.parametrize("role", INTERNAL, ids=lambda r: r.value)
def test_internal_user_lists_organisations(
    app: Flask,
    token_for: Callable[..., str],
    mock_services: dict[str, MagicMock],
    expected_body: dict[str, Any],
    role: Role,
) -> None:
    response, status = _call_route(
        app, "organisations.list_organisations", "GET", token_for(role=role)
    )

    assert status == 200
    mock_services["list_organisations"].assert_called_once_with()
    assert response.get_json() == {"organisations": [expected_body]}
