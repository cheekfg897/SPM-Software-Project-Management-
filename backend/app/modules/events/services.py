"""Business logic for the events module.

These functions are the module's public API: routes call them, tests call
them directly, and future modules that need event request data call them
instead of touching :class:`~app.modules.events.models.EventRequest`.

What happens to a request is written to its event history with
:func:`record_event_history`, which only this module calls (ADR-0018).

Every function takes an optional ``session`` so unit tests can pass a mock
instead of a real database session. In production the default
``db.session`` is used.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.common.database import resolve_session
from app.common.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.auth.permissions import Role
from app.modules.auth.services import get_user_by_id, list_user_ids_with_role
from app.modules.equipment.services import get_equipment_type
from app.modules.events.models import (
    REFERENCE_UNIQUE_CONSTRAINT,
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import EditEquipmentLineSchema, SubmitEventRequestSchema
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users

logger = logging.getLogger("connectsphere.events")

# Reference format (ADR-0004): "EVR-" + 8 characters with no look-alikes (0 O 1 I L).
REFERENCE_PREFIX = "EVR-"
REFERENCE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
REFERENCE_LENGTH = 8
MAX_REFERENCE_ATTEMPTS = 3

#: One answer for a reference that doesn't exist and one that isn't the caller's, so a
#: reference can't be probed (ADR-0012).
EVENT_REQUEST_NOT_FOUND_MESSAGE = "Event request not found."

#: Statuses in which an assigned coordinator is still working a request, so they count
#: towards the coordinator's load (ADR-0018).
OPEN_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.SUBMITTED, EventRequestStatus.UNDER_REVIEW}
)


class ReferenceGenerationError(AppError):
    """No unused reference was found after several attempts (500)."""

    status_code = 500
    error_code = "reference_generation_failed"


class OrganiserWithoutOrganisationError(AppError):
    """The organiser's account isn't linked to a client organisation (403, ADR-0013)."""

    status_code = 403
    error_code = "organiser_without_organisation"


@dataclass(frozen=True)
class CoordinatorContact:
    """The assigned coordinator as the organiser sees them (SCRUM-30 AC3).

    Users record no phone number, so the contact details are the email address.
    """

    full_name: str
    email: str


def generate_reference() -> str:
    """Return a random reference such as ``EVR-7K2QX9AB``."""
    return REFERENCE_PREFIX + "".join(
        secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH)
    )


def is_reference_collision(exc: IntegrityError) -> bool:
    """Return ``True`` if ``exc`` was caused by the unique constraint on ``reference``.

    PostgreSQL (psycopg2) reports the violated constraint on ``orig.diag``.
    Drivers without that (e.g. SQLite) only give a message, so fall back to it.
    """
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint is not None:
        return constraint == REFERENCE_UNIQUE_CONSTRAINT
    message = str(exc.orig)
    return REFERENCE_UNIQUE_CONSTRAINT in message or "event_requests.reference" in message


def record_event_history(
    event_request: EventRequest,
    kind: EventHistoryKind,
    *,
    actor_id: int | None,
    details: dict[str, Any] | None = None,
    session: Session | None = None,
    now: datetime | None = None,
) -> EventHistoryEntry:
    """Add a history entry for ``event_request`` without committing (ADR-0018).

    The entry rides in the caller's transaction, so it is saved with the change it
    records or not at all. ``event_request`` need not be flushed yet.

    Args:
        event_request: The request the entry is about.
        kind: What happened.
        actor_id: The user who did it, or ``None`` when the system did.
        details: Anything the kind needs to say, e.g. ``{"coordinator_id": 3}``.
        session: Database session; defaults to ``db.session``.
        now: When it happened; defaults to the current instant.

    Returns:
        The new entry, added to the session but not yet committed.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    entry = EventHistoryEntry(
        event_request=event_request,
        kind=kind,
        actor_id=actor_id,
        details=details,
        occurred_at=now,
    )
    resolve_session(session).add(entry)
    return entry


def _organisation_of_organiser(organiser_id: int | str, session: Session) -> int:
    """The client organisation an event request is filed under (SCRUM-66 AC4).

    Raises:
        OrganiserWithoutOrganisationError: 403 — an account from before SCRUM-66 that
            no one has linked to an organisation yet.
    """
    organiser = get_user_by_id(organiser_id, session=session)
    if organiser.organisation_id is None:
        raise OrganiserWithoutOrganisationError(
            "Your account is not linked to a client organisation, "
            "so it cannot submit event requests yet."
        )
    return organiser.organisation_id


def _open_request_counts(coordinator_ids: list[int], session: Session) -> dict[int, int]:
    """How many open requests each coordinator holds; 0 for those holding none."""
    stmt = (
        select(EventRequest.coordinator_id, func.count())
        .where(
            EventRequest.coordinator_id.in_(coordinator_ids),
            EventRequest.status.in_(OPEN_STATUSES),
        )
        .group_by(EventRequest.coordinator_id)
    )
    counts = dict.fromkeys(coordinator_ids, 0)
    for coordinator_id, count in session.execute(stmt):
        counts[coordinator_id] = count
    return counts


def _least_loaded_coordinator(coordinator_ids: list[int], session: Session) -> int | None:
    """The Event Coordinator with the fewest open requests (SCRUM-30 AC1, ADR-0018).

    The lowest user id wins a tie. ``None`` when there is no Event Coordinator at all.
    """
    if not coordinator_ids:
        return None
    counts = _open_request_counts(coordinator_ids, session)

    def load_then_id(coordinator_id: int) -> tuple[int, int]:
        return counts[coordinator_id], coordinator_id

    return min(coordinator_ids, key=load_then_id)


def _raise_notifications(
    recipient_ids: list[int], event_request: EventRequest, kind: NotificationKind, session: Session
) -> None:
    """Notify ``recipient_ids`` that ``kind`` happened to ``event_request``.

    Runs after the change's own commit, so the notifications refer to a saved row
    (ADR-0015). If they can't be saved, only they are lost and a warning is logged:
    what they announce is already saved, and failing the reply would invite the
    caller to do it again.
    """
    event = EventSummary(
        id=event_request.id, reference=event_request.reference, name=event_request.name
    )
    try:
        notify_users(recipient_ids, event, kind, session=session)
    except SQLAlchemyError:
        session.rollback()
        logger.warning(
            "event_request_notification_failed reference=%s kind=%s", event.reference, kind.value
        )


def _notify_about_submission(event_request: EventRequest, session: Session) -> None:
    """Tell the assigned coordinator the new request is theirs (SCRUM-30 AC4).

    SCRUM-28 AC3 raises a new request to the coordinators; only the assigned one is
    told (ADR-0018, replacing ADR-0015's notice to every coordinator). With no
    coordinator to assign the request stays unassigned and nobody is told; that is
    logged so someone can pick it up.
    """
    if event_request.coordinator_id is None:
        logger.warning("event_request_unassigned reference=%s", event_request.reference)
        return
    _raise_notifications(
        [event_request.coordinator_id],
        event_request,
        NotificationKind.COORDINATOR_ASSIGNED,
        session,
    )


def submit_event_request(
    organiser_id: int | str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    today: date | None = None,
    reference_factory: Callable[[], str] = generate_reference,
) -> EventRequest:
    """Submit a new event request on behalf of an organiser (SCRUM-19).

    Validates the payload (AC1-AC4), then saves it with status ``submitted``
    and a fresh reference (AC5), filed under the organiser's client
    organisation (SCRUM-66 AC4). It is assigned to the Event Coordinator with
    the fewest open requests, and the assignment is written to its event history
    (:data:`EventHistoryKind.COORDINATOR_ASSIGNED`) in the same commit (SCRUM-30
    AC1, AC2, ADR-0018); with no Event Coordinator it is saved unassigned. If the
    reference is already taken, the save is rolled back and retried with a new
    one, up to :data:`MAX_REFERENCE_ATTEMPTS` times. Once saved, the assigned
    coordinator is told it is theirs (SCRUM-28 AC3, SCRUM-30 AC4).

    Args:
        organiser_id: The caller's user id, taken from their token.
        payload: Decoded JSON body.
        session: Database session; defaults to ``db.session``.
        today: Reference date for the "not in the past" rule; defaults to
            today in the business timezone.
        reference_factory: Makes references; tests swap it out.

    Returns:
        The saved :class:`EventRequest`.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
        OrganiserWithoutOrganisationError: 403 — the organiser has no client
            organisation (ADR-0013).
        NotFoundError: 404 — the token names a user that no longer exists.
        ReferenceGenerationError: 500 — every attempt hit a used reference.
        IntegrityError: any other constraint failure; not retried.
    """
    data = load_or_raise(SubmitEventRequestSchema(today=today), payload)
    sess = resolve_session(session)
    organisation_id = _organisation_of_organiser(organiser_id, sess)
    # Chosen before the retry loop: a retry changes nobody's load.
    coordinator_ids = list_user_ids_with_role(Role.EVENT_COORDINATOR, session=sess)
    coordinator_id = _least_loaded_coordinator(coordinator_ids, sess)

    for attempt in range(1, MAX_REFERENCE_ATTEMPTS + 1):
        event_request = EventRequest(
            organiser_id=int(organiser_id),
            organisation_id=organisation_id,
            coordinator_id=coordinator_id,
            reference=reference_factory(),
            status=EventRequestStatus.SUBMITTED,
            **data,
        )
        sess.add(event_request)
        if coordinator_id is not None:
            # Same commit as the request: a rolled-back attempt leaves no entry (AC2).
            record_event_history(
                event_request,
                EventHistoryKind.COORDINATOR_ASSIGNED,
                actor_id=None,
                details={"coordinator_id": coordinator_id},
                session=sess,
            )
        try:
            sess.commit()
        except IntegrityError as exc:
            sess.rollback()
            if not is_reference_collision(exc):
                raise
            logger.warning(
                "event_request_reference_collision reference=%s attempt=%d",
                event_request.reference,
                attempt,
            )
            continue
        # Outside the try: a failed notification commit is not a reference collision.
        _notify_about_submission(event_request, sess)
        return event_request

    raise ReferenceGenerationError("Could not create the event request. Please try again.")


def _list_event_requests_newest_first(
    belongs_to: ColumnElement[bool], session: Session
) -> list[EventRequest]:
    """Event requests matching ``belongs_to``, newest first, later id first on a tie."""
    stmt = (
        select(EventRequest)
        .where(belongs_to)
        .order_by(EventRequest.created_at.desc(), EventRequest.id.desc())
    )
    return list(session.scalars(stmt))


def _visible_to_organiser(organiser_id: int | str) -> ColumnElement[bool]:
    """The event requests an organiser may see: the ones they submitted (ADR-0012).

    The one place an organiser's scope is decided, so their list and the detail of
    one request can't disagree about what is theirs.
    """
    return EventRequest.organiser_id == int(organiser_id)


def list_event_requests_for_organiser(
    organiser_id: int | str, *, session: Session | None = None
) -> list[EventRequest]:
    """Return the organiser's own event requests, newest first (SCRUM-19 AC5)."""
    return _list_event_requests_newest_first(
        _visible_to_organiser(organiser_id), resolve_session(session)
    )


def list_event_requests_for_coordinator(
    coordinator_id: int | str, *, session: Session | None = None
) -> list[EventRequest]:
    """Return the requests assigned to the coordinator, newest first (SCRUM-30 AC5)."""
    return _list_event_requests_newest_first(
        EventRequest.coordinator_id == int(coordinator_id), resolve_session(session)
    )


def _normalise_reference(reference: str) -> str:
    """A reference as typed by a user, trimmed and upper-cased (ADR-0004)."""
    return reference.strip().upper()


def _event_request_by_reference(
    reference: str, session: Session, *, belongs_to: ColumnElement[bool] | None = None
) -> EventRequest:
    """An event request by its reference, among those matching ``belongs_to`` if given.

    Case and surrounding spaces are ignored (ADR-0004). A request outside
    ``belongs_to`` is not found, the same 404 as a reference that doesn't exist, so
    "not yours" can't be told apart from "no such request" (ADR-0012). Callers that
    check ownership afterwards answer "not yours" with that same 404 too.

    Raises:
        NotFoundError: 404 — no such request, or none matching ``belongs_to``.
    """
    stmt = select(EventRequest).where(EventRequest.reference == _normalise_reference(reference))
    if belongs_to is not None:
        stmt = stmt.where(belongs_to)
    event_request = session.scalar(stmt)
    if event_request is None:
        raise NotFoundError(EVENT_REQUEST_NOT_FOUND_MESSAGE)
    return event_request


def get_event_request_for_organiser(
    organiser_id: int | str, reference: str, *, session: Session | None = None
) -> EventRequest:
    """Fetch one of the organiser's own event requests by reference (SCRUM-22 AC2).

    A reference that belongs to another organiser gets the same 404 as one that
    doesn't exist (ADR-0012).

    Args:
        organiser_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such request among the caller's own.
    """
    return _event_request_by_reference(
        reference, resolve_session(session), belongs_to=_visible_to_organiser(organiser_id)
    )


def _coordinator_contact(
    event_request: EventRequest, session: Session
) -> CoordinatorContact | None:
    """The request's assigned coordinator, or ``None`` while it has none (ADR-0018)."""
    if event_request.coordinator_id is None:
        return None
    coordinator = get_user_by_id(event_request.coordinator_id, session=session)
    return CoordinatorContact(full_name=coordinator.full_name, email=coordinator.email)


def get_event_record_for_organiser(
    organiser_id: int | str, reference: str, *, session: Session | None = None
) -> tuple[EventRequest, CoordinatorContact | None]:
    """One of the organiser's own requests and its assigned coordinator (SCRUM-30 AC3).

    Same lookup and scope as :func:`get_event_request_for_organiser`; the coordinator
    is ``None`` until one is assigned (ADR-0018).

    Args:
        organiser_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, and its coordinator's name and email or ``None``.

    Raises:
        NotFoundError: 404 — no such request among the caller's own.
    """
    sess = resolve_session(session)
    event_request = get_event_request_for_organiser(organiser_id, reference, session=sess)
    return event_request, _coordinator_contact(event_request, sess)


# --------------------------------------------------------------------------
# SCRUM-37 — record what equipment an event needs
# --------------------------------------------------------------------------

#: Statuses in which a request is still awaiting review, so its equipment may change
#: (SCRUM-37 AC2, ADR-0019).
AWAITING_REVIEW_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.SUBMITTED, EventRequestStatus.UNDER_REVIEW}
)
NOT_AWAITING_REVIEW_MESSAGE = "Equipment can only be changed while the request is awaiting review."
DUPLICATE_LINE_MESSAGE = (
    "This event already has a line for that equipment type. Edit that line instead."
)


class RequestNotAwaitingReviewError(AppError):
    """The request is no longer awaiting review, so its equipment can't change (409)."""

    status_code = 409
    error_code = "request_not_awaiting_review"


def _event_request_assigned_to(
    coordinator_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The request, if ``coordinator_id`` is its assigned coordinator (ADR-0019).

    Another coordinator's request, or an unassigned one, gets the same 404 as a
    reference that doesn't exist, as an organiser's "not yours" does (ADR-0012).

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own.
    """
    event_request = _event_request_by_reference(reference, session)
    if event_request.coordinator_id != int(coordinator_id):
        raise NotFoundError(EVENT_REQUEST_NOT_FOUND_MESSAGE)
    return event_request


def _event_request_awaiting_review(
    coordinator_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The coordinator's request, if its equipment may still change (SCRUM-37 AC2).

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own.
        RequestNotAwaitingReviewError: 409 — the request is no longer awaiting review.
    """
    event_request = _event_request_assigned_to(coordinator_id, reference, session)
    if event_request.status not in AWAITING_REVIEW_STATUSES:
        raise RequestNotAwaitingReviewError(NOT_AWAITING_REVIEW_MESSAGE)
    return event_request


def _check_equipment_type(equipment_type_id: int, session: Session) -> None:
    """Reject an equipment type that isn't in the catalogue, as a 400 on its field."""
    try:
        get_equipment_type(equipment_type_id, session=session)
    except NotFoundError as exc:
        raise ValidationError(
            "Invalid request.", details={"equipment_type_id": [exc.message]}
        ) from exc


def _commit_line_or_conflict(session: Session) -> None:
    """Commit; a second line for an equipment type on one event is a 409 (ADR-0019)."""
    # The schema has enforced every other rule and the type has been checked, so the
    # only integrity error left here is the unique (event, equipment type) pair.
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(DUPLICATE_LINE_MESSAGE) from exc


def _line_of_event(
    event_request: EventRequest, line_id: int, session: Session
) -> EventEquipmentLine:
    """One of the event's own equipment lines, by id (SCRUM-37 AC2).

    Raises:
        NotFoundError: 404 — the event has no line with that id.
    """
    stmt = select(EventEquipmentLine).where(
        EventEquipmentLine.id == line_id,
        EventEquipmentLine.event_request_id == event_request.id,
    )
    line = session.scalar(stmt)
    if line is None:
        raise NotFoundError("Equipment line not found.")
    return line


def add_equipment_line(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventEquipmentLine:
    """Record one kind of equipment an event needs (SCRUM-37 AC1, AC3).

    Only the event's assigned coordinator may (ADR-0019). The line is saved with
    status ``requested``; once it is saved, every Technical Support Staff member is
    notified (AC5).

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The event request's ``EVR-…`` reference; case and surrounding
            spaces are ignored.
        payload: Decoded JSON body: ``equipment_type_id``, ``quantity`` and optional
            ``notes``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The saved :class:`EventEquipmentLine`.

    Raises:
        ValidationError: 400 — payload invalid, or no such equipment type.
        NotFoundError: 404 — no such event request among the coordinator's own.
        RequestNotAwaitingReviewError: 409 — the request is no longer awaiting review.
        ConflictError: 409 — the event already has a line for that equipment type.
    """
    data = load_or_raise(EditEquipmentLineSchema(), payload)
    sess = resolve_session(session)
    event_request = _event_request_awaiting_review(coordinator_id, reference, sess)
    _check_equipment_type(data["equipment_type_id"], sess)

    line = EventEquipmentLine(
        event_request_id=event_request.id, status=EquipmentLineStatus.REQUESTED, **data
    )
    sess.add(line)
    _commit_line_or_conflict(sess)
    technical_support_ids = list_user_ids_with_role(Role.TECHNICAL_SUPPORT_STAFF, session=sess)
    _raise_notifications(
        technical_support_ids, event_request, NotificationKind.EQUIPMENT_REQUESTED, sess
    )
    return line


def list_equipment_lines(
    viewer_id: int | str, reference: str, *, viewer_role: Role, session: Session | None = None
) -> tuple[EventRequest, list[EventEquipmentLine]]:
    """An event and its equipment lines with their state, in the order added (AC4).

    The event comes too: its date and times tell Technical Support by when the
    equipment is needed. Technical Support Staff may list any event's lines; a
    coordinator only those of an event assigned to them (ADR-0019).

    Args:
        viewer_id: The caller's user id, taken from their token.
        reference: The event request's ``EVR-…`` reference; case and surrounding
            spaces are ignored.
        viewer_role: The caller's role.
        session: Database session; defaults to ``db.session``.

    Returns:
        The event request, and its lines.

    Raises:
        NotFoundError: 404 — no such event request, or for a coordinator, none among
            their own.
    """
    sess = resolve_session(session)
    if viewer_role is Role.TECHNICAL_SUPPORT_STAFF:
        event_request = _event_request_by_reference(reference, sess)
    else:
        event_request = _event_request_assigned_to(viewer_id, reference, sess)
    return event_request, list(event_request.equipment_lines)


def update_equipment_line(
    coordinator_id: int | str,
    reference: str,
    line_id: int,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventEquipmentLine:
    """Change a line's equipment type, quantity or notes (SCRUM-37 AC2, AC3).

    Only the fields in ``payload`` change; ``notes`` is cleared only when sent as
    ``null``. Only the event's assigned coordinator may, while the request is awaiting
    review (ADR-0019).

    Returns:
        The updated :class:`EventEquipmentLine`.

    Raises:
        ValidationError: 400 — invalid values for the fields sent, or no such
            equipment type.
        NotFoundError: 404 — no such event request among the coordinator's own, or no
            such line on it.
        RequestNotAwaitingReviewError: 409 — the request is no longer awaiting review.
        ConflictError: 409 — another line on the event already has that equipment type.
    """
    schema = EditEquipmentLineSchema()
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    event_request = _event_request_awaiting_review(coordinator_id, reference, sess)
    line = _line_of_event(event_request, line_id, sess)
    if "equipment_type_id" in data:
        _check_equipment_type(data["equipment_type_id"], sess)

    for key, value in data.items():
        setattr(line, key, value)
    _commit_line_or_conflict(sess)
    return line


def remove_equipment_line(
    coordinator_id: int | str, reference: str, line_id: int, *, session: Session | None = None
) -> None:
    """Delete one of an event's equipment lines (SCRUM-37 AC2).

    Only the event's assigned coordinator may, while the request is awaiting review.
    Nobody is notified (ADR-0019).

    Raises:
        NotFoundError: 404 — no such event request among the coordinator's own, or no
            such line on it.
        RequestNotAwaitingReviewError: 409 — the request is no longer awaiting review.
    """
    sess = resolve_session(session)
    event_request = _event_request_awaiting_review(coordinator_id, reference, sess)
    line = _line_of_event(event_request, line_id, sess)
    sess.delete(line)
    sess.commit()
