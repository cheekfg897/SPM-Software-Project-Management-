"""HTTP routes for the registration module — ``/api/events/catalogue`` and friends.

Routes stay thin: read the request, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all error
responses come from the handlers in :mod:`app.common.errors`.

The blueprint shares ``/api/events`` with the events module, because ADR-0032 puts the
catalogue there; the two blueprints' paths do not overlap.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import optional_auth, requires_role
from app.modules.auth.permissions import Role
from app.modules.registration.schemas import (
    CataloguePageSchema,
    MyEventsWindow,
    MyRegistrationSchema,
    RegistrantListSchema,
    RegistrationSchema,
)
from app.modules.registration.services import (
    list_catalogue,
    list_my_registrations,
    list_registrants,
    register_for_event,
)

bp = Blueprint("registration", __name__, url_prefix="/api/events")

#: What an attendee's empty list says, for each window (SCRUM-24 AC11, ADR-0044).
NO_EVENTS_MESSAGES = {
    MyEventsWindow.UPCOMING: "You have no upcoming events.",
    MyEventsWindow.PAST: "You have no past events.",
}

_catalogue_page_schema = CataloguePageSchema()
_registration_schema = RegistrationSchema()
_my_registration_schema = MyRegistrationSchema(many=True)
_registrant_list_schema = RegistrantListSchema()


@bp.get("/catalogue")
@optional_auth
def browse_catalogue() -> Response:
    """List the events open for registration (SCRUM-52 AC1).

    Public. A valid token only decides ``is_registered``: it is the caller's.
    """
    page = list_catalogue(request.args.to_dict(), g.current_user_id)
    return jsonify(_catalogue_page_schema.dump(page))


@bp.post("/catalogue/<int:event_id>/registrations")
@requires_role(Role.ATTENDEE)
def register_for_catalogue_event(event_id: int) -> tuple[Response, int]:
    """Register the caller for an event (SCRUM-52 AC2).

    Returns ``201`` with the registration. There is no body: the account is the
    registration (ADR-0032).
    """
    registration = register_for_event(g.current_user_id, event_id)
    return jsonify(_registration_schema.dump(registration)), 201


@bp.get("/registrations")
@requires_role(Role.ATTENDEE)
def view_my_registrations() -> Response:
    """List the caller's own upcoming or past registrations (SCRUM-52 AC5, ADR-0044).

    An empty list says so (SCRUM-24 AC11).
    """
    listing = list_my_registrations(g.current_user_id, request.args.to_dict())
    body: dict[str, Any] = {"registrations": _my_registration_schema.dump(listing.registrations)}
    if not listing.registrations:
        body["message"] = NO_EVENTS_MESSAGES[listing.when]
    return jsonify(body)


@bp.get("/requests/<reference>/registrations")
@requires_role(Role.EVENT_ORGANISER, Role.EVENT_COORDINATOR)
def view_registrants(reference: str) -> Response:
    """List who has registered for an event, with its count and capacity (SCRUM-55).

    An Event Organiser sees their client organisation's events, an Event Coordinator
    the events assigned to them; anyone else's is ``404``, like an unknown reference
    (ADR-0012). Attendees are refused with ``403`` by the decorator, so none sees
    another's details (AC5).
    """
    listing = list_registrants(g.current_user_id, reference, viewer_role=Role(g.current_user_role))
    return jsonify(_registrant_list_schema.dump(listing))
