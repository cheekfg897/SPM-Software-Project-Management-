"""HTTP routes for the equipment module — ``/api/equipment/*``.

Routes stay thin: decode JSON, call a service, serialise the result. All
validation and business rules live in ``schemas.py`` / ``services.py``; all
error responses come from the handlers in :mod:`app.common.errors`.

Testing note: business logic is tested at the service layer against an
in-memory database. Each route's access control is tested by calling the
registered view function directly (``tests/equipment/test_equipment_permissions.py``).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.common.decorators import requires_role
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.equipment import services
from app.modules.equipment.schemas import EquipmentTypeSchema

bp = Blueprint("equipment", __name__, url_prefix="/api/equipment")

_equipment_type_schema = EquipmentTypeSchema()


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
