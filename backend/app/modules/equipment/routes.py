"""HTTP routes for the equipment module — ``/api/equipment/*``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.

Testing note: business logic is tested at the service layer against an
in-memory database. Each route's access control is tested by calling the
registered view function directly (``tests/equipment/test_equipment_permissions.py``).
"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from app.common.decorators import requires_role
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.equipment import services
from app.modules.equipment.schemas import (
    EquipmentAvailabilitySchema,
    EquipmentReservationSchema,
    EquipmentTypeSchema,
    OutOfServiceSchema,
)

bp = Blueprint("equipment", __name__, url_prefix="/api/equipment")

#: Who reads an event's equipment, as with its equipment lines (ADR-0019, ADR-0037).
#: Which events a coordinator may read is the services' job.
_EQUIPMENT_READERS = (Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF)

_equipment_type_schema = EquipmentTypeSchema()
_availability_schema = EquipmentAvailabilitySchema()
_reservation_schema = EquipmentReservationSchema()
_out_of_service_schema = OutOfServiceSchema()


@bp.post("/types")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def create_equipment_type() -> tuple[Response, int]:
    """Add an equipment type. Technical Support Staff only (SCRUM-27 AC3)."""
    equipment_type = services.create_equipment_type(request.get_json(silent=True))
    return jsonify(_equipment_type_schema.dump(equipment_type)), 201


@bp.get("/types")
@requires_role(*INTERNAL_ROLES)
def list_equipment_types() -> tuple[Response, int]:
    """Every equipment type with its total quantity, by name. Internal roles (AC2)."""
    equipment_types = services.list_equipment_types()
    return jsonify(_equipment_type_schema.dump(equipment_types, many=True)), 200


@bp.get("/types/<int:equipment_type_id>")
@requires_role(*INTERNAL_ROLES)
def get_equipment_type(equipment_type_id: int) -> tuple[Response, int]:
    """Fetch one equipment type. Internal roles (AC3)."""
    equipment_type = services.get_equipment_type(equipment_type_id)
    return jsonify(_equipment_type_schema.dump(equipment_type)), 200


@bp.patch("/types/<int:equipment_type_id>")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def update_equipment_type(equipment_type_id: int) -> tuple[Response, int]:
    """Change only the fields sent. Technical Support Staff only (SCRUM-27 AC3)."""
    equipment_type = services.update_equipment_type(
        equipment_type_id, request.get_json(silent=True)
    )
    return jsonify(_equipment_type_schema.dump(equipment_type)), 200


@bp.get("/events/<reference>/availability")
@requires_role(*_EQUIPMENT_READERS)
def get_event_availability(reference: str) -> tuple[Response, int]:
    """What is free of each equipment type for the event's own period (SCRUM-45).

    Technical Support check it before reserving, for any event; a coordinator judges
    from it whether an event assigned to them is feasible.
    """
    availability = services.equipment_availability_for_event(
        g.current_user_id, reference, viewer_role=Role(g.current_user_role)
    )
    return jsonify(_availability_schema.dump(availability, many=True)), 200


@bp.post("/events/<reference>/reservations")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def reserve_equipment(reference: str) -> tuple[Response, int]:
    """Reserve equipment for the event. Technical Support Staff only (SCRUM-46 AC1)."""
    reservation = services.reserve_equipment(
        reference, request.get_json(silent=True), reserved_by=g.current_user_id
    )
    return jsonify(_reservation_schema.dump(reservation)), 201


@bp.get("/events/<reference>/reservations")
@requires_role(*_EQUIPMENT_READERS)
def list_event_reservations(reference: str) -> tuple[Response, int]:
    """The equipment reserved for the event, oldest first (SCRUM-46 AC4).

    Technical Support for any event; a coordinator for an event assigned to them.
    """
    reservations = services.list_reservations_for_event(
        g.current_user_id, reference, viewer_role=Role(g.current_user_role)
    )
    return jsonify(_reservation_schema.dump(reservations, many=True)), 200


@bp.post("/types/<int:equipment_type_id>/out-of-service")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def mark_out_of_service(equipment_type_id: int) -> tuple[Response, int]:
    """Take units out of service as damaged or under maintenance (SCRUM-47 AC1)."""
    entry = services.mark_out_of_service(
        equipment_type_id, request.get_json(silent=True), recorded_by=g.current_user_id
    )
    return jsonify(_out_of_service_schema.dump(entry)), 201


@bp.get("/types/<int:equipment_type_id>/out-of-service")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def list_out_of_service(equipment_type_id: int) -> tuple[Response, int]:
    """The units of the type still out of service, oldest first (SCRUM-47 AC1)."""
    entries = services.list_out_of_service(equipment_type_id)
    return jsonify(_out_of_service_schema.dump(entries, many=True)), 200


@bp.post("/out-of-service/<int:entry_id>/return")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def return_to_service(entry_id: int) -> tuple[Response, int]:
    """Put units back in service so they count as available again (SCRUM-47 AC1)."""
    entry = services.return_to_service(entry_id, resolved_by=g.current_user_id)
    return jsonify(_out_of_service_schema.dump(entry)), 200


@bp.put("/reservations/<int:reservation_id>/preparation")
@requires_role(Role.TECHNICAL_SUPPORT_STAFF)
def update_preparation_details(reservation_id: int) -> tuple[Response, int]:
    """Record the preparation status and notes of a reservation (SCRUM-85 AC1)."""
    reservation = services.update_preparation_details(
        reservation_id, request.get_json(silent=True), updated_by=int(g.current_user_id)
    )
    return jsonify(_reservation_schema.dump(reservation)), 200
