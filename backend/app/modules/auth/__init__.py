"""Auth module — registration, login, role-based permissions and staff provisioning.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.auth.services.get_user_by_id`
* :func:`app.modules.auth.services.list_user_ids_with_role`
* :data:`app.modules.auth.permissions.Role` and the role groups

Registers the ``flask create-staff-user`` command (SCRUM-88, ADR-0023), the only
way to provision an internal staff account.
"""

from __future__ import annotations

from typing import Any

from flask import Flask

from app.common.errors import invalid_token_response
from app.extensions import jwt
from app.modules.auth.services import is_token_revoked


def _configure_jwt_error_shape() -> None:
    """Make Flask-JWT-Extended's own errors use the project error shape.

    Our decorators catch token errors before these callbacks fire, but they
    are configured anyway so that anything using ``@jwt_required()`` directly
    (or future modules) can never leak a differently-shaped ``401``.

    The response is unit-tested in ``tests/common/test_errors.py``. That
    Flask-JWT-Extended calls it is only observable through the HTTP layer.
    """
    jwt.unauthorized_loader(invalid_token_response)
    jwt.invalid_token_loader(invalid_token_response)
    jwt.expired_token_loader(invalid_token_response)
    jwt.revoked_token_loader(invalid_token_response)


def _is_logged_out(_jwt_header: dict[str, Any], jwt_payload: dict[str, Any]) -> bool:
    """Flask-JWT-Extended's blocklist check: was this token logged out? (SCRUM-89).

    It runs inside ``verify_jwt_in_request``, which every auth decorator calls, so a
    logged-out token is refused on every protected route with the usual ``401``, and
    read as a visitor on a public one (ADR-0110).
    """
    return is_token_revoked(jwt_payload["jti"])


def register(app: Flask) -> None:
    """Attach the auth blueprint, JWT callbacks and blocklist, and CLI commands."""
    from app.modules.auth.commands import create_staff_user_command
    from app.modules.auth.routes import bp

    app.register_blueprint(bp)
    _configure_jwt_error_shape()
    jwt.token_in_blocklist_loader(_is_logged_out)
    app.cli.add_command(create_staff_user_command)
