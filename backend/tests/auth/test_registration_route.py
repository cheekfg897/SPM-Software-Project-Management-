"""Unit tests for the sign-up route, ``POST /api/auth/register`` (SCRUM-65 AC1, AC3).

``tests/auth/test_registration.py`` checks the service. These check what the route
adds: it passes the body on as sent, answers ``201`` with the public user shape and
never echoes the password. They run the real service on the in-memory database and
read the saved row back, so the account must really exist for them to pass.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role

pytestmark = pytest.mark.scrum_65

REGISTER_PATH = "/api/auth/register"
REGISTER_ROUTE = ("auth.register", "POST", REGISTER_PATH, {}, None)


def _saved_users(db_session: Session) -> list[User]:
    """Every account in the database, read past the session's cache."""
    db_session.expire_all()
    return list(db_session.scalars(select(User)))


def test_a_valid_body_saves_the_account_and_answers_201_with_the_public_shape(
    call_route: Callable[..., Any],
    db_session: Session,
    valid_registration_payload: dict[str, Any],
) -> None:
    response, status = call_route(*REGISTER_ROUTE, body=valid_registration_payload)

    assert status == 201
    [saved] = _saved_users(db_session)
    assert saved.email == "new.user@example.com"
    assert response.get_json() == {
        "id": saved.id,
        "email": "new.user@example.com",
        "full_name": "New User",
        "role": "attendee",
        "organisation_id": None,
        "created_at": saved.created_at.isoformat(),
    }


def test_the_answer_never_carries_the_password_or_its_hash(
    call_route: Callable[..., Any],
    db_session: Session,
    valid_registration_payload: dict[str, Any],
) -> None:
    response, _ = call_route(*REGISTER_ROUTE, body=valid_registration_payload)

    [saved] = _saved_users(db_session)
    answer = response.get_data(as_text=True)
    assert valid_registration_payload["password"] not in answer
    assert saved.password_hash not in answer


def test_an_internal_role_is_refused_by_field_and_no_account_is_saved(
    call_route: Callable[..., Any],
    db_session: Session,
    valid_registration_payload: dict[str, Any],
) -> None:
    body = {**valid_registration_payload, "role": Role.EVENT_COORDINATOR.value}

    with pytest.raises(ValidationError) as refusal:
        call_route(*REGISTER_ROUTE, body=body)

    assert refusal.value.details == {"role": ["Role must be one of: attendee, event_organiser."]}
    assert _saved_users(db_session) == []


def test_a_body_that_is_not_json_is_refused_as_invalid(app: Flask) -> None:
    with app.test_request_context(REGISTER_PATH, method="POST", data="not json"):
        with pytest.raises(ValidationError) as refusal:
            app.view_functions["auth.register"]()

    assert refusal.value.message == "Request body must be a JSON object."
