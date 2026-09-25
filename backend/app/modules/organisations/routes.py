"""HTTP routes for the organisations module — ``/api/organisations``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.

Both routes are for internal users only: client organisation details are not
shown to Attendees or Event Organisers (SCRUM-66 AC5, ADR-0013). Access control is
tested by calling the registered view functions directly
(``tests/organisations/test_client_organisations_permissions.py``).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.common.decorators import requires_role
from app.modules.auth.permissions import INTERNAL_ROLES
from app.modules.organisations import services
from app.modules.organisations.schemas import ClientOrganisationSchema

bp = Blueprint("organisations", __name__, url_prefix="/api/organisations")

_organisation_schema = ClientOrganisationSchema()


@bp.post("")
@requires_role(*INTERNAL_ROLES)
def create_organisation() -> tuple[Response, int]:
    """Record a client organisation (SCRUM-66 AC1). Internal users only."""
    organisation = services.create_organisation(request.get_json(silent=True))
    return jsonify(_organisation_schema.dump(organisation)), 201


@bp.get("")
@requires_role(*INTERNAL_ROLES)
def list_organisations() -> tuple[Response, int]:
    """List every client organisation by name. Internal users only (AC5)."""
    organisations = services.list_organisations()
    return jsonify({"organisations": _organisation_schema.dump(organisations, many=True)}), 200
