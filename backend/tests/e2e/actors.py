"""The :class:`Actor` that end-to-end journeys make their requests as (SCRUM-41).

It lives in a plain module rather than in ``conftest.py``, because a conftest holds
only fixtures: the ``sign_in`` fixture and the tests both import it, and the
:data:`SignIn` type, from here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flask.testing import FlaskClient
from werkzeug.test import TestResponse


@dataclass(frozen=True)
class Actor:
    """A signed-in user making requests: every call carries their access token."""

    client: FlaskClient
    token: str

    def _call(self, method: str, path: str, body: dict[str, Any] | None) -> TestResponse:
        headers = {"Authorization": f"Bearer {self.token}"}
        return self.client.open(path, method=method, headers=headers, json=body)

    def get(self, path: str) -> TestResponse:
        """Send a ``GET`` as this user."""
        return self._call("GET", path, None)

    def post(self, path: str, body: dict[str, Any] | None = None) -> TestResponse:
        """Send a ``POST`` as this user, with an optional JSON body."""
        return self._call("POST", path, body)

    def put(self, path: str, body: dict[str, Any]) -> TestResponse:
        """Send a ``PUT`` with a JSON body as this user."""
        return self._call("PUT", path, body)

    def patch(self, path: str, body: dict[str, Any]) -> TestResponse:
        """Send a ``PATCH`` with a JSON body as this user."""
        return self._call("PATCH", path, body)


#: What the ``sign_in`` fixture returns: takes an email and password, gives an Actor.
SignIn = Callable[[str, str], Actor]
