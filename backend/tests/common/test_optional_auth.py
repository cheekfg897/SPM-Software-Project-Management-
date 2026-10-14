"""Unit tests for ``@optional_auth``, the decorator for routes open to visitors.

SCRUM-52's catalogue is public, but its ``is_registered`` is about whoever is asking
(ADR-0032). The decorator lets a visitor in, says who a signed-in caller is in ``g``,
and treats a token that isn't valid as a visitor rather than refusing the page.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from flask import Flask, g
from flask_jwt_extended import create_access_token

from app.common.decorators import optional_auth
from app.modules.auth.models import User
from app.modules.auth.permissions import Role

pytestmark = pytest.mark.scrum_52


@optional_auth
def _who_is_asking() -> tuple[Any, Any]:
    return g.current_user_id, g.current_user_role


def _ask(app: Flask, token: str | None) -> tuple[Any, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    with app.test_request_context("/", headers=headers):
        return _who_is_asking()


def test_a_visitor_with_no_token_is_let_in_as_nobody(app: Flask) -> None:
    assert _ask(app, None) == (None, None)


def test_a_signed_in_caller_is_named_in_g(
    app: Flask, make_user: Callable[..., User], token_for: Callable[..., str]
) -> None:
    attendee = make_user(role=Role.ATTENDEE, user_id=21)

    assert _ask(app, token_for(attendee)) == ("21", "attendee")


def test_a_token_that_is_not_valid_is_a_visitor(app: Flask) -> None:
    assert _ask(app, "not-a-token") == (None, None)


def test_an_expired_token_is_a_visitor(app: Flask) -> None:
    expired = create_access_token(identity="21", expires_delta=timedelta(seconds=-1))

    assert _ask(app, expired) == (None, None)
