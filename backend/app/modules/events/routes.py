"""HTTP routes for the events module — ``/api/events/*``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, g, jsonify, request
from marshmallow import Schema

from app.common.decorators import requires_role
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.events.schemas import (
    EQUIPMENT_EVENT_FIELDS,
    EVENT_LIST_FIELDS,
    CoordinatorContactSchema,
    DecisionSchema,
    EditedEventRequestSchema,
    EquipmentAwaitingActionSchema,
    EquipmentLineSchema,
    EventHistoryEntrySchema,
    EventRequestDetailSchema,
    EventRequestSchema,
    FieldChangeSchema,
)
from app.modules.events.services import (
    EventRecord,
    add_equipment_line,
    complete_event_request,
    decide_event_request,
    get_event_record_for_coordinator,
    get_event_record_for_organiser,
    list_equipment_lines,
    list_equipment_requests_awaiting_action,
    list_event_history,
    list_event_requests_for_coordinator,
    list_event_requests_for_organiser,
    list_event_requests_with_equipment,
    reassign_coordinator,
    remove_equipment_line,
    request_clarification,
    save_draft_event_request,
    start_event_request_review,
    submit_draft_event_request,
    submit_event_request,
    update_draft_event_request,
    update_equipment_line,
    update_event_request,
)

bp = Blueprint("events", __name__, url_prefix="/api/events")

_event_request_schema = EventRequestSchema()
_coordinator_contact_schema = CoordinatorContactSchema()
_decision_schema = DecisionSchema()
_event_request_detail_schema = EventRequestDetailSchema()
_equipment_line_schema = EquipmentLineSchema()
_equipment_event_schema = EventRequestSchema(only=EQUIPMENT_EVENT_FIELDS)
_equipment_awaiting_action_schema = EquipmentAwaitingActionSchema()
_edited_event_request_schema = EditedEventRequestSchema()
_field_change_schema = FieldChangeSchema()
_event_history_entry_schema = EventHistoryEntrySchema()
_event_list_row_schema = EventRequestSchema(only=EVENT_LIST_FIELDS)

#: What each role's event list says when it is empty (SCRUM-24 AC10, ADR-0026).
NO_ORGANISATION_REQUESTS_MESSAGE = "Your organisation has no event requests yet."
NO_ASSIGNED_REQUESTS_MESSAGE = "No event requests are assigned to you yet."
NO_EQUIPMENT_REQUESTS_MESSAGE = "No events have an equipment request yet."


def _event_list_body(listed: list[dict[str, Any]], empty_message: str) -> dict[str, Any]:
    """A role's event list; an empty one also says there are none (SCRUM-24 AC10).

    Copies ``search_venues``'s precedent (SCRUM-35 AC4): ``message`` is added only
    when the list is empty, so a client shows it whenever it is present.
    """
    body: dict[str, Any] = {"event_requests": listed}
    if not listed:
        body["message"] = empty_message
    return body


def _shown_or_none(schema: Schema, value: object | None) -> dict[str, Any] | None:
    """``value`` dumped with ``schema``, or ``None`` when there is nothing to show."""
    if value is None:
        return None
    return schema.dump(value)


def _event_record_body(record: EventRecord) -> dict[str, Any]:
    """A request's record as the API shows it: the request, coordinator and decision."""
    body = _event_request_detail_schema.dump(record.event_request)
    body["coordinator"] = _shown_or_none(_coordinator_contact_schema, record.coordinator)
    body["decision"] = _shown_or_none(_decision_schema, record.decision)
    return body


@bp.post("/requests")
@requires_role(Role.EVENT_ORGANISER)
def submit_request() -> tuple[Response, int]:
    """Submit an event request (SCRUM-19).

    Returns ``201`` with the new request's reference and status.
    """
    # The organiser is always the caller; the body cannot choose it.
    event_request = submit_event_request(g.current_user_id, request.get_json(silent=True))
    return jsonify(_event_request_schema.dump(event_request)), 201


# TODO: SCRUM-42 adds Venue Staff's list (AC4) and SCRUM-52 the Attendee's (AC7),
# in the same shape (ADR-0026).
@bp.get("/requests")
@requires_role(Role.EVENT_ORGANISER)
def list_my_requests() -> tuple[Response, int]:
    """List the caller's client organisation's event requests, newest first.

    Every organiser of the organisation sees the same list (SCRUM-7 AC1, AC3;
    SCRUM-19 AC5); an organiser with no organisation gets ``403`` (ADR-0020).
    """
    event_requests = list_event_requests_for_organiser(g.current_user_id)
    listed = _event_request_schema.dump(event_requests, many=True)
    return jsonify(_event_list_body(listed, NO_ORGANISATION_REQUESTS_MESSAGE)), 200


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
# either way, so none is ever taken for a reference.
@bp.get("/requests/assigned")
@requires_role(Role.EVENT_COORDINATOR)
def list_assigned_requests() -> tuple[Response, int]:
    """List the event requests assigned to the caller, newest first (SCRUM-30 AC5)."""
    event_requests = list_event_requests_for_coordinator(g.current_user_id)
    listed = _event_request_schema.dump(event_requests, many=True)
    return jsonify(_event_list_body(listed, NO_ASSIGNED_REQUESTS_MESSAGE)), 200


@bp.get("/requests/awaiting-equipment")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def list_equipment_awaiting_action() -> tuple[Response, int]:
    """Equipment still awaiting Technical Support, soonest event first (SCRUM-38).

    One list for all Technical Support Staff (ADR-0022).
    """
    awaiting = list_equipment_requests_awaiting_action()
    body = {"equipment_requests": _equipment_awaiting_action_schema.dump(awaiting, many=True)}
    return jsonify(body), 200


@bp.get("/requests/with-equipment")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def list_requests_with_equipment() -> tuple[Response, int]:
    """Every event that has an equipment request, newest first (SCRUM-24 AC5).

    Each row carries only ``EVENT_LIST_FIELDS``: the same name, date and times
    Technical Support's own event view (``/equipment``) shows, plus status.
    SCRUM-38's ``/awaiting-equipment`` stays their queue of what still needs
    doing (ADR-0026).
    """
    event_requests = list_event_requests_with_equipment()
    listed = _event_list_row_schema.dump(event_requests, many=True)
    return jsonify(_event_list_body(listed, NO_EQUIPMENT_REQUESTS_MESSAGE)), 200


@bp.get("/requests/<reference>")
@requires_role(Role.EVENT_ORGANISER, Role.EVENT_COORDINATOR)
def get_my_request(reference: str) -> tuple[Response, int]:
    """An event request's record: its status, coordinator, equipment and decision.

    Any organiser of the request's client organisation may open it; another
    organisation's request is ``404`` like an unknown reference (SCRUM-7 AC2, AC3,
    ADR-0012). An Event Coordinator opens the same sections, but only for a request
    assigned to them (SCRUM-24 AC2, AC9; ADR-0026, ADR-0034).
    The current status is SCRUM-22's; the assigned coordinator's name and email are
    SCRUM-30 AC3's, ``null`` until one is assigned (ADR-0018); the equipment lines are
    SCRUM-37 AC4's; the current decision, its reason and who made it are SCRUM-31
    AC9's, ``null`` until one is recorded (ADR-0028). Technical Support's view of the
    equipment is ``/equipment``.
    """
    if Role(g.current_user_role) is Role.EVENT_COORDINATOR:
        record = get_event_record_for_coordinator(g.current_user_id, reference)
    else:
        record = get_event_record_for_organiser(g.current_user_id, reference)
    return jsonify(_event_record_body(record)), 200


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


@bp.get("/requests/<reference>/history")
@requires_role(*INTERNAL_ROLES, Role.EVENT_ORGANISER)
def list_history(reference: str) -> tuple[Response, int]:
    """An event's history, oldest first (SCRUM-33).

    Internal staff may open any event's history; an Event Organiser only their own
    client organisation's, and never a ``field_changed`` entry about
    ``internal_planning_notes``.
    """
    history = list_event_history(
        g.current_user_id, reference, viewer_role=Role(g.current_user_role)
    )
    body = {"history": _event_history_entry_schema.dump(history, many=True)}
    return jsonify(body), 200


# --------------------------------------------------------------------------
# SCRUM-68 — mark an event as completed after it has taken place
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/complete")
@requires_role(Role.EVENT_COORDINATOR)
def complete_request(reference: str) -> tuple[Response, int]:
    """Mark a confirmed event completed once it has ended (SCRUM-68, ADR-0027).

    Only the request's assigned coordinator may; the service answers anyone else
    with the equipment routes' "not yours" 404. Returns ``200`` with the completed
    request. The caller is recorded in the event history as having done it (AC5).
    """
    event_request = complete_event_request(g.current_user_id, reference)
    return jsonify(_event_request_schema.dump(event_request)), 200


# --------------------------------------------------------------------------
# SCRUM-31 — review and decide a submitted request
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/review")
@requires_role(Role.EVENT_COORDINATOR)
def review_request(reference: str) -> tuple[Response, int]:
    """Move a submitted request assigned to the caller to under review (SCRUM-31 AC3).

    Only the request's own coordinator may; the service answers anyone else with the
    equipment routes' "not yours" 404 (AC5, ADR-0028). Returns ``200`` with the
    request.
    """
    event_request = start_event_request_review(g.current_user_id, reference)
    return jsonify(_event_request_schema.dump(event_request)), 200


@bp.post("/requests/<reference>/decide")
@requires_role(Role.EVENT_COORDINATOR)
def decide_request(reference: str) -> tuple[Response, int]:
    """Approve or reject a request assigned to the caller (SCRUM-31 AC1, AC4).

    The body is ``{"outcome": "approved" | "rejected", "reason": ...}``; a rejection
    needs a reason. Only the request's own coordinator may; the service answers
    anyone else with the "not yours" 404 (AC5, ADR-0028). Returns ``200`` with the
    request in its new status.
    """
    event_request = decide_event_request(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    return jsonify(_event_request_schema.dump(event_request)), 200


@bp.post("/requests/<reference>/request-clarification")
@requires_role(Role.EVENT_COORDINATOR)
def ask_for_clarification(reference: str) -> tuple[Response, int]:
    """Ask the organiser a question about a request under review (SCRUM-32 AC1).

    The body is ``{"message": ...}``. Only the request's own coordinator may; the
    service answers anyone else with the "not yours" 404 (ADR-0029). Returns ``200``
    with the request, now awaiting clarification.
    """
    event_request = request_clarification(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    return jsonify(_event_request_schema.dump(event_request)), 200
