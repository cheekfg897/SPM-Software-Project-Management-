"""Unit tests for the login route, ``POST /api/auth/login`` (SCRUM-6 AC1, AC2).

``tests/auth/test_login.py`` checks the service. These check what the route adds:
it reads the email and password from the body, refuses a bad body before anyone's
password is checked, and answers with the shape the frontend's session reads. They
run the real service on the in-memory database, so a wrong field name can't pass on
a mock's say-so.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_jwt_extended import decode_token
from sqlalchemy.orm import Session

from app.common.errors import AuthenticationError, ValidationError
from app.modules.auth import routes as auth_routes
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.auth.services import INVALID_CREDENTIALS_MESSAGE

pytestmark = pytest.mark.scrum_6

LOGIN_PATH = "/api/auth/login"
LOGIN_ROUTE = ("auth.login", "POST", LOGIN_PATH, {}, None)
EMAIL = "gwen@example.com"
USER_ID = 41


@pytest.fixture()
def saved_coordinator(
    make_user: Callable[..., User], db_session: Session, valid_password: str
) -> None:
    """A saved coordinator and a decoy, so the route must find the right one."""
    coordinator = make_user(
        email=EMAIL,
        password=valid_password,
        full_name="Gwen Lim",
        role=Role.EVENT_COORDINATOR,
        user_id=USER_ID,
    )
    decoy = make_user(email="decoy@example.com", password=valid_password, user_id=USER_ID + 1)
    db_session.add_all([coordinator, decoy])
    db_session.commit()


@pytest.mark.usefixtures("saved_coordinator")
def test_the_right_password_answers_200_with_the_token_and_who_signed_in(
    call_route: Callable[..., Any], valid_password: str
) -> None:
    response, status = call_route(*LOGIN_ROUTE, body={"email": EMAIL, "password": valid_password})

    assert status == 200
    body = response.get_json()
    assert decode_token(body.pop("access_token"))["sub"] == str(USER_ID)
    assert body == {
        "token_type": "Bearer",
        "user": {"id": USER_ID, "full_name": "Gwen Lim", "role": "event_coordinator"},
    }


@pytest.mark.usefixtures("saved_coordinator")
def test_a_wrong_password_is_refused_without_saying_which_part_was_wrong(
    call_route: Callable[..., Any], valid_password: str
) -> None:
    body = {"email": EMAIL, "password": f"{valid_password}-wrong"}

    with pytest.raises(AuthenticationError) as refusal:
        call_route(*LOGIN_ROUTE, body=body)

    assert refusal.value.message == INVALID_CREDENTIALS_MESSAGE


def test_a_missing_password_is_refused_by_field_before_any_password_is_checked(
    call_route: Callable[..., Any],
    replace_services: Callable[[ModuleType, dict[str, Any]], dict[str, MagicMock]],
) -> None:
    mocks = replace_services(auth_routes, {"authenticate_user": None})

    with pytest.raises(ValidationError) as refusal:
        call_route(*LOGIN_ROUTE, body={"email": EMAIL})

    assert refusal.value.details == {"password": ["Missing data for required field."]}
    mocks["authenticate_user"].assert_not_called()


def test_a_body_that_is_not_json_is_refused_as_invalid(app: Flask) -> None:
    with app.test_request_context(LOGIN_PATH, method="POST", data="not json"):
        with pytest.raises(ValidationError) as refusal:
            app.view_functions["auth.login"]()

    assert refusal.value.message == "Request body must be a JSON object."
