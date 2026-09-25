"""HTTP routes for the events module — ``/api/events/*``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.
"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import requires_role
from app.modules.auth.permissions import Role
from app.modules.events.schemas import CoordinatorContactSchema, EventRequestSchema
from app.modules.events.services import (
    get_event_record_for_organiser,
    list_event_requests_for_coordinator,
    list_event_requests_for_organiser,
    submit_event_request,
)

bp = Blueprint("events", __name__, url_prefix="/api/events")

_event_request_schema = EventRequestSchema()
_coordinator_contact_schema = CoordinatorContactSchema()


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


# Declared before ``/requests/<reference>`` for readers; Werkzeug matches the static
# segment first either way, so "assigned" is never taken for a reference.
@bp.get("/requests/assigned")
@requires_role(Role.EVENT_COORDINATOR)
def list_assigned_requests() -> tuple[Response, int]:
    """List the event requests assigned to the caller, newest first (SCRUM-30 AC5)."""
    event_requests = list_event_requests_for_coordinator(g.current_user_id)
    return (
        jsonify({"event_requests": _event_request_schema.dump(event_requests, many=True)}),
        200,
    )


@bp.get("/requests/<reference>")
@requires_role(Role.EVENT_ORGANISER)
def get_my_request(reference: str) -> tuple[Response, int]:
    """One of the caller's own event requests: its status and its coordinator.

    The current status is SCRUM-22's; the assigned coordinator's name and email are
    SCRUM-30 AC3's, ``null`` until one is assigned (ADR-0018).
    """
    event_request, coordinator = get_event_record_for_organiser(g.current_user_id, reference)
    body = _event_request_schema.dump(event_request)
    if coordinator is None:
        body["coordinator"] = None
    else:
        body["coordinator"] = _coordinator_contact_schema.dump(coordinator)
    return jsonify(body), 200
