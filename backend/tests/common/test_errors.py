"""Unit tests for the shared error responses (SCRUM-21 AC5: refused requests).

Flask-JWT-Extended calls its error callbacks with either the error text or the token's
header and payload. One function serves every callback, so it is exercised with both.

The JSON error handlers run through ``app.handle_user_exception``, the call Flask makes
when a view raises, so each exception finds its handler as it would in a real request.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from flask import Flask
from werkzeug.exceptions import BadRequest, Gone, HTTPException, MethodNotAllowed, NotFound

from app.common.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
    invalid_token_response,
)

pytestmark = pytest.mark.scrum_21


def _handled(app: Flask, error: Exception) -> Any:
    """Raise ``error`` and hand it over the way Flask does when a view raises it."""
    with app.test_request_context("/"):
        try:
            raise error
        except Exception as raised:
            return app.handle_user_exception(raised)


def _gone_without_a_description() -> Gone:
    error = Gone()
    error.description = None
    return error


@pytest.mark.parametrize(
    "callback_args",
    [("Missing Authorization Header",), ({"alg": "HS256"}, {"sub": "7"})],
)
def test_invalid_token_response_uses_the_project_error_shape(
    callback_args: tuple[Any, ...],
) -> None:
    response, status = invalid_token_response(*callback_args)

    assert status == 401
    assert response.get_json() == {
        "error": "authentication_error",
        "message": "Missing, invalid or expired token.",
    }


@pytest.mark.parametrize(
    ("error_type", "status", "code"),
    [
        (ValidationError, 400, "validation_error"),
        (AuthenticationError, 401, "authentication_error"),
        (AuthorizationError, 403, "authorization_error"),
        (NotFoundError, 404, "not_found"),
        (ConflictError, 409, "conflict"),
    ],
)
def test_an_app_error_answers_with_its_own_status_and_the_standard_body(
    app: Flask, error_type: type[AppError], status: int, code: str
) -> None:
    response, answered_status = _handled(app, error_type("Said to the client."))

    assert answered_status == status
    assert response.get_json() == {"error": code, "message": "Said to the client."}


def test_an_app_error_with_details_sends_them_for_the_form_to_show_by_field(app: Flask) -> None:
    field_messages = {"email": ["Not a valid email address."]}

    response, status = _handled(app, ValidationError("Invalid request.", details=field_messages))

    assert status == 400
    assert response.get_json() == {
        "error": "validation_error",
        "message": "Invalid request.",
        "details": {"email": ["Not a valid email address."]},
    }


def test_empty_details_leave_the_key_out_of_the_body(app: Flask) -> None:
    response, _ = _handled(app, ConflictError("Clashes.", details={}))

    assert response.get_json() == {"error": "conflict", "message": "Clashes."}


@pytest.mark.parametrize(
    ("error", "status", "code", "message"),
    [
        (NotFound("No such page."), 404, "not_found", "No such page."),
        (MethodNotAllowed(description="Not here."), 405, "method_not_allowed", "Not here."),
        (BadRequest("Malformed JSON."), 400, "bad_request", "Malformed JSON."),
        (_gone_without_a_description(), 410, "gone", "Gone"),
    ],
)
def test_a_framework_error_answers_in_the_standard_body(
    app: Flask, error: HTTPException, status: int, code: str, message: str
) -> None:
    response, answered_status = _handled(app, error)

    assert answered_status == status
    assert response.get_json() == {"error": code, "message": message}


def test_an_unexpected_error_hides_what_went_wrong_from_the_client(app: Flask) -> None:
    response, status = _handled(app, RuntimeError("the connection string leaked here"))

    assert status == 500
    assert response.get_json() == {
        "error": "internal_error",
        "message": "An unexpected error occurred.",
    }


def test_an_unexpected_error_logs_its_traceback_for_the_team(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    error = RuntimeError("a bug in the app")

    with caplog.at_level(logging.ERROR, logger=app.logger.name):
        _handled(app, error)

    [record] = caplog.records
    assert record.getMessage() == "Unhandled exception: a bug in the app"
    assert record.exc_info is not None
    assert record.exc_info[1] is error
