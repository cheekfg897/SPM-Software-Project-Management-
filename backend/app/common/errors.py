"""Centralised error handling.

Every error the API returns has the same JSON shape::

    {
        "error": "<machine_readable_code>",
        "message": "<human readable>",
        "details": {...},
    }

``details`` is optional and only present when there is structured information
to return (e.g. per-field validation messages).

Services raise the :class:`AppError` subclasses below; the Flask error handlers
registered by :func:`register_error_handlers` turn them into responses. Routes
never build error responses by hand.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

#: Shown for every missing, malformed or expired token, whichever code detects it.
#: A message, not a credential: bandit's S105 only reacts to "TOKEN" in the name.
INVALID_TOKEN_MESSAGE = "Missing, invalid or expired token."  # noqa: S105


class AppError(Exception):
    """Base class for all application-level errors.

    Attributes:
        status_code: HTTP status to return.
        error_code: Short machine-readable identifier.
        message: Human-readable explanation, safe to show to a client.
        details: Optional structured payload (e.g. field errors).
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.__class__.__doc__ or "Error")
        self.message: str = message or "An unexpected error occurred."
        self.details: dict[str, Any] | None = details

    def to_dict(self) -> dict[str, Any]:
        """Serialise into the standard error body."""
        body: dict[str, Any] = {"error": self.error_code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body


class ValidationError(AppError):
    """Request payload failed validation (400)."""

    status_code = 400
    error_code = "validation_error"


class AuthenticationError(AppError):
    """Missing, invalid or expired credentials/token (401)."""

    status_code = 401
    error_code = "authentication_error"


class AuthorizationError(AppError):
    """Authenticated, but not permitted to perform this action (403)."""

    status_code = 403
    error_code = "authorization_error"


class NotFoundError(AppError):
    """Requested resource does not exist (404)."""

    status_code = 404
    error_code = "not_found"


class ConflictError(AppError):
    """Request conflicts with existing state, e.g. duplicate email (409)."""

    status_code = 409
    error_code = "conflict"


def error_response(status_code: int, error_code: str, message: str) -> tuple[Response, int]:
    """Build a response in the standard error shape.

    Used by the handlers below and by the JWT callbacks so that token errors
    raised inside Flask-JWT-Extended look identical to our own errors.
    """
    return jsonify({"error": error_code, "message": message}), status_code


def invalid_token_response(*_callback_args: Any) -> tuple[Response, int]:
    """Build the ``401`` for a missing, malformed or expired token.

    Registered as Flask-JWT-Extended's error callbacks, which pass either the error text
    or the token's header and payload. The response is the same whatever went wrong, so
    those arguments are accepted and ignored.
    """
    return error_response(
        AuthenticationError.status_code, AuthenticationError.error_code, INVALID_TOKEN_MESSAGE
    )


def register_error_handlers(app: Flask) -> None:
    """Attach JSON error handlers to ``app``.

    ``tests/common/test_errors.py`` runs each handler the way Flask does when a
    view raises. The end-to-end journey in ``tests/e2e`` also drives ``AppError``
    responses through them over HTTP (ADR-0031).
    """

    @app.errorhandler(AppError)
    def _handle_app_error(exc: AppError) -> tuple[Response, int]:
        return jsonify(exc.to_dict()), exc.status_code

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException) -> tuple[Response, int]:
        # Werkzeug errors (404 for unknown routes, 405, malformed JSON, ...)
        code = exc.code or 500
        return error_response(
            code,
            (exc.name or "http_error").lower().replace(" ", "_"),
            exc.description or exc.name or "HTTP error",
        )

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception) -> tuple[Response, int]:
        # Anything not anticipated. Log the traceback, hide it from the client.
        app.logger.exception("Unhandled exception: %s", exc)
        return error_response(500, "internal_error", "An unexpected error occurred.")
