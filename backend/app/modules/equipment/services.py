"""Business logic for the equipment module.

Same shape as the other modules: routes call these functions, tests call them
directly, and other modules call them instead of touching the models. Every
function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.equipment.models import EquipmentType
from app.modules.equipment.schemas import EditEquipmentTypeSchema
from app.modules.venue.services import get_venue


def _check_venue(venue_id: int | None, session: Session) -> None:
    """Reject a venue id that isn't in the catalogue (ADR-0014). ``None`` means a store.

    A deactivated venue still counts: it can go on holding equipment.
    """
    if venue_id is None:
        return
    try:
        get_venue(venue_id, session=session)
    except NotFoundError as exc:
        raise ValidationError(
            "Invalid request.", details={"venue_id": ["Venue not found."]}
        ) from exc


def _commit_or_conflict(session: Session) -> None:
    """Commit; a duplicate name becomes a 409 (ADR-0014)."""
    # The schema has already enforced every other constraint and the venue has been
    # checked, so the only integrity error left here is the unique name.
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("An equipment type with this name already exists.") from exc


def get_equipment_type(equipment_type_id: int, *, session: Session | None = None) -> EquipmentType:
    """Fetch one equipment type by id (SCRUM-27 AC2).

    Raises:
        NotFoundError: 404 — no such equipment type.
    """
    equipment_type = resolve_session(session).get(EquipmentType, equipment_type_id)
    if equipment_type is None:
        raise NotFoundError("Equipment type not found.")
    return equipment_type


def list_equipment_types(*, session: Session | None = None) -> list[EquipmentType]:
    """Every equipment type with its total quantity, by name (SCRUM-27 AC2).

    Names are unique (ADR-0014), so the order needs no tie-breaker.
    """
    stmt = select(EquipmentType).order_by(EquipmentType.name)
    return list(resolve_session(session).scalars(stmt))


def create_equipment_type(
    payload: Mapping[str, Any] | None, *, session: Session | None = None
) -> EquipmentType:
    """Add an equipment type to the catalogue (SCRUM-27 AC1).

    Args:
        payload: Decoded JSON body: ``name``, ``total_quantity``, an optional
            ``description``, and exactly one of ``venue_id`` or ``store_name``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The saved :class:`EquipmentType`.

    Raises:
        ValidationError: 400 — missing or invalid fields, no location or two, or an
            unknown venue.
        ConflictError: 409 — an equipment type with this name already exists.
    """
    data = load_or_raise(EditEquipmentTypeSchema(), payload)
    sess = resolve_session(session)
    _check_venue(data["venue_id"], sess)

    equipment_type = EquipmentType(
        name=data["name"],
        description=data["description"],
        total_quantity=data["total_quantity"],
        venue_id=data["venue_id"],
        store_name=data["store_name"],
    )
    sess.add(equipment_type)
    _commit_or_conflict(sess)
    return equipment_type


def update_equipment_type(
    equipment_type_id: int,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EquipmentType:
    """Change an equipment type's fields (SCRUM-27 AC1).

    Only the fields in ``payload`` change. Sending ``venue_id`` or ``store_name``
    replaces the location as a whole; sending neither leaves it (ADR-0014).

    Returns:
        The updated :class:`EquipmentType`.

    Raises:
        NotFoundError: 404 — no such equipment type.
        ValidationError: 400 — invalid values for the fields sent, or an unknown venue.
        ConflictError: 409 — another equipment type already has the new name.
    """
    schema = EditEquipmentTypeSchema()
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    equipment_type = get_equipment_type(equipment_type_id, session=sess)

    if "venue_id" in data or "store_name" in data:
        # Whichever one is sent, both are replaced, so the other is cleared.
        venue_id = data.pop("venue_id", None)
        store_name = data.pop("store_name", None)
        _check_venue(venue_id, sess)
        equipment_type.venue_id = venue_id
        equipment_type.store_name = store_name
    for key, value in data.items():
        setattr(equipment_type, key, value)

    _commit_or_conflict(sess)
    return equipment_type
