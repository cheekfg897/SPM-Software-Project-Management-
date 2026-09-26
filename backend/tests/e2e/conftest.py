"""The harness for end-to-end journeys: Flask's test client, signed in over HTTP.

This is the one place the suite uses a test client (ADR-0031). Everywhere else, tests
call services and view functions directly; the tests under ``tests/e2e`` walk a user's
journey through the real routes, so routing, auth decorators, JSON parsing and the
error handlers run as they would for a browser.

Requests share ``db_session``. The autouse ``app_context`` fixture has already pushed an
application context, and each test-client request reuses it rather than pushing its
own. Flask-SQLAlchemy scopes ``db.session`` by application context, so ``db.session``
inside a route is the same session as ``db_session``: what a test saves, a route reads,
and what a route commits, the test can read back.

The :class:`~tests.e2e.actors.Actor` the requests are made as lives in
``tests/e2e/actors.py``, since a conftest holds only fixtures.
"""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from tests.e2e.actors import Actor, SignIn


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    """Flask's test client for the session's app."""
    return app.test_client()


@pytest.fixture()
def sign_in(client: FlaskClient) -> SignIn:
    """Log a user in over ``POST /api/auth/login`` and return them as an :class:`Actor`.

    Returns a function taking the email and password.
    """

    def _sign_in(email: str, password: str) -> Actor:
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.get_json()
        return Actor(client, token=response.get_json()["access_token"])

    return _sign_in
