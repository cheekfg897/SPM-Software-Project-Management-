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
)

bp = Blueprint("equipment", __name__, url_prefix="/api/equipment")

_equipment_type_schema = EquipmentTypeSchema()
_availability_schema = EquipmentAvailabilitySchema()
_reservation_schema = EquipmentReservationSchema()


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
@requires_role(*INTERNAL_ROLES)
def get_event_availability(reference: str) -> tuple[Response, int]:
    """What is free of each equipment type for the event's own period (SCRUM-45).

    Internal roles: Technical Support check it before reserving, and coordinators
    judge from it whether an event is feasible.
    """
    availability = services.equipment_availability_for_event(reference)
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
@requires_role(*INTERNAL_ROLES)
def list_event_reservations(reference: str) -> tuple[Response, int]:
    """The equipment reserved for the event, oldest first (SCRUM-46 AC4)."""
    reservations = services.list_reservations_for_event(reference)
    return jsonify(_reservation_schema.dump(reservations, many=True)), 200
