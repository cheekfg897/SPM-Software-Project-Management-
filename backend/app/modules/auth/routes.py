"""HTTP routes for the auth module — ``/api/auth/*``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.

Testing note: route bodies are deliberately **not** unit-tested this sprint
(the suite exercises services/decorators directly with a mocked DB). They will
be covered by the HTTP-level integration tests planned for next sprint.
"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import requires_auth, requires_role
from app.common.validation import load_or_raise
from app.modules.auth.permissions import INTERNAL_ROLES
from app.modules.auth.schemas import LoginSchema, UserSchema
from app.modules.auth.services import authenticate_user, get_user_by_id, register_user

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_user_schema = UserSchema()


@bp.post("/register")
def register() -> tuple[Response, int]:
    """Create an account (SCRUM-65). Returns ``201`` with the public user shape."""
    # TODO(product): confirm internal-role provisioning with customer.
    # Currently every role — including event_coordinator, venue_staff and
    # technical_support_staff — can self-register here. If the customer wants
    # internal staff provisioned by an admin instead, restrict `role` in
    # RegisterSchema to EXTERNAL_ROLES and add an admin-only provisioning story.
    user = register_user(request.get_json(silent=True))
    return jsonify(_user_schema.dump(user)), 201


@bp.post("/login")
def login() -> tuple[Response, int]:
    """Exchange email + password for a JWT access token (SCRUM-6)."""
    data = load_or_raise(LoginSchema(), request.get_json(silent=True))
    result = authenticate_user(data["email"], data["password"])
    return (
        jsonify(
            {
                "access_token": result.access_token,
                "token_type": "Bearer",
                "user": {
                    "id": result.user.id,
                    "full_name": result.user.full_name,
                    "role": result.user.role.value,
                },
            }
        ),
        200,
    )


@bp.get("/me")
@requires_auth
def me() -> tuple[Response, int]:
    """Return the caller's own profile (SCRUM-21 — any authenticated user)."""
    user = get_user_by_id(g.current_user_id)
    return jsonify(_user_schema.dump(user)), 200


@bp.get("/internal-only")
@requires_role(*INTERNAL_ROLES)
def internal_only() -> tuple[Response, int]:
    """Example role-restricted route (SCRUM-21 — internal staff only).

    Exists purely to demonstrate the ``@requires_role`` pattern that feature
    modules will use in later sprints.
    """
    return (
        jsonify(
            {
                "message": "Hello, internal staff.",
                "role": g.current_user_role,
            }
        ),
        200,
    )
