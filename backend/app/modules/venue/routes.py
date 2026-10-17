"""HTTP routes for the venue module — ``/api/venues/*``.

Routes stay thin: decode JSON/query params, call a service, serialise the
result. All validation and business rules live in ``schemas.py`` /
``services.py``; all error responses come from the handlers in
:mod:`app.common.errors`.

Testing note: business logic is tested at the service layer against an
in-memory database. Each route's access control is tested by calling the
registered view function directly (``tests/venue/test_venue_permissions.py``).
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import requires_auth, requires_role
from app.common.validation import load_or_raise
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.schemas import (
    BlockOverlapWarningSchema,
    CalendarEntrySchema,
    CalendarQuerySchema,
    ConflictingBookingSchema,
    OverlapWarningSchema,
    SuitabilityResultSchema,
    VenueBlockSchema,
    VenueBookingRequestSchema,
    VenueMatchSchema,
    VenueSchema,
)

bp = Blueprint("venue", __name__, url_prefix="/api/venues")

_venue_schema = VenueSchema()
_calendar_entry_schema = CalendarEntrySchema()
_venue_match_schema = VenueMatchSchema()
_overlap_warning_schema = OverlapWarningSchema()
_block_overlap_warning_schema = BlockOverlapWarningSchema()
_venue_block_schema = VenueBlockSchema()
_conflicting_booking_schema = ConflictingBookingSchema()
_suitability_result_schema = SuitabilityResultSchema()
_booking_request_schema = VenueBookingRequestSchema()

#: SCRUM-35 AC4: what an empty search says.
NO_MATCHES_MESSAGE = "No venues match your search criteria."


# --------------------------------------------------------------------------
# SCRUM-25 — Update venue catalogue
# --------------------------------------------------------------------------


@bp.post("")
@requires_role(Role.VENUE_STAFF)
def create_venue() -> tuple[Response, int]:
    """Create a venue. Venue Staff only (AC3)."""
    venue = services.create_venue(request.get_json(silent=True))
    return jsonify(_venue_schema.dump(venue)), 201


@bp.get("")
@requires_auth
def list_venues() -> tuple[Response, int]:
    """List active venues. Read-only for everyone (AC3)."""
    venues = services.list_venues()
    return jsonify(_venue_schema.dump(venues, many=True)), 200


@bp.get("/<int:venue_id>")
@requires_auth
def get_venue(venue_id: int) -> tuple[Response, int]:
    """Fetch one venue (active or not) by id. Read-only for everyone (AC3)."""
    venue = services.get_venue(venue_id)
    return jsonify(_venue_schema.dump(venue)), 200


@bp.patch("/<int:venue_id>")
@requires_role(Role.VENUE_STAFF)
def update_venue(venue_id: int) -> tuple[Response, int]:
    """Update a venue's editable fields. Venue Staff only (SCRUM-25 AC4, SCRUM-67 AC5).

    If the setup or turnaround time changed, the response lists confirmed bookings that
    now overlap each other or run into a block (SCRUM-67 AC4, ADR-0033).
    """
    venue, overlap_warnings, block_overlap_warnings = services.update_venue(
        venue_id, request.get_json(silent=True)
    )
    body = _venue_schema.dump(venue)
    body["overlap_warnings"] = _overlap_warning_schema.dump(overlap_warnings, many=True)
    body["block_overlap_warnings"] = _block_overlap_warning_schema.dump(
        block_overlap_warnings, many=True
    )
    return jsonify(body), 200


@bp.post("/<int:venue_id>/deactivate")
@requires_role(Role.VENUE_STAFF)
def deactivate_venue(venue_id: int) -> tuple[Response, int]:
    """Deactivate a venue (AC5)."""
    venue = services.deactivate_venue(venue_id)
    return jsonify(_venue_schema.dump(venue)), 200


@bp.post("/<int:venue_id>/reactivate")
@requires_role(Role.VENUE_STAFF)
def reactivate_venue(venue_id: int) -> tuple[Response, int]:
    """Reactivate a previously deactivated venue (AC6)."""
    venue = services.reactivate_venue(venue_id)
    return jsonify(_venue_schema.dump(venue)), 200


# --------------------------------------------------------------------------
# SCRUM-26 — View a venue's availability calendar
# --------------------------------------------------------------------------


@bp.get("/<int:venue_id>/calendar")
@requires_role(*INTERNAL_ROLES)
def get_calendar(venue_id: int) -> tuple[Response, int]:
    """A venue's bookings and blocked periods in a range. Internal roles only (AC4)."""
    query = load_or_raise(CalendarQuerySchema(), request.args)
    entries = services.get_venue_calendar(
        venue_id,
        query["range_start"],
        query["range_end"],
        viewer_role=Role(g.current_user_role),
    )
    return jsonify(_calendar_entry_schema.dump(entries, many=True)), 200


# --------------------------------------------------------------------------
# SCRUM-35 — Search and filter venues against event requirements
# --------------------------------------------------------------------------


@bp.post("/search")
@requires_role(Role.EVENT_COORDINATOR)
def search_venues() -> tuple[Response, int]:
    """Venues that meet an event's needs and are free. Event Coordinators only."""
    matches = services.search_venues(request.get_json(silent=True))
    body: dict[str, Any] = {"results": _venue_match_schema.dump(matches, many=True)}
    if not matches:
        body["message"] = NO_MATCHES_MESSAGE
    return jsonify(body), 200


# --------------------------------------------------------------------------
# SCRUM-34 — Block a venue for maintenance or internal use
# --------------------------------------------------------------------------


@bp.post("/<int:venue_id>/blocks")
@requires_role(Role.VENUE_STAFF)
def block_venue(venue_id: int) -> tuple[Response, int]:
    """Block a venue for a period. Venue Staff only (SCRUM-34 AC1).

    The block is saved even over confirmed bookings; the response lists the ones it
    cuts into (AC2, ADR-0016).
    """
    block, conflicting_bookings = services.block_venue(venue_id, request.get_json(silent=True))
    body = _venue_block_schema.dump(block)
    body["conflicting_bookings"] = _conflicting_booking_schema.dump(conflicting_bookings, many=True)
    return jsonify(body), 201


@bp.get("/<int:venue_id>/blocks")
@requires_role(Role.VENUE_STAFF)
def list_venue_blocks(venue_id: int) -> tuple[Response, int]:
    """A venue's blocks with ids and reasons, to find one to remove. Venue Staff only.

    SCRUM-34 AC4, ADR-0016.
    """
    blocks = services.list_venue_blocks(venue_id)
    return jsonify(_venue_block_schema.dump(blocks, many=True)), 200


@bp.delete("/<int:venue_id>/blocks/<int:block_id>")
@requires_role(Role.VENUE_STAFF)
def remove_venue_block(venue_id: int, block_id: int) -> tuple[Response, int]:
    """Remove a block, freeing the venue again. Venue Staff only (SCRUM-34 AC4)."""
    services.remove_venue_block(venue_id, block_id)
    return Response(), 204


# --------------------------------------------------------------------------
# SCRUM-36 — Check whether a venue suits an event
# --------------------------------------------------------------------------


@bp.post("/<int:venue_id>/suitability")
@requires_role(Role.EVENT_COORDINATOR, Role.VENUE_STAFF)
def check_suitability(venue_id: int) -> tuple[Response, int]:
    """Whether a venue meets an event's requirements. Coordinators and Venue Staff.

    Lists every requirement the venue fails. Always ``200``: an unsuitable venue is a
    result, not an error (ADR-0017).
    """
    result = services.check_venue_suitability(venue_id, request.get_json(silent=True))
    return jsonify(_suitability_result_schema.dump(result)), 200


# --------------------------------------------------------------------------
# SCRUM-42 — Request a venue booking for an approved event
# --------------------------------------------------------------------------


@bp.post("/events/<reference>/booking-requests")
@requires_role(Role.EVENT_COORDINATOR)
def raise_booking_request(reference: str) -> tuple[Response, int]:
    """Raise a Pending booking request for the coordinator's approved event."""
    shown = services.raise_booking_request(
        reference, request.get_json(silent=True), requested_by=int(g.current_user_id)
    )
    return jsonify(_booking_request_schema.dump(shown)), 201


@bp.get("/events/<reference>/booking-requests")
@requires_role(Role.EVENT_COORDINATOR)
def list_booking_requests(reference: str) -> tuple[Response, int]:
    """The booking requests raised for the coordinator's event, with its details."""
    shown = services.list_booking_requests_for_event(
        reference, coordinator_id=int(g.current_user_id)
    )
    return jsonify(_booking_request_schema.dump(shown, many=True)), 200


@bp.post("/events/<reference>/booking-requests/<int:arrangement_id>/withdraw")
@requires_role(Role.EVENT_COORDINATOR)
def withdraw_arrangement(reference: str, arrangement_id: int) -> tuple[Response, int]:
    """Retract one of the coordinator's event's venue arrangements."""
    shown = services.withdraw_arrangement(
        reference, arrangement_id, coordinator_id=int(g.current_user_id)
    )
    return jsonify(_booking_request_schema.dump(shown)), 200


@bp.post("/events/<reference>/booking-requests/cancel-all")
@requires_role(Role.EVENT_COORDINATOR)
def cancel_all_arrangements(reference: str) -> tuple[Response, int]:
    """Retire every venue arrangement the coordinator's event still has."""
    shown = services.cancel_all_arrangements(reference, coordinator_id=int(g.current_user_id))
    return jsonify(_booking_request_schema.dump(shown, many=True)), 200


@bp.patch("/events/<reference>/booking-requests/<int:arrangement_id>")
@requires_role(Role.EVENT_COORDINATOR)
def change_arrangement(reference: str, arrangement_id: int) -> tuple[Response, int]:
    """Change one of the coordinator's event's pending venue arrangements."""
    shown = services.change_arrangement(
        reference,
        arrangement_id,
        request.get_json(silent=True),
        coordinator_id=int(g.current_user_id),
    )
    return jsonify(_booking_request_schema.dump(shown)), 200


# --------------------------------------------------------------------------
# SCRUM-43 — Venue Staff approve or reject a booking request
# --------------------------------------------------------------------------


@bp.get("/booking-requests")
@requires_role(Role.VENUE_STAFF)
def list_pending_booking_requests() -> tuple[Response, int]:
    """Every booking request waiting for a decision, the earliest event first."""
    shown = services.list_pending_booking_requests()
    return jsonify(_booking_request_schema.dump(shown, many=True)), 200


@bp.post("/booking-requests/<int:request_id>/decision")
@requires_role(Role.VENUE_STAFF)
def decide_booking_request(request_id: int) -> tuple[Response, int]:
    """Approve or reject a Pending booking request, with a reason."""
    shown = services.decide_booking_request(
        request_id, request.get_json(silent=True), decided_by=int(g.current_user_id)
    )
    return jsonify(_booking_request_schema.dump(shown)), 200


# --------------------------------------------------------------------------
# SCRUM-84 — Venue Staff record a booking's preparation details
# --------------------------------------------------------------------------


@bp.put("/booking-requests/<int:request_id>/preparation")
@requires_role(Role.VENUE_STAFF)
def update_preparation_details(request_id: int) -> tuple[Response, int]:
    """Record the preparation status and notes of an approved booking."""
    shown = services.update_preparation_details(
        request_id, request.get_json(silent=True), updated_by=int(g.current_user_id)
    )
    return jsonify(_booking_request_schema.dump(shown)), 200


# --------------------------------------------------------------------------
# SCRUM-75 — Venue Staff hold a venue tentatively
# --------------------------------------------------------------------------


@bp.post("/booking-requests/<int:request_id>/hold")
@requires_role(Role.VENUE_STAFF)
def place_booking_hold(request_id: int) -> tuple[Response, int]:
    """Hold the request's venue tentatively until an expiry, instead of booking it."""
    shown = services.place_booking_hold(request_id, request.get_json(silent=True))
    return jsonify(_booking_request_schema.dump(shown)), 200


@bp.patch("/booking-requests/<int:request_id>/hold")
@requires_role(Role.VENUE_STAFF)
def change_hold_expiry(request_id: int) -> tuple[Response, int]:
    """Move the expiry of the request's active hold."""
    shown = services.change_hold_expiry(request_id, request.get_json(silent=True))
    return jsonify(_booking_request_schema.dump(shown)), 200
