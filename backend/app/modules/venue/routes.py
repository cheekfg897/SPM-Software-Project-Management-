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

from flask import Blueprint, Response, jsonify, request

from app.common.decorators import requires_auth, requires_role
from app.modules.auth.permissions import Role
from app.modules.venue import services
from app.modules.venue.schemas import VenueSchema

bp = Blueprint("venue", __name__, url_prefix="/api/venues")

_venue_schema = VenueSchema()


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
    """Update a venue's editable fields. Venue Staff only (AC3)."""
    venue = services.update_venue(venue_id, request.get_json(silent=True))
    return jsonify(_venue_schema.dump(venue)), 200


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
