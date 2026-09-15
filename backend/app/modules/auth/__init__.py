"""Auth module — registration, login and role-based permissions.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.auth.services.get_user_by_id`
* :data:`app.modules.auth.permissions.Role` and the role groups
"""

from __future__ import annotations

from flask import Flask

from app.common.errors import error_response
from app.extensions import jwt


def register(app: Flask) -> None:
    """Attach the auth blueprint and JWT callbacks to ``app``."""
    from app.modules.auth.routes import bp

    app.register_blueprint(bp)
    _configure_jwt_error_shape()


def _configure_jwt_error_shape() -> None:
    """Make Flask-JWT-Extended's own errors use the project error shape.

    Our decorators catch token errors before these callbacks fire, but they
    are configured anyway so that anything using ``@jwt_required()`` directly
    (or future modules) can never leak a differently-shaped ``401``.

    Not unit-tested this sprint: only reachable via the HTTP layer.
    """

    @jwt.unauthorized_loader
    def _missing_token(reason: str):  # type: ignore[no-untyped-def]
        return error_response(401, "authentication_error", "Missing, invalid or expired token.")

    @jwt.invalid_token_loader
    def _invalid_token(reason: str):  # type: ignore[no-untyped-def]
        return error_response(401, "authentication_error", "Missing, invalid or expired token.")

    @jwt.expired_token_loader
    def _expired_token(jwt_header, jwt_payload):  # type: ignore[no-untyped-def]
        return error_response(401, "authentication_error", "Missing, invalid or expired token.")
