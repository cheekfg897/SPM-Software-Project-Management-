"""HTTP routes for the venue module — ``/api/venues/*``.

Routes stay thin: decode JSON/query params, call a service, serialise the
result. All validation and business rules live in ``schemas.py`` /
``services.py``; all error responses come from the handlers in
:mod:`app.common.errors`.

Testing note: same as the auth module — route bodies are not unit-tested
this sprint (services/decorators are exercised directly with a mocked DB).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import requires_auth, requires_role
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import VenueBlock, venue_to_dict
from app.modules.venue.schemas import CalendarQuerySchema, load_or_raise

bp = Blueprint("venue", __name__, url_prefix="/api/venues")


def _iso(value: datetime) -> str:
    return value.isoformat()


def _calendar_entry_to_dict(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "start_time": _iso(entry["start_time"]),
        "end_time": _iso(entry["end_time"]),
        "kind": entry["kind"],
        "reason": entry["reason"],
    }


def _block_to_dict(block: VenueBlock) -> dict[str, Any]:
    return {
        "id": block.id,
        "venue_id": block.venue_id,
        "start_time": _iso(block.start_time),
        "end_time": _iso(block.end_time),
        "reason": block.reason,
    }


def _overlap_warning_to_dict(warning: dict[str, Any]) -> dict[str, Any]:
    return {
        "booking_ids": warning["booking_ids"],
        "overlap_start": _iso(warning["overlap_start"]),
        "overlap_end": _iso(warning["overlap_end"]),
    }


def _build_search_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Shape the search response body (SCRUM-35 AC4 — a clear message when empty)."""
    body: dict[str, Any] = {"results": results}
    if not results:
        body["message"] = "No venues match your search criteria."
    return body


# --------------------------------------------------------------------------
# SCRUM-25 — Update venue catalogue
# --------------------------------------------------------------------------


@bp.post("")
@requires_role(Role.VENUE_STAFF)
def create_venue() -> tuple[Response, int]:
    """Create a venue. Venue Staff only (AC3)."""
    venue = services.create_venue(request.get_json(silent=True))
    return jsonify(venue_to_dict(venue)), 201


@bp.get("")
@requires_auth
def list_venues() -> tuple[Response, int]:
    """List active venues. Read-only for everyone (AC3)."""
    venues = services.list_venues()
    return jsonify([venue_to_dict(v) for v in venues]), 200


@bp.get("/<int:venue_id>")
@requires_auth
def get_venue(venue_id: int) -> tuple[Response, int]:
    """Fetch one venue (active or not) by id. Read-only for everyone (AC3)."""
    venue = services.get_venue(venue_id)
    return jsonify(venue_to_dict(venue)), 200


@bp.patch("/<int:venue_id>")
@requires_role(Role.VENUE_STAFF)
def update_venue(venue_id: int) -> tuple[Response, int]:
    """Update a venue's editable fields. Venue Staff only (AC3)."""
    venue, overlap_warnings = services.update_venue(venue_id, request.get_json(silent=True))
    body = venue_to_dict(venue)
    body["overlap_warnings"] = [_overlap_warning_to_dict(w) for w in overlap_warnings]
    return jsonify(body), 200


@bp.post("/<int:venue_id>/deactivate")
@requires_role(Role.VENUE_STAFF)
def deactivate_venue(venue_id: int) -> tuple[Response, int]:
    """Deactivate a venue (AC5)."""
    venue = services.deactivate_venue(venue_id)
    return jsonify(venue_to_dict(venue)), 200


@bp.post("/<int:venue_id>/reactivate")
@requires_role(Role.VENUE_STAFF)
def reactivate_venue(venue_id: int) -> tuple[Response, int]:
    """Reactivate a previously deactivated venue (AC6)."""
    venue = services.reactivate_venue(venue_id)
    return jsonify(venue_to_dict(venue)), 200


@bp.post("/<int:venue_id>/blocks")
@requires_role(Role.VENUE_STAFF)
def create_block(venue_id: int) -> tuple[Response, int]:
    """Record a maintenance/renovation/safety block against a venue.

    Minimal supporting endpoint for SCRUM-26 AC2 — see services.create_block.
    """
    block = services.create_block(venue_id, request.get_json(silent=True))
    return jsonify(_block_to_dict(block)), 201


# --------------------------------------------------------------------------
# SCRUM-26 — View a venue's availability calendar
# --------------------------------------------------------------------------


@bp.get("/<int:venue_id>/calendar")
@requires_role(*INTERNAL_ROLES)
def get_calendar(venue_id: int) -> tuple[Response, int]:
    """Bookings + blocked periods across a date range. Internal roles only (AC4)."""
    query = load_or_raise(CalendarQuerySchema(), request.args)
    entries = services.get_venue_calendar(
        venue_id,
        query["range_start"],
        query["range_end"],
        viewer_role=g.current_user_role,
    )
    return jsonify([_calendar_entry_to_dict(e) for e in entries]), 200


# --------------------------------------------------------------------------
# SCRUM-35 — Search and filter venues against event requirements
# --------------------------------------------------------------------------


@bp.post("/search")
@requires_auth
def search_venues() -> tuple[Response, int]:
    """Search venues against an event's requirements (AC1-AC3)."""
    results = services.search_venues(request.get_json(silent=True))
    return jsonify(_build_search_response(results)), 200
