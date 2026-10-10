"""Business logic for the equipment module.

Same shape as the other modules: routes call these functions, tests call them
directly, and other modules call them instead of touching the models. Every
function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.database import resolve_session
from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.equipment.models import EquipmentOutOfService, EquipmentReservation, EquipmentType
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


def _overlapping(starts_at: datetime, ends_at: datetime) -> ColumnElement[bool]:
    """Match reservations overlapping ``starts_at`` to ``ends_at`` (SCRUM-45 AC4, AC5).

    The one definition of overlap, used by every availability query. Both comparisons
    are strict, so a reservation ending exactly when another starts does not overlap
    it. Unlike a venue (ADR-0011), equipment has no setup or turnaround buffer: a
    projector can go from one event straight to the next, so only the events' own
    periods count.
    """
    return (EquipmentReservation.starts_at < ends_at) & (EquipmentReservation.ends_at > starts_at)


def _reserved_quantity(
    equipment_type_id: int, starts_at: datetime, ends_at: datetime, session: Session
) -> int:
    """Units of the type reserved for any event overlapping the period."""
    statement = select(func.coalesce(func.sum(EquipmentReservation.quantity), 0)).where(
        EquipmentReservation.equipment_type_id == equipment_type_id,
        _overlapping(starts_at, ends_at),
    )
    return session.scalar(statement)


def _out_of_service_quantity(equipment_type_id: int, session: Session) -> int:
    """Units of the type recorded as damaged or under maintenance and not yet back."""
    statement = select(func.coalesce(func.sum(EquipmentOutOfService.quantity), 0)).where(
        EquipmentOutOfService.equipment_type_id == equipment_type_id,
        EquipmentOutOfService.resolved_at.is_(None),
    )
    return session.scalar(statement)


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


def available_quantity(
    equipment_type_id: int,
    starts_at: datetime,
    ends_at: datetime,
    *,
    session: Session | None = None,
) -> int:
    """Units of an equipment type free for the period ``starts_at`` to ``ends_at``.

    The units held, less those reserved for overlapping events (SCRUM-45 AC1, AC4,
    AC5) and those out of service (AC2), never below zero: units can break after they
    were reserved, leaving more committed than held. An out-of-service row is not tied
    to a period in this model (ADR-0037), so every unresolved row reduces every period.

    Args:
        equipment_type_id: The equipment type to count.
        starts_at: Start of the period, timezone-aware UTC.
        ends_at: End of the period, timezone-aware UTC.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such equipment type.
    """
    sess = resolve_session(session)
    equipment_type = get_equipment_type(equipment_type_id, session=sess)
    reserved = _reserved_quantity(equipment_type_id, starts_at, ends_at, sess)
    out_of_service = _out_of_service_quantity(equipment_type_id, sess)
    return max(equipment_type.total_quantity - reserved - out_of_service, 0)


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
