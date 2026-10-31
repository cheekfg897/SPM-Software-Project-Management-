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
    EQUIPMENT_LINES_EVENT_FIELDS,
    EVENT_LIST_FIELDS,
    ClarificationSchema,
    CoordinatorContactSchema,
    DecisionSchema,
    EditedEventRequestSchema,
    EquipmentAwaitingActionSchema,
    EquipmentLineSchema,
    EquipmentLineWithOutcomeSchema,
    EventAwaitingSafetyReviewSchema,
    EventHistoryEntrySchema,
    EventRequestDetailSchema,
    EventRequestSchema,
    FieldChangeSchema,
    OrganiserRecordSectionsSchema,
    RecordVenueArrangementSchema,
    RegistrationSettingsSchema,
    SafetyOutcomeSchema,
    StaffEventRecordSectionsSchema,
    StaffEventRequestSchema,
    UnassignedRequestSchema,
)
from app.modules.events.services import (
    EventRecord,
    OrganiserEventRecord,
    add_equipment_line,
    assign_coordinator_to_request,
    complete_event_request,
    confirm_event_request,
    decide_event_request,
    equipment_lines_as_shown,
    get_event_record_for_coordinator,
    get_event_record_for_organiser,
    get_staff_event_record,
    list_active_requests,
    list_equipment_lines,
    list_equipment_requests_awaiting_action,
    list_event_history,
    list_event_requests_for_coordinator,
    list_event_requests_for_organiser,
    list_event_requests_with_equipment,
    list_event_requests_with_venue_bookings,
    list_events_awaiting_safety_review,
    list_requests_for_each_coordinator,
    list_unassigned_requests,
    reassign_coordinator,
    record_equipment_outcome,
    record_safety_outcome,
    reject_event_during_planning,
    remove_equipment_line,
    request_clarification,
    resubmit_event_request,
    save_draft_event_request,
    start_event_request_review,
    submit_draft_event_request,
    submit_event_request,
    submit_for_safety_review,
    update_draft_event_request,
    update_equipment_line,
    update_event_request,
    update_registration_settings,
)

bp = Blueprint("events", __name__, url_prefix="/api/events")

_event_request_schema = EventRequestSchema()
_coordinator_contact_schema = CoordinatorContactSchema()
_decision_schema = DecisionSchema()
_clarification_schema = ClarificationSchema(many=True)
_event_request_detail_schema = EventRequestDetailSchema()
_equipment_line_schema = EquipmentLineSchema()
_equipment_line_with_outcome_schema = EquipmentLineWithOutcomeSchema()
_organiser_record_sections_schema = OrganiserRecordSectionsSchema()
_record_venue_arrangement_schema = RecordVenueArrangementSchema()
_safety_outcome_schema = SafetyOutcomeSchema()
_equipment_event_schema = EventRequestSchema(only=EQUIPMENT_LINES_EVENT_FIELDS)
_equipment_awaiting_action_schema = EquipmentAwaitingActionSchema()
_awaiting_safety_review_schema = EventAwaitingSafetyReviewSchema()
_edited_event_request_schema = EditedEventRequestSchema()
_field_change_schema = FieldChangeSchema()
_event_history_entry_schema = EventHistoryEntrySchema()
_event_list_row_schema = EventRequestSchema(only=EVENT_LIST_FIELDS)
_unassigned_request_schema = UnassignedRequestSchema()
_registration_settings_schema = RegistrationSettingsSchema()
_staff_event_request_schema = StaffEventRequestSchema()
_staff_record_sections_schema = StaffEventRecordSectionsSchema()

#: Who opens any submitted event's read-only record (SCRUM-24 AC9, AC10; ADR-0095). An
#: Event Coordinator opens only their own events, through ``/requests/<reference>``.
_STAFF_RECORD_READERS = (
    Role.VENUE_STAFF,
    Role.TECHNICAL_SUPPORT_STAFF,
    Role.SAFETY_OFFICER,
    Role.EVENT_COORDINATOR_LEAD,
)

#: What each role's event list says when it is empty (SCRUM-24 AC10, ADR-0026).
NO_ORGANISATION_REQUESTS_MESSAGE = "Your organisation has no event requests yet."
NO_ASSIGNED_REQUESTS_MESSAGE = "No event requests are assigned to you yet."
NO_EQUIPMENT_REQUESTS_MESSAGE = "No events have an equipment request yet."
NO_VENUE_BOOKINGS_MESSAGE = "No events have a venue booking request yet."
NO_UNASSIGNED_REQUESTS_MESSAGE = "No event requests are waiting to be assigned."
NO_ACTIVE_REQUESTS_MESSAGE = "There are no active event requests."
NO_WORKLOAD_MESSAGE = "There are no Event Coordinators."
NO_SAFETY_REVIEW_EVENTS_MESSAGE = "No events are waiting for a safety review."


def _event_list_body(
    listed: list[dict[str, Any]], empty_message: str, list_name: str = "event_requests"
) -> dict[str, Any]:
    """A role's list under ``list_name``; an empty one also says there are none.

    Copies ``search_venues``'s precedent (SCRUM-35 AC4): ``message`` is added only
    when the list is empty, so a client shows it whenever it is present (SCRUM-24
    AC10). The Lead's workload list and the Safety Officer's list name theirs
    differently.
    """
    body: dict[str, Any] = {list_name: listed}
    if not listed:
        body["message"] = empty_message
    return body


def _shown_or_none(schema: Schema, value: object | None) -> dict[str, Any] | None:
    """``value`` dumped with ``schema``, or ``None`` when there is nothing to show."""
    if value is None:
        return None
    return schema.dump(value)


def _event_record_body(record: EventRecord) -> dict[str, Any]:
    """A request's record as the API shows it.

    The request, its coordinator, its decision and its clarification exchange.
    """
    body = _event_request_detail_schema.dump(record.event_request)
    body["coordinator"] = _shown_or_none(_coordinator_contact_schema, record.coordinator)
    body["decision"] = _shown_or_none(_decision_schema, record.decision)
    body["clarifications"] = _clarification_schema.dump(record.clarifications)
    return body


def _organiser_event_record_body(record: OrganiserEventRecord) -> dict[str, Any]:
    """The record as the event's organiser is shown it: everything on it (ADR-0104).

    The sections every record shows, with the planning notes, every venue arrangement
    in full, the equipment lines with their outcome and reviewer in place of the
    staff's lines, the reservations and the current safety outcome (SCRUM-24 AC10).
    """
    body = _event_record_body(record)
    body.update(_organiser_record_sections_schema.dump(record))
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


# Venue Staff's list (AC4) is /requests/with-venue-bookings below (ADR-0085). The
# Attendee's (AC7) is the registration module's GET /api/events/registrations
# (ADR-0044).
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


@bp.get("/requests/unassigned")
@requires_role(Role.EVENT_COORDINATOR_LEAD)
def list_unassigned() -> tuple[Response, int]:
    """The requests waiting for the Lead, longest-waiting first (SCRUM-95 AC2).

    Only the Event Coordinator Lead may see the queue (ADR-0036); every other role,
    Event Coordinators included, gets ``403`` from the decorator.
    """
    event_requests = list_unassigned_requests()
    listed = _unassigned_request_schema.dump(event_requests, many=True)
    return jsonify(_event_list_body(listed, NO_UNASSIGNED_REQUESTS_MESSAGE)), 200


@bp.get("/requests/active")
@requires_role(Role.EVENT_COORDINATOR_LEAD)
def list_active() -> tuple[Response, int]:
    """Every active event with its status and coordinator, newest first (SCRUM-96 AC1).

    Only the Event Coordinator Lead may see it (AC3); the coordinator is shown by
    name, never by id.
    """
    listed = []
    for active in list_active_requests():
        row = _event_list_row_schema.dump(active.event_request)
        row["coordinator"] = active.coordinator_name
        listed.append(row)
    return jsonify(_event_list_body(listed, NO_ACTIVE_REQUESTS_MESSAGE)), 200


@bp.get("/coordinators/workload")
@requires_role(Role.EVENT_COORDINATOR_LEAD)
def list_coordinator_workload() -> tuple[Response, int]:
    """Every Event Coordinator with the active events assigned to them (SCRUM-96 AC3).

    Only the Event Coordinator Lead may see it (AC4); coordinators are shown by name,
    never by id. ``active_count`` is sent so the web app shows the count, an idle
    coordinator's 0 included, without counting for itself (ADR-0120).
    """
    listed = []
    for workload in list_requests_for_each_coordinator():
        events = _event_list_row_schema.dump(workload.assigned, many=True)
        listed.append(
            {
                "coordinator": workload.coordinator_name,
                "active_count": len(workload.assigned),
                "event_requests": events,
            }
        )
    return jsonify(_event_list_body(listed, NO_WORKLOAD_MESSAGE, "coordinators")), 200


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


@bp.get("/requests/with-venue-bookings")
@requires_role(Role.VENUE_STAFF)
def list_requests_with_venue_bookings() -> tuple[Response, int]:
    """Every event with a venue booking request or a booking, newest first (AC4).

    The same rows as Technical Support's ``/with-equipment``: ``EVENT_LIST_FIELDS``.
    One list for all Venue Staff (ADR-0085). SCRUM-43's ``/api/venues/booking-requests``
    stays their queue of requests still to decide.
    """
    event_requests = list_event_requests_with_venue_bookings()
    listed = _event_list_row_schema.dump(event_requests, many=True)
    return jsonify(_event_list_body(listed, NO_VENUE_BOOKINGS_MESSAGE)), 200


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
        body = _event_record_body(record)
        body["venue_arrangements"] = _record_venue_arrangement_schema.dump(
            record.venue_arrangements, many=True
        )
        # What the Safety Officer asked to rework, if anything (SCRUM-99 AC4).
        body["safety_outcome"] = _shown_or_none(_safety_outcome_schema, record.safety_outcome)
        return jsonify(body), 200
    organiser_record = get_event_record_for_organiser(g.current_user_id, reference)
    return jsonify(_organiser_event_record_body(organiser_record)), 200


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
    equipment is needed, and its status, so its coordinator is offered changes only
    while the lines can change (SCRUM-110, ADR-0116).
    """
    event_request, lines = list_equipment_lines(
        g.current_user_id, reference, viewer_role=Role(g.current_user_role)
    )
    body = {
        "event": _equipment_event_schema.dump(event_request),
        "equipment_lines": _equipment_line_with_outcome_schema.dump(
            equipment_lines_as_shown(lines), many=True
        ),
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


@bp.post("/requests/<reference>/equipment/<int:line_id>/outcome")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def record_outcome(reference: str, line_id: int) -> tuple[Response, int]:
    """Record or revise the outcome of this event's equipment review (SCRUM-48)."""
    line = record_equipment_outcome(
        g.current_user_id, reference, line_id, request.get_json(silent=True)
    )
    [shown] = equipment_lines_as_shown([line])
    return jsonify(_equipment_line_with_outcome_schema.dump(shown)), 200


# --------------------------------------------------------------------------
# SCRUM-87 — reassign an event to a different coordinator
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/reassign")
@requires_role(Role.EVENT_COORDINATOR_LEAD)
def reassign_request(reference: str) -> tuple[Response, int]:
    """Move a request to the Event Coordinator named by ``coordinator_email``.

    SCRUM-87, ADR-0021; the Event Coordinator Lead's alone since SCRUM-96, so an Event
    Coordinator is refused with ``403`` and the service is never reached. Returns
    ``200`` with the request and the new coordinator's name and email (AC6). The
    caller is recorded as having done it (AC7).
    """
    event_request, coordinator = reassign_coordinator(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    body = _event_request_schema.dump(event_request)
    body["coordinator"] = _coordinator_contact_schema.dump(coordinator)
    return jsonify(body), 200


# --------------------------------------------------------------------------
# SCRUM-95 — the Event Coordinator Lead assigns a coordinator
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/coordinator")
@requires_role(Role.EVENT_COORDINATOR_LEAD)
def assign_coordinator(reference: str) -> tuple[Response, int]:
    """Give a queued request to the Event Coordinator named by ``coordinator_email``.

    SCRUM-95 AC3, AC6, ADR-0036. Only the Event Coordinator Lead may: an Event
    Coordinator who calls this gets ``403`` from the decorator, so none can assign an
    event to themselves or anyone else. Returns ``200`` with the request and the
    coordinator's name and email. The Lead is recorded as having done it.
    """
    event_request, coordinator = assign_coordinator_to_request(
        reference, request.get_json(silent=True), assigned_by=g.current_user_id
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

    Internal staff may open any event's history, except an Event Coordinator, who sees
    only events assigned to them; an Event Organiser only their own client
    organisation's, and never a ``field_changed`` entry about
    ``internal_planning_notes``.
    """
    history = list_event_history(
        g.current_user_id, reference, viewer_role=Role(g.current_user_role)
    )
    body = {"history": _event_history_entry_schema.dump(history, many=True)}
    return jsonify(body), 200


# --------------------------------------------------------------------------
# SCRUM-24 AC9, AC10 — the read-only record other internal users open
# --------------------------------------------------------------------------


@bp.get("/requests/<reference>/staff-record")
@requires_role(*_STAFF_RECORD_READERS)
def get_staff_record(reference: str) -> tuple[Response, int]:
    """Any submitted event's read-only record, for internal users (ADR-0095).

    Venue Staff, Technical Support Staff and the Safety Officer (SCRUM-24 AC9) and the
    Event Coordinator Lead (AC10), for any event but a draft, assigned or not. The
    request with its notes, then each section: coordinator, decision, clarifications,
    venue arrangements and equipment with their preparation (SCRUM-84 AC2, SCRUM-85
    AC2) and the current safety outcome. Its history is ``/history``; it has no
    registrants (SCRUM-55).
    """
    staff_record = get_staff_event_record(reference)
    body = _staff_event_request_schema.dump(staff_record.record.event_request)
    body.update(_staff_record_sections_schema.dump(staff_record))
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


@bp.post("/requests/<reference>/resubmit")
@requires_role(Role.EVENT_ORGANISER)
def resubmit_request(reference: str) -> tuple[Response, int]:
    """Answer a clarification request, with any amendments, and resubmit (SCRUM-32 AC2).

    The body is ``{"response": ..., <any submission field>: ...}``. Any organiser of
    the request's client organisation may (ADR-0029). Returns ``200`` with the
    request, back under review.
    """
    event_request = resubmit_event_request(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    return jsonify(_event_request_schema.dump(event_request)), 200


# --------------------------------------------------------------------------
# SCRUM-69 — enable registration for an event and set its capacity
# --------------------------------------------------------------------------


@bp.patch("/requests/<reference>/registration")
@requires_role(Role.EVENT_COORDINATOR)
def update_registration(reference: str) -> tuple[Response, int]:
    """Enable or disable registration for the caller's request, and set its capacity.

    SCRUM-69, ADR-0043. Only the request's assigned coordinator may; the service
    answers anyone else with the equipment routes' "not yours" 404. Returns ``200``
    with the registration settings. The caller is recorded in the event history as
    having changed them (AC6).
    """
    event_request = update_registration_settings(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    return jsonify(_registration_settings_schema.dump(event_request)), 200


# --------------------------------------------------------------------------
# SCRUM-97 — submit an event for operational safety check
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/safety-review")
@requires_role(Role.EVENT_COORDINATOR)
def submit_request_for_safety_review(reference: str) -> tuple[Response, int]:
    """Send the caller's approved event to the Safety Officer (SCRUM-97, ADR-0047).

    Only the event's assigned coordinator may; the service answers anyone else with
    the equipment routes' "not yours" 404, and refuses an event whose venues or
    equipment aren't settled with a ``409`` naming each gap. Returns ``200`` with the
    request, now in Safety Review.
    """
    event_request = submit_for_safety_review(g.current_user_id, reference)
    return jsonify(_event_request_schema.dump(event_request)), 200


@bp.get("/requests/awaiting-safety-review")
@requires_role(Role.SAFETY_OFFICER)
def list_events_awaiting_review() -> tuple[Response, int]:
    """The events in Safety Review, soonest first, for the Safety Officer (SCRUM-97).

    Each comes with its status, venues, accessibility needs and equipment (AC5, AC6;
    SCRUM-24 AC6, AC8). One list for all Safety Officers (ADR-0047); an empty one
    says so (SCRUM-24 AC11).
    """
    awaiting = list_events_awaiting_safety_review()
    listed = _awaiting_safety_review_schema.dump(awaiting, many=True)
    return jsonify(_event_list_body(listed, NO_SAFETY_REVIEW_EVENTS_MESSAGE, "events")), 200


# --------------------------------------------------------------------------
# SCRUM-98 — record the operational safety check outcome
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/safety-outcome")
@requires_role(Role.SAFETY_OFFICER)
def record_request_safety_outcome(reference: str) -> tuple[Response, int]:
    """Record the Safety Officer's outcome for an event in Safety Review (SCRUM-98).

    The body is the ``outcome``, the ``checklist`` and, unless approving, a
    ``reason``. Returns ``200`` with the request in the status the outcome leaves it
    in: Safety Review on an approval, back in planning (``approved``) otherwise.
    """
    event_request = record_safety_outcome(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    return jsonify(_event_request_schema.dump(event_request)), 200


# --------------------------------------------------------------------------
# SCRUM-49 — confirm an event once its arrangements are in place
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/confirm")
@requires_role(Role.EVENT_COORDINATOR)
def confirm_request(reference: str) -> tuple[Response, int]:
    """Confirm the caller's event in Safety Review (SCRUM-49, ADR-0051).

    Only the event's assigned coordinator may; the service answers anyone else with
    the equipment routes' "not yours" 404, and refuses an event whose approvals
    aren't all in with a ``409`` naming each gap. Returns ``200`` with the request,
    now confirmed.
    """
    event_request = confirm_event_request(g.current_user_id, reference)
    return jsonify(_event_request_schema.dump(event_request)), 200


# --------------------------------------------------------------------------
# SCRUM-49 AC9, AC10 — reject an event during planning
# --------------------------------------------------------------------------


@bp.post("/requests/<reference>/reject")
@requires_role(Role.EVENT_COORDINATOR)
def reject_request(reference: str) -> tuple[Response, int]:
    """Reject the caller's event during planning, with a reason (SCRUM-49, ADR-0093).

    The body is ``{"reason": ...}``. Only the event's assigned coordinator may; the
    service answers anyone else with the equipment routes' "not yours" 404, and refuses
    an event that isn't Approved or in Safety Review with a ``409``. Its venues are
    released and its equipment returned. Returns ``200`` with the request, now rejected.
    """
    event_request = reject_event_during_planning(
        g.current_user_id, reference, request.get_json(silent=True)
    )
    return jsonify(_event_request_schema.dump(event_request)), 200
