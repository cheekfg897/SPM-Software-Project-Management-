"""HTTP routes for the events module — ``/api/events/*``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.
"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import requires_role
from app.modules.auth.permissions import Role
from app.modules.events.schemas import (
    EQUIPMENT_EVENT_FIELDS,
    CoordinatorContactSchema,
    EditedEventRequestSchema,
    EquipmentAwaitingActionSchema,
    EquipmentLineSchema,
    EventRequestDetailSchema,
    EventRequestSchema,
    FieldChangeSchema,
)
from app.modules.events.services import (
    add_equipment_line,
    get_event_record_for_organiser,
    list_equipment_lines,
    list_equipment_requests_awaiting_action,
    list_event_requests_for_coordinator,
    list_event_requests_for_organiser,
    reassign_coordinator,
    remove_equipment_line,
    save_draft_event_request,
    submit_draft_event_request,
    submit_event_request,
    update_draft_event_request,
    update_equipment_line,
    update_event_request,
)

bp = Blueprint("events", __name__, url_prefix="/api/events")

_event_request_schema = EventRequestSchema()
_coordinator_contact_schema = CoordinatorContactSchema()
_event_request_detail_schema = EventRequestDetailSchema()
_equipment_line_schema = EquipmentLineSchema()
_equipment_event_schema = EventRequestSchema(only=EQUIPMENT_EVENT_FIELDS)
_equipment_awaiting_action_schema = EquipmentAwaitingActionSchema()
_edited_event_request_schema = EditedEventRequestSchema()
_field_change_schema = FieldChangeSchema()


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
    """List the caller's client organisation's event requests, newest first.

    Every organiser of the organisation sees the same list (SCRUM-7 AC1, AC3;
    SCRUM-19 AC5); an organiser with no organisation gets ``403`` (ADR-0020).
    """
    event_requests = list_event_requests_for_organiser(g.current_user_id)
    return (
        jsonify({"event_requests": _event_request_schema.dump(event_requests, many=True)}),
        200,
    )


# --------------------------------------------------------------------------
# SCRUM-20 — save and resume a draft event request
# --------------------------------------------------------------------------


@bp.post("/requests/drafts")
@requires_role(Role.EVENT_ORGANISER)
def save_draft() -> tuple[Response, int]:
    """Save a new draft event request with only its name required (SCRUM-20 AC1).

    Returns ``201`` with the draft's reference and status.
    """
    draft = save_draft_event_request(g.current_user_id, request.get_json(silent=True))
    return jsonify(_event_request_schema.dump(draft)), 201


@bp.patch("/requests/drafts/<reference>")
@requires_role(Role.EVENT_ORGANISER)
def update_draft(reference: str) -> tuple[Response, int]:
    """Change the fields sent on one of the caller's own drafts (SCRUM-20 AC3)."""
    draft = update_draft_event_request(g.current_user_id, reference, request.get_json(silent=True))
    return jsonify(_event_request_schema.dump(draft)), 200


@bp.post("/requests/drafts/<reference>/submit")
@requires_role(Role.EVENT_ORGANISER)
def submit_draft(reference: str) -> tuple[Response, int]:
    """Submit one of the caller's own drafts under the full submission rules (SCRUM-20).

    Takes no body: what gets submitted is whatever was already saved on the draft.
    """
    submitted = submit_draft_event_request(g.current_user_id, reference)
    return jsonify(_event_request_schema.dump(submitted)), 200


# The static ``/requests/...`` paths above and below are declared before
# ``/requests/<reference>`` for readers; Werkzeug matches a static segment first
# either way, so "drafts", "assigned" and "awaiting-equipment" are never taken for a
# reference.
@bp.get("/requests/assigned")
@requires_role(Role.EVENT_COORDINATOR)
def list_assigned_requests() -> tuple[Response, int]:
    """List the event requests assigned to the caller, newest first (SCRUM-30 AC5)."""
    event_requests = list_event_requests_for_coordinator(g.current_user_id)
    return (
        jsonify({"event_requests": _event_request_schema.dump(event_requests, many=True)}),
        200,
    )


@bp.get("/requests/awaiting-equipment")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def list_equipment_awaiting_action() -> tuple[Response, int]:
    """Equipment still awaiting Technical Support, soonest event first (SCRUM-38).

    One list for all Technical Support Staff (ADR-0022).
    """
    awaiting = list_equipment_requests_awaiting_action()
    body = {"equipment_requests": _equipment_awaiting_action_schema.dump(awaiting, many=True)}
    return jsonify(body), 200


@bp.get("/requests/<reference>")
@requires_role(Role.EVENT_ORGANISER)
def get_my_request(reference: str) -> tuple[Response, int]:
    """One of the organisation's event requests: its status, coordinator and equipment.

    Any organiser of the request's client organisation may open it; another
    organisation's request is ``404`` like an unknown reference (SCRUM-7 AC2, AC3,
    ADR-0012). The current status is SCRUM-22's; the assigned coordinator's name and
    email are SCRUM-30 AC3's, ``null`` until one is assigned (ADR-0018); the
    equipment lines are SCRUM-37 AC4's.
    """
    event_request, coordinator = get_event_record_for_organiser(g.current_user_id, reference)
    body = _event_request_detail_schema.dump(event_request)
    if coordinator is None:
        body["coordinator"] = None
    else:
        body["coordinator"] = _coordinator_contact_schema.dump(coordinator)
    return jsonify(body), 200


# --------------------------------------------------------------------------
# SCRUM-37 — record what equipment an event needs
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/equipment")
@requires_role(Role.EVENT_COORDINATOR)
def add_equipment(reference: str) -> tuple[Response, int]:
    """Add an equipment line to a request assigned to the caller (SCRUM-37 AC1).

    Returns ``201`` with the new line. Technical Support Staff are notified (AC5).
    """
    line = add_equipment_line(g.current_user_id, reference, request.get_json(silent=True))
    return jsonify(_equipment_line_schema.dump(line)), 201


@bp.get("/requests/<reference>/equipment")
@requires_role(Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF)
def list_equipment(reference: str) -> tuple[Response, int]:
    """An event request's equipment lines with their status (SCRUM-37 AC4, ADR-0019).

    The event's date and times come too, so Technical Support know by when the
    equipment is needed.
    """
    event_request, lines = list_equipment_lines(
        g.current_user_id, reference, viewer_role=Role(g.current_user_role)
    )
    body = {
        "event": _equipment_event_schema.dump(event_request),
        "equipment_lines": _equipment_line_schema.dump(lines, many=True),
    }
    return jsonify(body), 200


@bp.patch("/requests/<reference>/equipment/<int:line_id>")
@requires_role(Role.EVENT_COORDINATOR)
def update_equipment(reference: str, line_id: int) -> tuple[Response, int]:
    """Change the fields sent on a line of a request assigned to the caller (AC2)."""
    line = update_equipment_line(
        g.current_user_id, reference, line_id, request.get_json(silent=True)
    )
    return jsonify(_equipment_line_schema.dump(line)), 200


@bp.delete("/requests/<reference>/equipment/<int:line_id>")
@requires_role(Role.EVENT_COORDINATOR)
def remove_equipment(reference: str, line_id: int) -> tuple[Response, int]:
    """Remove an equipment line of a request assigned to the caller (SCRUM-37 AC2)."""
    remove_equipment_line(g.current_user_id, reference, line_id)
    return Response(), 204


# --------------------------------------------------------------------------
# SCRUM-87 — reassign an event to a different coordinator
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/reassign")
@requires_role(Role.EVENT_COORDINATOR)
def reassign_request(reference: str) -> tuple[Response, int]:
    """Move a request to the Event Coordinator named by ``coordinator_email``.

    SCRUM-87, ADR-0021. Only the request's current coordinator may; the service
    answers anyone else with the equipment routes' "not yours" 404. Returns ``200``
    with the request and the new coordinator's name and email (AC6). The caller is
    recorded as having done it (AC7).
    """
    event_request, coordinator = reassign_coordinator(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    body = _event_request_schema.dump(event_request)
    body["coordinator"] = _coordinator_contact_schema.dump(coordinator)
    return jsonify(body), 200


# --------------------------------------------------------------------------
# SCRUM-33 — update event information and flag significant changes
# --------------------------------------------------------------------------


@bp.patch("/requests/<reference>")
@requires_role(Role.EVENT_COORDINATOR)
def update_request(reference: str) -> tuple[Response, int]:
    """Edit fields of a request assigned to the caller (SCRUM-33 AC1-AC4).

    Returns ``200`` with the edited request (including its programme and internal
    planning notes) and the list of changes made.
    """
    edit = update_event_request(g.current_user_id, reference, request.get_json(silent=True))
    body = _edited_event_request_schema.dump(edit.event_request)
    body["changes"] = _field_change_schema.dump(edit.changes, many=True)
    return jsonify(body), 200
