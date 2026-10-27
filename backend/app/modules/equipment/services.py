"""Business logic for the equipment module.

Same shape as the other modules: routes call these functions, tests call them
directly, and other modules call them instead of touching the models. Every
function takes an optional ``session``, defaulting to ``db.session``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import ColumnElement, Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.common.database import resolve_session
from app.common.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.common.preparation import PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE
from app.common.validation import load_or_raise
from app.modules.auth.permissions import Role
from app.modules.auth.services import get_user_full_names
from app.modules.equipment.models import (
    EquipmentOutOfService,
    EquipmentReservation,
    EquipmentType,
    OutOfServiceReason,
    PreparationStatus,
)
from app.modules.equipment.schemas import (
    EditEquipmentTypeSchema,
    EquipmentUnitsSchema,
    MarkOutOfServiceSchema,
    UpdatePreparationSchema,
)

# The module, not its names: events.services imports this module too (to check a
# catalogue entry), and module-attribute access is what lets the two import each other.
from app.modules.events import services as events_services
from app.modules.venue.services import get_venue

EQUIPMENT_TYPE_NOT_FOUND_MESSAGE = "Equipment type not found."
RESERVATION_NOT_FOUND_MESSAGE = "Equipment reservation not found."


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
    #: Units out of service have left the type short of what is reserved (SCRUM-47 AC3).
    needs_attention: bool
    #: Technical Support's progress and notes on the units (SCRUM-85).
    preparation_status: PreparationStatus
    preparation_notes: str | None


@dataclass(frozen=True)
class OutOfServiceAsShown:
    """Units of an equipment type out of service, as the API shows them (SCRUM-47).

    People are shown by name, as reservations are; ``None`` once their account is gone
    or, for the resolver, while the units are still out.
    """

    id: int
    equipment_type_id: int
    quantity: int
    reason: OutOfServiceReason
    recorded_by: str | None
    recorded_at: datetime
    resolved_by: str | None
    resolved_at: datetime | None


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
                needs_attention=reservation.needs_attention,
                preparation_status=reservation.preparation_status,
                preparation_notes=reservation.preparation_notes,
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


def _units_in_service(equipment_type: EquipmentType, session: Session) -> int:
    """Units of the type held and not recorded as out of service."""
    return equipment_type.total_quantity - _out_of_service_quantity(equipment_type.id, session)


def _out_of_service_as_shown(
    entries: list[EquipmentOutOfService], session: Session
) -> list[OutOfServiceAsShown]:
    """The entries with the names of who recorded and resolved them, in one query."""
    user_ids = set()
    for entry in entries:
        user_ids.add(entry.recorded_by)
        if entry.resolved_by is not None:
            user_ids.add(entry.resolved_by)
    names = get_user_full_names(user_ids, session=session)
    shown = []
    for entry in entries:
        shown.append(
            OutOfServiceAsShown(
                id=entry.id,
                equipment_type_id=entry.equipment_type_id,
                quantity=entry.quantity,
                reason=entry.reason,
                recorded_by=names.get(entry.recorded_by),
                recorded_at=entry.recorded_at,
                resolved_by=names.get(entry.resolved_by),
                resolved_at=entry.resolved_at,
            )
        )
    return shown


def _reflag_short_reservations(
    equipment_type: EquipmentType, now: datetime, session: Session
) -> list[int]:
    """Flag the type's coming reservations that are short, and clear the rest (AC3).

    A reservation is short when the units reserved for any event overlapping its
    period, as availability counts them, are more than the units in service. Units out
    of service belong to no period (ADR-0037), so which reservation "depends on" a
    broken unit can't be told: every reservation in an over-committed period is
    flagged. A reservation that has ended is left as it was. Nothing is deleted or
    released (ADR-0046).

    Returns:
        The ids of the events with a reservation flagged by this call, each once, so
        a coordinator is not told again about a reservation already flagged.
    """
    in_service = _units_in_service(equipment_type, session)
    statement = select(EquipmentReservation).where(
        EquipmentReservation.equipment_type_id == equipment_type.id,
        EquipmentReservation.ends_at > now,
    )
    newly_flagged_event_ids = []
    for reservation in list(session.scalars(statement)):
        reserved = _reserved_quantity(
            equipment_type.id, reservation.starts_at, reservation.ends_at, session
        )
        is_short = reserved > in_service
        newly_flagged = is_short and not reservation.needs_attention
        if newly_flagged and reservation.event_id not in newly_flagged_event_ids:
            newly_flagged_event_ids.append(reservation.event_id)
        reservation.needs_attention = is_short
    return newly_flagged_event_ids


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
    viewer_id: int | str, reference: str, *, viewer_role: Role, session: Session | None = None
) -> list[EquipmentAvailability]:
    """What is free for an event's own period, against what it asks for (SCRUM-45).

    One row for every equipment type in the catalogue, by name, so an event that asks
    for nothing still sees what is free. The shortfall is how many units the request
    is short of (AC3), 0 when it is met. The period is the event's own start and end,
    not the whole day (AC4). Technical Support Staff may read any event's; a
    coordinator only an event assigned to them (ADR-0019, ADR-0037).

    Args:
        viewer_id: The caller's user id, taken from their token.
        reference: The event's ``EVR-…`` reference.
        viewer_role: The caller's role.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such event, a draft, or for a coordinator, not one of
            their own.
        EventPeriodIncompleteError: 409 — the event has no complete date and times.
    """
    sess = resolve_session(session)
    need = events_services.get_event_equipment_need_for_viewer(
        viewer_id, reference, viewer_role=viewer_role, session=sess
    )
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


def list_reservations_of_event(
    event_id: int, *, session: Session | None = None
) -> list[ReservationAsShown]:
    """The equipment reserved for the event with this id, oldest first (ADR-0095).

    For the read-only record other internal users open (SCRUM-24 AC9, SCRUM-85 AC2):
    the caller has already decided who may read it.
    """
    sess = resolve_session(session)
    statement = (
        select(EquipmentReservation)
        .where(EquipmentReservation.event_id == event_id)
        .options(joinedload(EquipmentReservation.equipment_type))
        .order_by(EquipmentReservation.created_at, EquipmentReservation.id)
    )
    return _as_shown(list(sess.scalars(statement)), sess)


def list_reservations_for_event(
    viewer_id: int | str, reference: str, *, viewer_role: Role, session: Session | None = None
) -> list[ReservationAsShown]:
    """The equipment reserved for an event, oldest first, for its record (SCRUM-46 AC4).

    Technical Support Staff may read any event's; a coordinator only an event assigned
    to them (ADR-0019, ADR-0037).

    Args:
        viewer_id: The caller's user id, taken from their token.
        reference: The event's ``EVR-…`` reference.
        viewer_role: The caller's role.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such event, a draft, or for a coordinator, not one of
            their own.
    """
    sess = resolve_session(session)
    need = events_services.get_event_equipment_need_for_viewer(
        viewer_id, reference, viewer_role=viewer_role, session=sess
    )
    return list_reservations_of_event(need.event_id, session=sess)


def release_reservations(
    event_id: int, equipment_type_id: int, *, session: Session | None = None
) -> None:
    """Release every reservation of an equipment type for an event, without committing.

    For an equipment line the event no longer asks for: removed, or moved to another
    type (SCRUM-37 AC4, ADR-0092). The units are free for the period again as soon as
    the caller commits, in the same commit as the line change, or not at all.

    Args:
        event_id: The event request's id.
        equipment_type_id: The equipment type to release.
        session: Database session; defaults to ``db.session``.
    """
    statement = delete(EquipmentReservation).where(
        EquipmentReservation.event_id == event_id,
        EquipmentReservation.equipment_type_id == equipment_type_id,
    )
    resolve_session(session).execute(statement)


# --------------------------------------------------------------------------
# SCRUM-60 — mark reservations for reassessment after a change
# --------------------------------------------------------------------------


def _mark_for_reassessment(statement: Select[tuple[EquipmentReservation]], session: Session) -> int:
    """Mark the reservations ``statement`` selects for reassessment; how many it marked.

    Nothing else changes: each stays held for its own period until Technical Support
    act (SCRUM-60 AC6, ADR-0114).
    """
    marked = 0
    for reservation in session.scalars(statement):
        reservation.needs_reassessment = True
        marked += 1
    return marked


def mark_event_reservations_for_reassessment(
    event_id: int, *, session: Session | None = None
) -> int:
    """Mark every reservation for the event for reassessment, without committing.

    For a change to the event's date or time (SCRUM-60 AC1): the units stay held for
    each reservation's own period, so nothing is released before Technical Support
    act (AC6). The caller commits, with the change that marks them.

    Args:
        event_id: The event request's id.
        session: Database session; defaults to ``db.session``.

    Returns:
        How many reservations it marked; 0 when the event has none.
    """
    statement = select(EquipmentReservation).where(EquipmentReservation.event_id == event_id)
    return _mark_for_reassessment(statement, resolve_session(session))


def mark_type_reservations_for_reassessment(
    event_id: int, equipment_type_id: int, *, session: Session | None = None
) -> None:
    """Mark the event's reservations of one equipment type, without committing.

    For a new quantity on that type's line (SCRUM-60 AC8): reservations hold no line
    id, and an event has one line per type (ADR-0019, ADR-0092), so the line's
    reservations are the event's reservations of its type.

    Args:
        event_id: The event request's id.
        equipment_type_id: The line's equipment type.
        session: Database session; defaults to ``db.session``.
    """
    statement = select(EquipmentReservation).where(
        EquipmentReservation.event_id == event_id,
        EquipmentReservation.equipment_type_id == equipment_type_id,
    )
    _mark_for_reassessment(statement, resolve_session(session))


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
    reservation and its entry in the event's history are saved in one commit. Nobody is
    notified: the coordinator hears once, when the outcome is recorded (AC5, SCRUM-48,
    ADR-0102).

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
    (shown,) = _as_shown([reservation], sess)
    return shown


def mark_out_of_service(
    equipment_type_id: int,
    payload: Mapping[str, Any] | None,
    *,
    recorded_by: int | str,
    now: datetime | None = None,
    session: Session | None = None,
) -> OutOfServiceAsShown:
    """Take units of an equipment type out of service (SCRUM-47 AC1, AC4).

    The units stop counting as free (AC2). Reservations they leave short are flagged
    and, after the commit, each affected event's coordinator is told once (AC3). An
    event with a newly flagged reservation loses its safety approval, if it has one,
    in the same commit, so it must pass a new check (AC5, ADR-0087). The type is
    locked first, so a reservation made at the same moment is either counted before
    the change or flagged by it (ADR-0037 section 3).

    Args:
        equipment_type_id: The equipment type, from the URL.
        payload: Decoded JSON body: ``quantity`` and ``reason``.
        recorded_by: The caller's user id, taken from their token (a string there).
        now: When the change is made; defaults to the current time.
        session: Database session; defaults to ``db.session``.

    Returns:
        The saved entry, as the API shows it.

    Raises:
        ValidationError: 400 — invalid fields, or more units than are in service.
        NotFoundError: 404 — no such equipment type.
    """
    data = load_or_raise(MarkOutOfServiceSchema(), payload)
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)
    # A 404 for an unknown type; the locking read would call it a 400 on a body field.
    get_equipment_type(equipment_type_id, session=sess)
    equipment_type = _locked_equipment_type(equipment_type_id, sess)

    in_service = _units_in_service(equipment_type, sess)
    if data["quantity"] > in_service:
        message = f"Only {in_service} units are in service."
        raise ValidationError(message, details={"quantity": [message]})

    entry = EquipmentOutOfService(
        equipment_type_id=equipment_type.id,
        quantity=data["quantity"],
        reason=data["reason"],
        recorded_by=int(recorded_by),
        recorded_at=now,
    )
    sess.add(entry)
    flagged_event_ids = _reflag_short_reservations(equipment_type, now, sess)
    for event_id in flagged_event_ids:
        events_services.withdraw_safety_approval(
            event_id,
            actor_id=int(recorded_by),
            details={
                "equipment_type_id": equipment_type.id,
                "equipment_type_name": equipment_type.name,
                "units_out_of_service": entry.quantity,
            },
            session=sess,
        )
    sess.commit()
    # After the commit (ADR-0015): losing a notice must not lose the change.
    events_services.notify_coordinators_equipment_short(flagged_event_ids, session=sess)
    (shown,) = _out_of_service_as_shown([entry], sess)
    return shown


def return_to_service(
    entry_id: int,
    *,
    resolved_by: int | str,
    now: datetime | None = None,
    session: Session | None = None,
) -> OutOfServiceAsShown:
    """Put the units of an out-of-service entry back, so they count as free (SCRUM-47).

    Reservations that are no longer short lose their flag. Nobody is told: a flag
    going away is not news the coordinator has to act on.

    Args:
        entry_id: The out-of-service entry, from the URL.
        resolved_by: The caller's user id, taken from their token (a string there).
        now: When the units are back; defaults to the current time.
        session: Database session; defaults to ``db.session``.

    Returns:
        The updated entry, as the API shows it.

    Raises:
        NotFoundError: 404 — no such entry.
        ConflictError: 409 — the units are already back in service.
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)
    entry = sess.get(EquipmentOutOfService, entry_id)
    if entry is None:
        raise NotFoundError("Out-of-service entry not found.")
    equipment_type = _locked_equipment_type(entry.equipment_type_id, sess)
    # Another request may have returned the units while this one waited for the lock.
    sess.refresh(entry)
    if entry.resolved_at is not None:
        raise ConflictError("These units are already back in service.")

    entry.resolved_by = int(resolved_by)
    entry.resolved_at = now
    _reflag_short_reservations(equipment_type, now, sess)
    sess.commit()
    (shown,) = _out_of_service_as_shown([entry], sess)
    return shown


def list_out_of_service(
    equipment_type_id: int, *, session: Session | None = None
) -> list[OutOfServiceAsShown]:
    """The units of the type still out of service, oldest first (SCRUM-47 AC1).

    Raises:
        NotFoundError: 404 — no such equipment type.
    """
    sess = resolve_session(session)
    get_equipment_type(equipment_type_id, session=sess)
    statement = (
        select(EquipmentOutOfService)
        .where(
            EquipmentOutOfService.equipment_type_id == equipment_type_id,
            EquipmentOutOfService.resolved_at.is_(None),
        )
        .order_by(EquipmentOutOfService.recorded_at, EquipmentOutOfService.id)
    )
    return _out_of_service_as_shown(list(sess.scalars(statement)), sess)


def update_preparation_details(
    reservation_id: int,
    payload: Mapping[str, Any] | None,
    *,
    updated_by: int,
    session: Session | None = None,
) -> ReservationAsShown:
    """Record the preparation status and notes of an equipment reservation (SCRUM-85).

    AC1-AC5. Any Technical Support member may record them for any reservation: units
    are not assigned to particular staff (ADR-0050). Each update replaces the status
    and notes, and the event's history gets an entry naming the user and the time in
    the same commit (AC4). Nothing else of the reservation changes (AC3). The Safety
    Officer must have approved the event first (AC5, ADR-0047).

    Args:
        reservation_id: The reservation's id.
        payload: Decoded JSON body: ``status`` and optional ``notes``.
        updated_by: The Technical Support user's id, taken from their token.
        session: Database session; defaults to ``db.session``.

    Returns:
        The reservation, as the event record shows it.

    Raises:
        ValidationError: 400 - payload invalid, or it names a field other than these.
        NotFoundError: 404 - no such reservation.
        ConflictError: 409 - the Safety Officer hasn't approved the event.
    """
    data = load_or_raise(UpdatePreparationSchema(), payload)
    sess = resolve_session(session)
    reservation = sess.get(EquipmentReservation, reservation_id)
    if reservation is None:
        raise NotFoundError(RESERVATION_NOT_FOUND_MESSAGE)
    if not events_services.has_safety_approval(reservation.event_id, session=sess):
        raise ConflictError(PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE)

    reservation.preparation_status = data["status"]
    reservation.preparation_notes = data["notes"]
    events_services.record_equipment_preparation_updated(
        reservation.event_id,
        {
            "reservation_id": reservation.id,
            "equipment_type_id": reservation.equipment_type_id,
            "equipment_type_name": reservation.equipment_type.name,
            "status": data["status"].value,
            "notes": data["notes"],
        },
        actor_id=updated_by,
        session=sess,
    )
    sess.commit()
    (shown,) = _as_shown([reservation], sess)
    return shown


# --------------------------------------------------------------------------
# SCRUM-49 AC10 — return a rejected event's equipment
# --------------------------------------------------------------------------


def release_event_reservations(event_id: int, *, session: Session | None = None) -> None:
    """Return every unit reserved for the event to stock, without committing.

    SCRUM-49 AC10: an event rejected during planning gives its equipment back, as a
    cancelled event does (SCRUM-61 AC3, ADR-0093). Availability counts every
    reservation row (SCRUM-45), so the event's rows are deleted and their units are
    free for the period at once. Each reservation's ``equipment_reserved`` history
    entry stays, so the event's record still says what was set aside. The caller
    commits, with the rejection this is part of.

    Args:
        event_id: The event request's id.
        session: Database session; defaults to ``db.session``.
    """
    statement = delete(EquipmentReservation).where(EquipmentReservation.event_id == event_id)
    resolve_session(session).execute(statement)
