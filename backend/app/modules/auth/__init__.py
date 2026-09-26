"""Auth module — registration, login, role-based permissions and staff provisioning.

Public surface for other modules (import from here, not from sub-files):

* :func:`app.modules.auth.services.get_user_by_id`
* :func:`app.modules.auth.services.list_user_ids_with_role`
* :data:`app.modules.auth.permissions.Role` and the role groups

Registers the ``flask create-staff-user`` command (SCRUM-88, ADR-0023), the only
way to provision an internal staff account.
"""

from __future__ import annotations

from flask import Flask

from app.common.errors import invalid_token_response
from app.extensions import jwt


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


def register(app: Flask) -> None:
    """Attach the auth blueprint, JWT callbacks and CLI commands to ``app``."""
    from app.modules.auth.commands import create_staff_user_command
    from app.modules.auth.routes import bp

    app.register_blueprint(bp)
    _configure_jwt_error_shape()
    app.cli.add_command(create_staff_user_command)
