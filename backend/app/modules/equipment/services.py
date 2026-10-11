"""Business logic for the equipment module.

Same shape as the other modules: routes call these functions, tests call them
directly, and other modules call them instead of touching the models. Every
function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.common.database import resolve_session
from app.common.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.auth.services import get_user_full_names
from app.modules.equipment.models import EquipmentOutOfService, EquipmentReservation, EquipmentType
from app.modules.equipment.schemas import EditEquipmentTypeSchema, EquipmentUnitsSchema

# The module, not its names: events.services imports this module too (to check a
# catalogue entry), and module-attribute access is what lets the two import each other.
from app.modules.events import services as events_services
from app.modules.venue.services import get_venue

EQUIPMENT_TYPE_NOT_FOUND_MESSAGE = "Equipment type not found."


class EquipmentNotReservableError(AppError):
    """The event is over or will not happen, so nothing can be reserved for it (409)."""

    status_code = 409
    error_code = "equipment_not_reservable"


@dataclass(frozen=True)
class EquipmentAvailability:
    """One equipment type's availability for an event, with any shortfall (AC3)."""

    equipment_type_id: int
    equipment_type_name: str
    #: Units free for the event's own period.
    available: int
    #: Units the event's lines ask for; 0 when it has no line for the type.
    requested: int
    #: Units short of the request; 0 when the request is met.
    shortfall: int


@dataclass(frozen=True)
class ReservationAsShown:
    """One reservation as the event record shows it (SCRUM-46 AC4).

    No user id: the reserver is shown by name, as the events module shows its actors.
    """

    id: int
    equipment_type_id: int
    equipment_type_name: str
    quantity: int
    starts_at: datetime
    ends_at: datetime
    #: The reserver's full name, or ``None`` if they no longer exist.
    reserved_by: str | None
    created_at: datetime


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


def _locked_equipment_type(equipment_type_id: int, session: Session) -> EquipmentType:
    """The equipment type, its row locked until the transaction ends (Review Focus 3).

    ``SELECT … FOR UPDATE``: a second reservation of the same type waits here until
    the first commits, then counts what is free with the first one's units taken, so
    the two can never reserve more than was free between them. SQLite ignores the
    lock; Postgres honours it.

    Raises:
        ValidationError: 400 on ``equipment_type_id`` — no such equipment type.
    """
    # populate_existing: a copy the session loaded earlier may predate another
    # request's commit, so the locked row must overwrite it, not be skipped as known.
    statement = (
        select(EquipmentType)
        .where(EquipmentType.id == equipment_type_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    equipment_type = session.scalar(statement)
    if equipment_type is None:
        raise ValidationError(
            "Invalid request.", details={"equipment_type_id": [EQUIPMENT_TYPE_NOT_FOUND_MESSAGE]}
        )
    return equipment_type


def _as_shown(
    reservations: list[EquipmentReservation], session: Session
) -> list[ReservationAsShown]:
    """The reservations with their reservers' names, looked up in one query."""
    reserver_ids = {reservation.reserved_by for reservation in reservations}
    names = get_user_full_names(reserver_ids, session=session)
    shown = []
    for reservation in reservations:
        shown.append(
            ReservationAsShown(
                id=reservation.id,
                equipment_type_id=reservation.equipment_type_id,
                equipment_type_name=reservation.equipment_type.name,
                quantity=reservation.quantity,
                starts_at=reservation.starts_at,
                ends_at=reservation.ends_at,
                reserved_by=names.get(reservation.reserved_by),
                created_at=reservation.created_at,
            )
        )
    return shown


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
        raise NotFoundError(EQUIPMENT_TYPE_NOT_FOUND_MESSAGE)
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


def equipment_availability_for_event(
    reference: str, *, session: Session | None = None
) -> list[EquipmentAvailability]:
    """What is free for an event's own period, against what it asks for (SCRUM-45).

    One row for every equipment type in the catalogue, by name, so an event that asks
    for nothing still sees what is free. The shortfall is how many units the request
    is short of (AC3), 0 when it is met. The period is the event's own start and end,
    not the whole day (AC4).

    Args:
        reference: The event's ``EVR-…`` reference.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such event, or it is still a draft.
        EventPeriodIncompleteError: 409 — the event has no complete date and times.
    """
    sess = resolve_session(session)
    need = events_services.get_event_equipment_need(reference, session=sess)
    rows = []
    for equipment_type in list_equipment_types(session=sess):
        available = available_quantity(
            equipment_type.id, need.starts_at, need.ends_at, session=sess
        )
        requested = need.requested.get(equipment_type.id, 0)
        rows.append(
            EquipmentAvailability(
                equipment_type_id=equipment_type.id,
                equipment_type_name=equipment_type.name,
                available=available,
                requested=requested,
                shortfall=max(requested - available, 0),
            )
        )
    return rows


def list_reservations_for_event(
    reference: str, *, session: Session | None = None
) -> list[ReservationAsShown]:
    """The equipment reserved for an event, oldest first, for its record (SCRUM-46 AC4).

    Args:
        reference: The event's ``EVR-…`` reference.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such event, or it is still a draft.
    """
    sess = resolve_session(session)
    event_id = events_services.get_event_equipment_need(reference, session=sess).event_id
    statement = (
        select(EquipmentReservation)
        .where(EquipmentReservation.event_id == event_id)
        .options(joinedload(EquipmentReservation.equipment_type))
        .order_by(EquipmentReservation.created_at, EquipmentReservation.id)
    )
    return _as_shown(list(sess.scalars(statement)), sess)


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


def reserve_equipment(
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    reserved_by: int | str,
    session: Session | None = None,
) -> ReservationAsShown:
    """Reserve units of an equipment type for an event's own period (SCRUM-46).

    Up to what is free for the period may be reserved (AC1); asking for more is
    refused with how many are free (AC3). The reservation holds the event's exact
    start and end, so overlapping events see that many fewer and others none fewer
    (AC2). Each call adds a reservation; several for one event and type add up. The
    reservation and its entry in the event's history are saved in one commit, then the
    event's assigned coordinator is told (AC5).

    Args:
        reference: The event's ``EVR-…`` reference.
        payload: Decoded JSON body: ``equipment_type_id`` and ``quantity``.
        reserved_by: The caller's user id, taken from their token (a string there).
        session: Database session; defaults to ``db.session``.

    Returns:
        The saved reservation, as the event record shows it.

    Raises:
        ValidationError: 400 — invalid fields, an unknown equipment type, or more
            units than are free, with how many are free.
        NotFoundError: 404 — no such event, or it is still a draft.
        EventPeriodIncompleteError: 409 — the event has no complete date and times.
        EquipmentNotReservableError: 409 — the event is completed, cancelled or
            rejected.
    """
    data = load_or_raise(EquipmentUnitsSchema(), payload)
    reserver_id = int(reserved_by)
    sess = resolve_session(session)
    need = events_services.get_event_equipment_need(reference, session=sess)
    if not need.accepts_reservations:
        raise EquipmentNotReservableError(events_services.RESERVATIONS_CLOSED_MESSAGE)

    # Lock, then count. Counting first would miss a reservation committed while this
    # one waited for the lock (Review Focus 3).
    equipment_type = _locked_equipment_type(data["equipment_type_id"], sess)
    available = available_quantity(equipment_type.id, need.starts_at, need.ends_at, session=sess)
    if data["quantity"] > available:
        message = f"Only {available} available for this period."
        raise ValidationError(message, details={"quantity": [message]})

    reservation = EquipmentReservation(
        event_id=need.event_id,
        equipment_type_id=equipment_type.id,
        quantity=data["quantity"],
        starts_at=need.starts_at,
        ends_at=need.ends_at,
        reserved_by=reserver_id,
    )
    sess.add(reservation)
    # Gives the reservation the id its history entry names.
    sess.flush()
    history_details = {
        "equipment_type_id": equipment_type.id,
        "equipment_type_name": equipment_type.name,
        "quantity": reservation.quantity,
        "reservation_id": reservation.id,
    }
    events_services.record_equipment_reserved(
        need.event_id, history_details, actor_id=reserver_id, session=sess
    )
    sess.commit()
    # After the commit (ADR-0015): losing the notice must not lose the reservation.
    events_services.notify_coordinator_equipment_reserved(need.event_id, session=sess)
    (shown,) = _as_shown([reservation], sess)
    return shown
