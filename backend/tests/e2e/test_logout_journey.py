"""SCRUM-89: logging out ends this session on the server, through the API.

An Event Organiser signs in twice (two devices) and an Event Coordinator once. The
organiser logs out on one device: that token is refused from then on, on every
protected route, with the usual ``401``, while the organiser's other device and the
coordinator carry on (SCRUM-6 AC4, ADR-0110). Logging out again with the refused token
is the same ``401``. Every call goes through the real routes with Flask's test client
(ADR-0031).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.common.errors import INVALID_TOKEN_MESSAGE
from app.modules.auth.models import User
from tests.e2e.actors import Actor, SignIn

pytestmark = [pytest.mark.scrum_89, pytest.mark.e2e]

PASSWORD = "Password123"
ORGANISER_EMAIL = "organiser7@example.com"
COORDINATOR_EMAIL = "coordinator3@example.com"
LOGOUT_PATH = "/api/auth/logout"
PROFILE_PATH = "/api/auth/me"

#: The endpoints anyone may call without a token: logging in, signing up, the health
#: check, static files and the public catalogue (``@optional_auth``).
PUBLIC_ENDPOINTS = frozenset(
    {
        "auth.login",
        "auth.register",
        "health.health",
        "static",
        "registration.browse_catalogue",
    }
)
#: Methods Flask answers by itself, without calling the view.
AUTOMATIC_METHODS = frozenset({"HEAD", "OPTIONS"})


def _protected_requests(app: Flask) -> Iterator[tuple[str, str]]:
    """Every (method, path) of a route that needs a token, with 1 for each URL value."""
    urls = app.url_map.bind("localhost")
    for rule in app.url_map.iter_rules():
        if rule.endpoint in PUBLIC_ENDPOINTS:
            continue
        values = {}
        for argument in rule.arguments:
            values[argument] = 1
        for method in sorted(rule.methods - AUTOMATIC_METHODS):
            yield method, urls.build(rule.endpoint, values, method=method)


@pytest.fixture()
def organiser(saved_users: list[User], sign_in: SignIn) -> Actor:
    """The saved Event Organiser, signed in over HTTP."""
    return sign_in(ORGANISER_EMAIL, PASSWORD)


def test_logging_out_ends_this_session_and_no_other(organiser: Actor, sign_in: SignIn) -> None:
    organiser_other_device = sign_in(ORGANISER_EMAIL, PASSWORD)
    coordinator = sign_in(COORDINATOR_EMAIL, PASSWORD)
    assert organiser.get(PROFILE_PATH).status_code == 200

    logout = organiser.post(LOGOUT_PATH)
    profile = organiser.get(PROFILE_PATH)

    assert (logout.status_code, logout.get_data(as_text=True)) == (204, "")
    assert profile.status_code == 401
    assert profile.get_json() == {
        "error": "authentication_error",
        "message": INVALID_TOKEN_MESSAGE,
    }
    assert organiser_other_device.get(PROFILE_PATH).status_code == 200
    assert coordinator.get(PROFILE_PATH).status_code == 200


def test_logging_out_again_with_the_logged_out_token_is_401(organiser: Actor) -> None:
    assert organiser.post(LOGOUT_PATH).status_code == 204

    again = organiser.post(LOGOUT_PATH)

    assert again.status_code == 401
    assert again.get_json()["message"] == INVALID_TOKEN_MESSAGE


def test_a_logged_out_token_is_refused_on_every_protected_route(
    app: Flask, organiser: Actor, client: FlaskClient
) -> None:
    assert organiser.post(LOGOUT_PATH).status_code == 204
    headers = {"Authorization": f"Bearer {organiser.token}"}

    not_refused = []
    for method, path in _protected_requests(app):
        response = client.open(path, method=method, headers=headers, json={})
        if response.status_code != 401:
            not_refused.append(f"{method} {path} -> {response.status_code}")

    assert not_refused == []


def test_the_route_sweep_skips_only_real_public_endpoints(
    app: Flask,
) -> None:
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    swept = {path for _method, path in _protected_requests(app)}

    assert endpoints >= PUBLIC_ENDPOINTS
    assert {LOGOUT_PATH, PROFILE_PATH} <= swept
