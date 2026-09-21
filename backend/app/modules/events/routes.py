"""HTTP routes for the events module — ``/api/events/*``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.
"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import requires_role
from app.modules.auth.permissions import Role
from app.modules.events.schemas import EventRequestSchema
from app.modules.events.services import (
    list_event_requests_for_organiser,
    submit_event_request,
)

bp = Blueprint("events", __name__, url_prefix="/api/events")

_event_request_schema = EventRequestSchema()


@bp.post("/requests")
@requires_role(Role.EVENT_ORGANISER)
def submit_request() -> tuple[Response, int]:
    """Submit an event request (SCRUM-19).

    Returns ``201`` with the new request's reference and status.
    """
    # The organiser is always the caller; the body cannot choose it.
    event_request = submit_event_request(g.current_user_id, request.get_json(silent=True))
    return jsonify(_event_request_schema.dump(event_request)), 201


@bp.get("/requests")
@requires_role(Role.EVENT_ORGANISER)
def list_my_requests() -> tuple[Response, int]:
    """List the caller's own event requests, newest first (SCRUM-19)."""
    event_requests = list_event_requests_for_organiser(g.current_user_id)
    return (
        jsonify({"event_requests": _event_request_schema.dump(event_requests, many=True)}),
        200,
    )
