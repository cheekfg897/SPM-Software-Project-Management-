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
    CalendarEntrySchema,
    CalendarQuerySchema,
    ConflictingBookingSchema,
    OverlapWarningSchema,
    VenueBlockSchema,
    VenueMatchSchema,
    VenueSchema,
)

bp = Blueprint("venue", __name__, url_prefix="/api/venues")

_venue_schema = VenueSchema()
_calendar_entry_schema = CalendarEntrySchema()
_venue_match_schema = VenueMatchSchema()
_overlap_warning_schema = OverlapWarningSchema()
_venue_block_schema = VenueBlockSchema()
_conflicting_booking_schema = ConflictingBookingSchema()

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
    now overlap (SCRUM-67 AC4).
    """
    venue, overlap_warnings = services.update_venue(venue_id, request.get_json(silent=True))
    body = _venue_schema.dump(venue)
    body["overlap_warnings"] = _overlap_warning_schema.dump(overlap_warnings, many=True)
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
