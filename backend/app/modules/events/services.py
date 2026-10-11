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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timezone
from typing import Any

from marshmallow import Schema
from sqlalchemy import Row, and_, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.common.clock import as_utc, local_today
from app.common.database import resolve_session
from app.common.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.auth.services import (
    get_user_by_email,
    get_user_by_id,
    get_user_full_names,
    list_user_ids_with_role,
)
from app.modules.equipment import services as equipment_services
from app.modules.events.models import (
    REFERENCE_UNIQUE_CONSTRAINT,
    DecisionOutcome,
    EquipmentLineStatus,
    EventEquipmentLine,
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import (
    AMENDABLE_FIELDS,
    DecideEventRequestSchema,
    EditEquipmentLineSchema,
    EditEventRequestSchema,
    EventRequestSchema,
    ReassignCoordinatorSchema,
    RequestClarificationSchema,
    ResubmitEventRequestSchema,
    SaveDraftSchema,
    SubmitEventRequestSchema,
)
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users

logger = logging.getLogger("connectsphere.events")

# Reference format (ADR-0004): "EVR-" + 8 characters with no look-alikes (0 O 1 I L).
REFERENCE_PREFIX = "EVR-"
REFERENCE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
REFERENCE_LENGTH = 8
MAX_REFERENCE_ATTEMPTS = 3

#: One answer for a reference that doesn't exist and one the caller may not see, so a
#: reference can't be probed (ADR-0012).
EVENT_REQUEST_NOT_FOUND_MESSAGE = "Event request not found."

#: Statuses in which an assigned coordinator is still working a request, so they count
#: towards the coordinator's load (ADR-0018). An approved request is still being
#: planned until it is confirmed (SCRUM-31, ADR-0028), and one awaiting clarification
#: comes back to its coordinator once the organiser answers (SCRUM-32, ADR-0029).
OPEN_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.AWAITING_CLARIFICATION,
        EventRequestStatus.APPROVED,
    }
)


class ReferenceGenerationError(AppError):
    """No unused reference was found after several attempts (500)."""

    status_code = 500
    error_code = "reference_generation_failed"


class OrganiserWithoutOrganisationError(AppError):
    """The organiser's account isn't linked to a client organisation (403).

    Refused on submit (ADR-0013) and on reading event requests (ADR-0020).
    """

    status_code = 403
    error_code = "organiser_without_organisation"


@dataclass(frozen=True)
class CoordinatorContact:
    """The assigned coordinator as the organiser sees them (SCRUM-30 AC3).

    Users record no phone number, so the contact details are the email address.
    """

    full_name: str
    email: str


@dataclass(frozen=True)
class DecisionAsShown:
    """The request's current decision as its record shows it (SCRUM-31 AC9, ADR-0028).

    No user ids: the coordinator who made it is shown by name.
    """

    #: ``approved`` or ``rejected``.
    outcome: str | None
    reason: str | None
    #: The deciding coordinator's full name, or ``None`` if they no longer exist.
    decided_by: str | None
    decided_at: datetime


@dataclass(frozen=True)
class ClarificationAsShown:
    """One clarification question and its answer as the record shows them (SCRUM-32).

    No user ids: the coordinator who asked and the organiser who answered are shown by
    name. The answer's fields stay ``None`` while the question is outstanding.
    """

    message: str | None
    #: The asking coordinator's full name, or ``None`` if they no longer exist.
    requested_by: str | None
    requested_at: datetime
    response: str | None = None
    #: The answering organiser's full name, or ``None`` if they no longer exist.
    answered_by: str | None = None
    answered_at: datetime | None = None


@dataclass(frozen=True)
class EventRecord:
    """A request with what its record shows beside it (SCRUM-30 AC3, ADR-0026)."""

    event_request: EventRequest
    #: The assigned coordinator's contact, or ``None`` while it has none (ADR-0018).
    coordinator: CoordinatorContact | None
    #: The current decision, or ``None`` until one is recorded (SCRUM-31 AC9).
    decision: DecisionAsShown | None = None
    #: Every clarification question in the order asked, each with its answer (SCRUM-32).
    clarifications: tuple[ClarificationAsShown, ...] = ()


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


def _user_ids_named_in(entries: list[EventHistoryEntry]) -> set[int]:
    """Every user id showing ``entries`` needs a name for (ADR-0025, ADR-0028).

    The actors, and the coordinator a ``coordinator_assigned`` entry names.
    """
    user_ids: set[int] = set()
    for entry in entries:
        if entry.actor_id is not None:
            user_ids.add(entry.actor_id)
        if entry.kind is EventHistoryKind.COORDINATOR_ASSIGNED:
            coordinator_id = (entry.details or {}).get("coordinator_id")
            if coordinator_id is not None:
                user_ids.add(coordinator_id)
    return user_ids


def _actor_name(entry: EventHistoryEntry, names: Mapping[int, str]) -> str | None:
    """Who made ``entry``, by name: ``None`` for the system or a removed user."""
    if entry.actor_id is None:
        return None
    return names.get(entry.actor_id)


def _organisation_of_organiser(organiser_id: int | str, session: Session) -> int:
    """The organiser's client organisation, read from their account.

    A request is filed under it (SCRUM-66 AC4), and the organiser sees that
    organisation's requests (SCRUM-7).

    Raises:
        OrganiserWithoutOrganisationError: 403 — an account from before SCRUM-66 that
            no one has linked to an organisation yet.
        NotFoundError: 404 — the token names a user that no longer exists.
    """
    organiser = get_user_by_id(organiser_id, session=session)
    if organiser.organisation_id is None:
        raise OrganiserWithoutOrganisationError(
            "Your account is not linked to a client organisation yet."
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


def _least_loaded_coordinator(session: Session) -> int | None:
    """The Event Coordinator with the fewest open requests (SCRUM-30 AC1, ADR-0018).

    The lowest user id wins a tie. ``None`` when there is no Event Coordinator at all.
    """
    coordinator_ids = list_user_ids_with_role(Role.EVENT_COORDINATOR, session=session)
    if not coordinator_ids:
        return None
    counts = _open_request_counts(coordinator_ids, session)

    def load_then_id(coordinator_id: int) -> tuple[int, int]:
        return counts[coordinator_id], coordinator_id

    return min(coordinator_ids, key=load_then_id)


def _mark_submitted(
    event_request: EventRequest, coordinator_id: int | None, session: Session
) -> None:
    """Move ``event_request`` to ``submitted`` and assign its coordinator, uncommitted.

    Sets both together, and records the assignment to the event history in the same
    transaction when there is a coordinator to assign (SCRUM-30 AC1, AC2, ADR-0018).
    Shared by submitting a new request and submitting a draft (SCRUM-20), so both
    reach ``submitted`` the same way. Does not commit: the caller decides when.

    Args:
        event_request: The request being submitted.
        coordinator_id: The coordinator to assign, or ``None`` to save unassigned.
        session: Database session the history entry is added to.
    """
    event_request.status = EventRequestStatus.SUBMITTED
    event_request.coordinator_id = coordinator_id
    if coordinator_id is not None:
        # Same commit as the request: a rolled-back attempt leaves no entry (AC2).
        record_event_history(
            event_request,
            EventHistoryKind.COORDINATOR_ASSIGNED,
            actor_id=None,
            details={"coordinator_id": coordinator_id},
            session=session,
        )


def _raise_notifications(
    recipient_ids: list[int],
    event_request: EventRequest,
    kind: NotificationKind,
    session: Session,
    *,
    detail: str | None = None,
) -> None:
    """Notify ``recipient_ids`` that ``kind`` happened to ``event_request``.

    Runs after the change's own commit, so the notifications refer to a saved row
    (ADR-0015). If they can't be saved, only they are lost and a warning is logged:
    what they announce is already saved, and failing the reply would invite the
    caller to do it again. ``detail`` says more, such as a decision's reason
    (SCRUM-31 AC10).
    """
    event = EventSummary(
        id=event_request.id, reference=event_request.reference, name=event_request.name
    )
    try:
        notify_users(recipient_ids, event, kind, session=session, detail=detail)
    except SQLAlchemyError:
        session.rollback()
        logger.warning(
            "event_request_notification_failed reference=%s kind=%s", event.reference, kind.value
        )


def _warn_unassigned(event_request: EventRequest) -> None:
    """Log that ``event_request`` has no coordinator, so someone can pick it up."""
    logger.warning("event_request_unassigned reference=%s", event_request.reference)


def _notify_about_assignment(
    event_request: EventRequest, coordinator_id: int, session: Session
) -> None:
    """Tell the new coordinator, then the organiser, that the request is assigned.

    The coordinator hears the event is theirs (SCRUM-30 AC4, SCRUM-87 AC4, SCRUM-39
    AC4), and the organiser who submitted it hears a coordinator has been assigned
    (SCRUM-39 AC1, ADR-0030). They are two separate writes, so losing one notice
    doesn't lose the other (ADR-0015).
    """
    _raise_notifications(
        [coordinator_id], event_request, NotificationKind.COORDINATOR_ASSIGNED, session
    )
    _raise_notifications(
        [event_request.organiser_id], event_request, NotificationKind.REQUEST_ASSIGNED, session
    )


def _notify_about_submission(event_request: EventRequest, session: Session) -> None:
    """Tell the assigned coordinator and the organiser about a new assignment.

    SCRUM-28 AC3 raises a new request to the coordinators; only the assigned one is
    told (ADR-0018, replacing ADR-0015's notice to every coordinator), and the
    organiser hears a coordinator has been assigned (SCRUM-39 AC1, ADR-0030). With no
    coordinator to assign the request stays unassigned and nobody is told; that is
    logged so someone can pick it up.
    """
    if event_request.coordinator_id is None:
        _warn_unassigned(event_request)
        return
    _notify_about_assignment(event_request, event_request.coordinator_id, session)


def _save_under_new_reference(
    new_request: Callable[[str], EventRequest],
    session: Session,
    reference_factory: Callable[[], str],
) -> EventRequest:
    """Build and save one row through ``new_request``, retrying a reference clash.

    Shared by every place that saves a request under a fresh reference (SCRUM-19,
    SCRUM-20 AC1, ADR-0004): only what the row looks like differs between them.
    ``new_request(reference)`` builds the row for that candidate reference and adds
    it, and anything that must be saved in the same commit (such as a history
    entry), to ``session``; this function only chooses the reference and commits. A
    reference collision rolls the attempt back and tries again with a new one, up
    to :data:`MAX_REFERENCE_ATTEMPTS` times; any other integrity error is raised as
    is, since a new reference would not fix it.

    Args:
        new_request: Builds and adds the row for a candidate reference.
        session: Database session to commit on.
        reference_factory: Makes a candidate reference each attempt.

    Returns:
        The row ``new_request`` built, once its commit has succeeded.

    Raises:
        ReferenceGenerationError: 500 — every attempt hit a used reference.
        IntegrityError: any other constraint failure; not retried.
    """
    for attempt in range(1, MAX_REFERENCE_ATTEMPTS + 1):
        reference = reference_factory()
        event_request = new_request(reference)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if not is_reference_collision(exc):
                raise
            logger.warning(
                "event_request_reference_collision reference=%s attempt=%d", reference, attempt
            )
            continue
        return event_request

    raise ReferenceGenerationError("Could not create the event request. Please try again.")


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
    coordinator is told it is theirs (SCRUM-28 AC3, SCRUM-30 AC4), and the organiser
    that a coordinator has been assigned (SCRUM-39 AC1, ADR-0030).

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
    coordinator_id = _least_loaded_coordinator(sess)

    def submitted_under(reference: str) -> EventRequest:
        """Build a request under ``reference``, then submit and assign it."""
        event_request = EventRequest(
            organiser_id=int(organiser_id),
            organisation_id=organisation_id,
            reference=reference,
            **data,
        )
        sess.add(event_request)
        _mark_submitted(event_request, coordinator_id, sess)
        return event_request

    event_request = _save_under_new_reference(submitted_under, sess, reference_factory)
    # Outside the retry: a failed notification commit is not a reference collision.
    _notify_about_submission(event_request, sess)
    return event_request


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


def _not_a_draft() -> ColumnElement[bool]:
    """The condition that a request has left the draft stage.

    The one definition of "past the draft stage" (SCRUM-20, ADR-0024), shared by
    every place that must not treat a draft as an ordinary request.
    """
    return EventRequest.status != EventRequestStatus.DRAFT


def _visible_to_organiser(organiser_id: int | str, session: Session) -> ColumnElement[bool]:
    """The event requests an organiser may see: their client organisation's (SCRUM-7).

    The organisation is read from the organiser's account each time, not from their
    token (ADR-0020). A request filed under no organisation matches nobody
    (ADR-0013). This is the one place an organiser's scope is decided, so their list
    and the detail of one request can't disagree; a colleague's draft is the one
    exception, kept from everyone but the organiser who wrote it (SCRUM-20 AC4,
    ADR-0024).

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no organisation.
        NotFoundError: 404 — the token names a user that no longer exists.
    """
    organisation_id = _organisation_of_organiser(organiser_id, session)
    written_by_them = EventRequest.organiser_id == int(organiser_id)
    return and_(
        EventRequest.organisation_id == organisation_id, or_(_not_a_draft(), written_by_them)
    )


def list_event_requests_for_organiser(
    organiser_id: int | str, *, session: Session | None = None
) -> list[EventRequest]:
    """Return the organiser's client organisation's event requests, newest first.

    Every organiser of the organisation gets the same list, whoever in it submitted
    each request (SCRUM-7 AC1, AC3; SCRUM-19 AC5).

    Args:
        organiser_id: The caller's user id, taken from their token.
        session: Database session; defaults to ``db.session``.

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no client
            organisation (ADR-0020).
        NotFoundError: 404 — the token names a user that no longer exists.
    """
    sess = resolve_session(session)
    return _list_event_requests_newest_first(_visible_to_organiser(organiser_id, sess), sess)


def _assigned_to(coordinator_id: int | str) -> ColumnElement[bool]:
    """The requests assigned to a coordinator (SCRUM-30 AC5)."""
    return EventRequest.coordinator_id == int(coordinator_id)


def list_event_requests_for_coordinator(
    coordinator_id: int | str, *, session: Session | None = None
) -> list[EventRequest]:
    """Return the requests assigned to the coordinator, newest first (SCRUM-30 AC5)."""
    return _list_event_requests_newest_first(_assigned_to(coordinator_id), resolve_session(session))


def _normalise_reference(reference: str) -> str:
    """A reference as typed by a user, trimmed and upper-cased (ADR-0004)."""
    return reference.strip().upper()


def _event_request_by_reference(
    reference: str, session: Session, *, belongs_to: ColumnElement[bool]
) -> EventRequest:
    """An event request by its reference, among those matching ``belongs_to``.

    Case and surrounding spaces are ignored (ADR-0004). A request outside
    ``belongs_to`` is not found, the same 404 as a reference that doesn't exist, so
    "not yours" can't be told apart from "no such request" (ADR-0012). Callers that
    check ownership afterwards answer "not yours" with that same 404 too. ``belongs_to``
    is required so that no caller can look a request up unscoped by accident and
    surface a draft it should never see (SCRUM-20, ADR-0024).

    Raises:
        NotFoundError: 404 — no such request, or none matching ``belongs_to``.
    """
    stmt = select(EventRequest).where(
        EventRequest.reference == _normalise_reference(reference), belongs_to
    )
    event_request = session.scalar(stmt)
    if event_request is None:
        raise NotFoundError(EVENT_REQUEST_NOT_FOUND_MESSAGE)
    return event_request


def _event_request_for_staff(reference: str, session: Session) -> EventRequest:
    """An event request by its reference, for internal staff (ADR-0019, ADR-0021).

    A draft is hidden from every internal role, not just the coordinator lookups:
    it belongs to its author alone until it is submitted (SCRUM-20 AC4, ADR-0024).

    Raises:
        NotFoundError: 404 — no such request, or it is still a draft.
    """
    return _event_request_by_reference(reference, session, belongs_to=_not_a_draft())


def get_event_request_for_organiser(
    organiser_id: int | str, reference: str, *, session: Session | None = None
) -> EventRequest:
    """Fetch one of the organiser's organisation's event requests by reference.

    Its status is SCRUM-22 AC2's. Any organiser of the request's client organisation
    may open it (SCRUM-7 AC3); a request of another organisation gets the same 404
    as a reference that doesn't exist (SCRUM-7 AC2, ADR-0012).

    Args:
        organiser_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no client
            organisation (ADR-0020).
        NotFoundError: 404 — no such request in the caller's organisation, or the
            token names a user that no longer exists.
    """
    sess = resolve_session(session)
    return _event_request_by_reference(
        reference, sess, belongs_to=_visible_to_organiser(organiser_id, sess)
    )


def _contact_of_coordinator(coordinator_id: int, session: Session) -> CoordinatorContact:
    """A coordinator's name and email, as the organiser sees them (SCRUM-30 AC3)."""
    coordinator = get_user_by_id(coordinator_id, session=session)
    return CoordinatorContact(full_name=coordinator.full_name, email=coordinator.email)


def _coordinator_contact(
    event_request: EventRequest, session: Session
) -> CoordinatorContact | None:
    """The request's assigned coordinator, or ``None`` while it has none (ADR-0018)."""
    if event_request.coordinator_id is None:
        return None
    return _contact_of_coordinator(event_request.coordinator_id, session)


def _current_decision_of(event_request: EventRequest, session: Session) -> DecisionAsShown | None:
    """The request's current decision, or ``None`` until one is recorded (AC9).

    Every decision stays in the history, and the most recent is the current one (AC8);
    of two at the same instant, the one recorded last wins. The coordinator's name is
    looked up now, so a removed coordinator shows as ``None`` (SCRUM-31, ADR-0028).
    """
    stmt = (
        select(EventHistoryEntry)
        .where(
            EventHistoryEntry.event_request_id == event_request.id,
            EventHistoryEntry.kind == EventHistoryKind.DECISION_RECORDED,
        )
        .order_by(EventHistoryEntry.occurred_at.desc(), EventHistoryEntry.id.desc())
        .limit(1)
    )
    entry = session.scalar(stmt)
    if entry is None:
        return None

    details = entry.details or {}
    names = get_user_full_names(_user_ids_named_in([entry]), session=session)
    return DecisionAsShown(
        outcome=details.get("outcome"),
        reason=details.get("reason"),
        decided_by=_actor_name(entry, names),
        decided_at=entry.occurred_at,
    )


def _clarification_entries(
    event_request: EventRequest, session: Session
) -> list[EventHistoryEntry]:
    """The request's clarification questions and answers, oldest first (SCRUM-32).

    Of two entries at the same instant, the one recorded first comes first.
    """
    stmt = (
        select(EventHistoryEntry)
        .where(
            EventHistoryEntry.event_request_id == event_request.id,
            EventHistoryEntry.kind.in_(
                [EventHistoryKind.CLARIFICATION_REQUESTED, EventHistoryKind.CLARIFICATION_ANSWERED]
            ),
        )
        .order_by(EventHistoryEntry.occurred_at, EventHistoryEntry.id)
    )
    return list(session.scalars(stmt))


def _clarifications_of(
    event_request: EventRequest, session: Session
) -> tuple[ClarificationAsShown, ...]:
    """Every clarification question in the order asked, each with its answer (AC4).

    An answer belongs to the question just before it; an answer with no question
    before it has nothing to belong to and is skipped. Names are looked up now, so a
    removed user shows as ``None`` (as SCRUM-31's decision does, ADR-0028).
    """
    entries = _clarification_entries(event_request, session)
    names = get_user_full_names(_user_ids_named_in(entries), session=session)

    shown: list[ClarificationAsShown] = []
    for entry in entries:
        details = entry.details or {}
        if entry.kind is EventHistoryKind.CLARIFICATION_REQUESTED:
            question = ClarificationAsShown(
                message=details.get("message"),
                requested_by=_actor_name(entry, names),
                requested_at=entry.occurred_at,
            )
            shown.append(question)
        elif shown:
            # An answer: it answers the last question asked.
            shown[-1] = replace(
                shown[-1],
                response=details.get("response"),
                answered_by=_actor_name(entry, names),
                answered_at=entry.occurred_at,
            )
    return tuple(shown)


def _event_record(event_request: EventRequest, session: Session) -> EventRecord:
    """The request with the sections its record shows.

    Its coordinator (SCRUM-30 AC3), its decision (SCRUM-31 AC9) and its clarification
    exchange (SCRUM-32 AC4).
    """
    return EventRecord(
        event_request=event_request,
        coordinator=_coordinator_contact(event_request, session),
        decision=_current_decision_of(event_request, session),
        clarifications=_clarifications_of(event_request, session),
    )


def get_event_record_for_organiser(
    organiser_id: int | str, reference: str, *, session: Session | None = None
) -> EventRecord:
    """One of the organisation's requests and its assigned coordinator (SCRUM-30 AC3).

    Same lookup and scope as :func:`get_event_request_for_organiser`; the coordinator
    is ``None`` until one is assigned (ADR-0018).

    Args:
        organiser_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request's record: the request, and its coordinator's name and email or
        ``None``.

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no client
            organisation (ADR-0020).
        NotFoundError: 404 — no such request in the caller's organisation, or the
            token names a user that no longer exists.
    """
    sess = resolve_session(session)
    event_request = get_event_request_for_organiser(organiser_id, reference, session=sess)
    return _event_record(event_request, sess)


# --------------------------------------------------------------------------
# SCRUM-20 — save and resume a draft event request
# --------------------------------------------------------------------------


def save_draft_event_request(
    organiser_id: int | str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    reference_factory: Callable[[], str] = generate_reference,
) -> EventRequest:
    """Save a new draft event request with only its name required (SCRUM-20 AC1).

    Every other field is optional and, when sent, is checked on its own; the rules
    that only apply once a request is submitted wait for that (ADR-0024). The draft
    is filed under the organiser's client organisation like any other request
    (SCRUM-66 AC4), under a fresh reference kept if it is later submitted (ADR-0004).
    It gets no coordinator, no event history and no notification: nothing has
    happened to it yet but its own saving.

    Args:
        organiser_id: The caller's user id, taken from their token.
        payload: Decoded JSON body.
        session: Database session; defaults to ``db.session``.
        reference_factory: Makes references; tests swap it out.

    Returns:
        The saved, draft :class:`EventRequest`.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
        OrganiserWithoutOrganisationError: 403 — the organiser has no client
            organisation (ADR-0013).
        NotFoundError: 404 — the token names a user that no longer exists.
        ReferenceGenerationError: 500 — every attempt hit a used reference.
    """
    data = load_or_raise(SaveDraftSchema(), payload)
    sess = resolve_session(session)
    organisation_id = _organisation_of_organiser(organiser_id, sess)

    def draft_under(reference: str) -> EventRequest:
        """Build a draft under ``reference`` and add it to the session."""
        draft = EventRequest(
            organiser_id=int(organiser_id),
            organisation_id=organisation_id,
            reference=reference,
            status=EventRequestStatus.DRAFT,
            **data,
        )
        sess.add(draft)
        return draft

    return _save_under_new_reference(draft_under, sess, reference_factory)


#: Shared by editing a draft and submitting one: both work only on a draft, and
#: refuse the same way once the request has moved on (SCRUM-20 AC3, ADR-0024).
NOT_A_DRAFT_MESSAGE = "Only a draft event request can be changed or submitted this way."


class RequestNotDraftError(AppError):
    """The request has moved past the draft stage, so it can't be used as one (409)."""

    status_code = 409
    error_code = "request_not_draft"


def _draft_of_organiser(organiser_id: int | str, reference: str, session: Session) -> EventRequest:
    """The organiser's own draft by reference (SCRUM-20 AC3, AC4).

    Goes through :func:`get_event_request_for_organiser`, so a colleague's draft is
    the same 404 as any other request outside the organiser's scope (ADR-0024); only
    once the request is found and is genuinely theirs does its status decide whether
    it may still be handled as a draft.

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no organisation.
        NotFoundError: 404 — no such request, or it is a colleague's draft.
        RequestNotDraftError: 409 — the request has already been submitted.
    """
    event_request = get_event_request_for_organiser(organiser_id, reference, session=session)
    if event_request.status is not EventRequestStatus.DRAFT:
        raise RequestNotDraftError(NOT_A_DRAFT_MESSAGE)
    return event_request


def update_draft_event_request(
    organiser_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventRequest:
    """Change the fields sent on one of the organiser's own drafts (SCRUM-20 AC3).

    Only the fields in ``payload`` change; a field sent as ``null`` clears it, except
    ``name``, which still identifies the draft to its author and so can never be
    blank or null. An empty body changes nothing. Every field sent is checked the
    same way a save is (SCRUM-20 AC1); the rules that only apply on submission still
    wait (ADR-0024).

    Args:
        organiser_id: The caller's user id, taken from their token.
        reference: The draft's ``EVR-…`` reference; case and surrounding spaces are
            ignored.
        payload: Decoded JSON body: any subset of the fields a draft may hold.
        session: Database session; defaults to ``db.session``.

    Returns:
        The updated, still-draft :class:`EventRequest`.

    Raises:
        ValidationError: 400 — a field sent is invalid (details per field).
        OrganiserWithoutOrganisationError: 403 — the organiser has no organisation.
        NotFoundError: 404 — no such draft, or it is a colleague's.
        RequestNotDraftError: 409 — the request has already been submitted.
    """
    schema = SaveDraftSchema()
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    draft = _draft_of_organiser(organiser_id, reference, sess)
    for key, value in data.items():
        setattr(draft, key, value)
    sess.commit()
    return draft


def _draft_as_payload(draft: EventRequest, schema: Schema) -> dict[str, Any]:
    """The draft's fields, as a payload ready for ``schema`` to load (SCRUM-20 AC3).

    Dumped with :class:`EventRequestSchema` and then loaded straight back through
    ``schema``, so submitting a draft is checked exactly the way a brand new
    submission is (ADR-0001 to ADR-0003): the two paths can never quietly diverge.
    A detail the draft never got comes back from the dump as ``None``; leaving it
    out here, rather than sending an explicit ``null``, is what makes a still-missing
    required field report "Missing data for required field.", the same message
    ``POST /requests`` gives for a field left out altogether.

    Args:
        draft: The draft being submitted.
        schema: The schema the payload will be loaded by; only its fields are dumped.

    Returns:
        The draft's non-``None`` fields, keyed the way ``schema`` expects them.
    """
    dumped = EventRequestSchema(only=tuple(schema.fields)).dump(draft)
    return {key: value for key, value in dumped.items() if value is not None}


def submit_draft_event_request(
    organiser_id: int | str,
    reference: str,
    *,
    session: Session | None = None,
    today: date | None = None,
) -> EventRequest:
    """Submit one of the organiser's own drafts under the submission rules (SCRUM-20).

    The stored draft is run back through :class:`SubmitEventRequestSchema` exactly as
    a new submission would be (ADR-0001 to ADR-0003, ADR-0024): a detail the draft
    never got, or one that fails a rule (a past date, an end before the start), is
    reported the same way ``POST /requests`` reports it, and nothing changes unless
    every rule passes. Its reference does not change (ADR-0004); like a fresh
    submission, it is assigned to the least-loaded Event Coordinator, the assignment
    is recorded to its event history, and that coordinator and the organiser are
    notified (SCRUM-30 AC1, AC2, AC4, ADR-0018; SCRUM-39 AC1, ADR-0030).

    Args:
        organiser_id: The caller's user id, taken from their token.
        reference: The draft's ``EVR-…`` reference; case and surrounding spaces are
            ignored.
        session: Database session; defaults to ``db.session``.
        today: Reference date for the "not in the past" rule; defaults to today in
            the business timezone.

    Returns:
        The now-submitted :class:`EventRequest`.

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no organisation.
        NotFoundError: 404 — no such draft, or it is a colleague's.
        RequestNotDraftError: 409 — the request has already been submitted.
        ValidationError: 400 — a detail is missing, or fails a submission rule.
    """
    sess = resolve_session(session)
    draft = _draft_of_organiser(organiser_id, reference, sess)
    schema = SubmitEventRequestSchema(today=today)
    data = load_or_raise(schema, _draft_as_payload(draft, schema))
    for key, value in data.items():
        setattr(draft, key, value)
    _mark_submitted(draft, _least_loaded_coordinator(sess), sess)
    sess.commit()
    _notify_about_submission(draft, sess)
    return draft


# --------------------------------------------------------------------------
# SCRUM-37 — record what equipment an event needs
# --------------------------------------------------------------------------

#: Statuses in which an event's equipment may change: while its request awaits review
#: (SCRUM-37 AC2, ADR-0019), and once it is approved, while the event is planned
#: (SCRUM-31, ADR-0028). Not while it awaits clarification: the request is then the
#: organiser's to change, not the coordinator's (SCRUM-32, ADR-0029).
EQUIPMENT_EDITABLE_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.SUBMITTED, EventRequestStatus.UNDER_REVIEW, EventRequestStatus.APPROVED}
)
EQUIPMENT_NOT_EDITABLE_MESSAGE = (
    "Equipment can only be changed while the request is submitted, under review or approved."
)
DUPLICATE_LINE_MESSAGE = (
    "This event already has a line for that equipment type. Edit that line instead."
)


class EquipmentNotEditableError(AppError):
    """The request's status no longer lets its equipment change (409)."""

    status_code = 409
    error_code = "equipment_not_editable"


def _check_assigned_to(coordinator_id: int | str, event_request: EventRequest) -> None:
    """Refuse a coordinator the request isn't assigned to (ADR-0019).

    Another coordinator's request, or an unassigned one, gets the same 404 as a
    reference that doesn't exist, as an organiser's "not yours" does (ADR-0012).

    Raises:
        NotFoundError: 404 — the request isn't assigned to ``coordinator_id``.
    """
    if event_request.coordinator_id != int(coordinator_id):
        raise NotFoundError(EVENT_REQUEST_NOT_FOUND_MESSAGE)


def _event_request_assigned_to(
    coordinator_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The request, if ``coordinator_id`` is its assigned coordinator (ADR-0019).

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own, or it is
            still a draft (SCRUM-20, ADR-0024).
    """
    event_request = _event_request_for_staff(reference, session)
    _check_assigned_to(coordinator_id, event_request)
    return event_request


@dataclass(frozen=True)
class EventForBooking:
    """What a venue booking request needs to know about its event (SCRUM-42).

    The event's timing stays in local business time, as the event stores it. An
    approved event always has its dates and times (SCRUM-22, SCRUM-31).
    """

    id: int
    reference: str
    name: str
    status: EventRequestStatus
    proposed_date: date
    end_date: date | None
    start_time: time
    end_time: time
    expected_attendance: int
    accessibility_needs: str | None


def get_event_for_coordinator(
    reference: str, coordinator_id: int | str, *, session: Session | None = None
) -> EventForBooking:
    """The event ``coordinator_id`` is assigned to, at any status (SCRUM-42, ADR-0019).

    The event is found by its ``EVR-…`` reference; case and surrounding spaces are
    ignored (ADR-0004).

    Raises:
        NotFoundError: 404 — no such event, or it isn't assigned to this coordinator.
    """
    event_request = _event_request_assigned_to(coordinator_id, reference, resolve_session(session))
    return EventForBooking(
        id=event_request.id,
        reference=event_request.reference,
        name=event_request.name,
        status=event_request.status,
        proposed_date=event_request.proposed_date,
        end_date=event_request.end_date,
        start_time=event_request.start_time,
        end_time=event_request.end_time,
        expected_attendance=event_request.expected_attendance,
        accessibility_needs=event_request.accessibility_needs,
    )


def get_approved_event_for_coordinator(
    reference: str, coordinator_id: int | str, *, session: Session | None = None
) -> EventForBooking:
    """The approved event ``coordinator_id`` is assigned to (SCRUM-42, ADR-0019).

    Raises:
        NotFoundError: 404 — no such event, or it isn't assigned to this coordinator.
        ConflictError: 409 — the event isn't approved; the message names its status.
    """
    event = get_event_for_coordinator(reference, coordinator_id, session=session)
    if event.status is not EventRequestStatus.APPROVED:
        raise ConflictError(
            "Only an approved event can have a venue booking request;"
            f" this one is {event.status.value}."
        )
    return event


def record_venue_booking_requested(
    event_id: int,
    *,
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for a venue booking request, without committing (SCRUM-42).

    The entry rides in the caller's transaction, so it is saved with the request it
    records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        EventHistoryKind.VENUE_BOOKING_REQUESTED,
        actor_id=actor_id,
        details=details,
        session=session,
    )


def _event_request_with_editable_equipment(
    coordinator_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The coordinator's request, if its equipment may still change (SCRUM-37 AC2).

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own; a draft is
            never found (ADR-0024).
        EquipmentNotEditableError: 409 — the request's equipment can no longer change.
    """
    event_request = _event_request_assigned_to(coordinator_id, reference, session)
    if event_request.status not in EQUIPMENT_EDITABLE_STATUSES:
        raise EquipmentNotEditableError(EQUIPMENT_NOT_EDITABLE_MESSAGE)
    return event_request


def _check_equipment_type(equipment_type_id: int, session: Session) -> None:
    """Reject an equipment type that isn't in the catalogue, as a 400 on its field."""
    try:
        equipment_services.get_equipment_type(equipment_type_id, session=session)
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


def _notify_technical_support(
    event_request: EventRequest, kind: NotificationKind, session: Session
) -> None:
    """Tell every Technical Support Staff member about ``event_request`` (ADR-0019).

    Used when equipment is requested for it (SCRUM-37 AC5) and when a significant
    change means equipment already requested for it may no longer fit (SCRUM-33 AC2,
    ADR-0025).
    """
    technical_support_ids = list_user_ids_with_role(Role.TECHNICAL_SUPPORT_STAFF, session=session)
    _raise_notifications(technical_support_ids, event_request, kind, session)


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
        EquipmentNotEditableError: 409 — the request's equipment can no longer change.
        ConflictError: 409 — the event already has a line for that equipment type.
    """
    data = load_or_raise(EditEquipmentLineSchema(), payload)
    sess = resolve_session(session)
    event_request = _event_request_with_editable_equipment(coordinator_id, reference, sess)
    _check_equipment_type(data["equipment_type_id"], sess)

    line = EventEquipmentLine(
        event_request_id=event_request.id, status=EquipmentLineStatus.REQUESTED, **data
    )
    sess.add(line)
    _commit_line_or_conflict(sess)
    _notify_technical_support(event_request, NotificationKind.EQUIPMENT_REQUESTED, sess)
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
        event_request = _event_request_for_staff(reference, sess)
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
    ``null``. Only the event's assigned coordinator may, while its equipment may still
    change (ADR-0019).

    Returns:
        The updated :class:`EventEquipmentLine`.

    Raises:
        ValidationError: 400 — invalid values for the fields sent, or no such
            equipment type.
        NotFoundError: 404 — no such event request among the coordinator's own, or no
            such line on it.
        EquipmentNotEditableError: 409 — the request's equipment can no longer change.
        ConflictError: 409 — another line on the event already has that equipment type.
    """
    schema = EditEquipmentLineSchema()
    data = load_or_raise(schema, payload, partial=tuple(schema.fields))
    sess = resolve_session(session)
    event_request = _event_request_with_editable_equipment(coordinator_id, reference, sess)
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

    Only the event's assigned coordinator may, while its equipment may still change.
    Nobody is notified (ADR-0019).

    Raises:
        NotFoundError: 404 — no such event request among the coordinator's own, or no
            such line on it.
        EquipmentNotEditableError: 409 — the request's equipment can no longer change.
    """
    sess = resolve_session(session)
    event_request = _event_request_with_editable_equipment(coordinator_id, reference, sess)
    line = _line_of_event(event_request, line_id, sess)
    sess.delete(line)
    sess.commit()


# --------------------------------------------------------------------------
# SCRUM-87 — reassign an event to a different coordinator
# --------------------------------------------------------------------------

#: Statuses in which an event request may move to another coordinator: from
#: submission until the event is over (SCRUM-87, ADR-0021; ``approved`` from SCRUM-31,
#: ADR-0028; ``awaiting_clarification`` from SCRUM-32, ADR-0029). A completed, cancelled
#: or rejected event has nothing left to coordinate; a draft is hidden from
#: coordinators altogether, so it never reaches this check (SCRUM-20, ADR-0024).
REASSIGNABLE_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.AWAITING_CLARIFICATION,
        EventRequestStatus.APPROVED,
        EventRequestStatus.CONFIRMED,
    }
)
NOT_REASSIGNABLE_MESSAGE = (
    "Only a submitted, under-review, awaiting-clarification, approved or confirmed event "
    "request can be reassigned."
)
NOT_ASSIGNED_MESSAGE = "This event request has no coordinator to reassign from."
NOT_A_COORDINATOR_MESSAGE = "No Event Coordinator has this email address."
ALREADY_ASSIGNED_MESSAGE = "That coordinator is already assigned to this event request."


class RequestNotReassignableError(AppError):
    """The request can't move to another coordinator in its current state (409)."""

    status_code = 409
    error_code = "request_not_reassignable"


def _coordinator_to_replace(actor_id: int | str, event_request: EventRequest) -> int:
    """The caller, if the request is theirs to hand on (ADR-0021).

    Only its current coordinator may reassign a request. The ownership check comes
    after the "no coordinator" one, which has its own answer, and before the status
    one, so another coordinator learns no more about a finished event than about an
    open one.

    Raises:
        RequestNotReassignableError: 409 — the request has no coordinator.
        NotFoundError: 404 — the caller isn't its coordinator (ADR-0019).
        RequestNotReassignableError: 409 — the request isn't submitted, under review
            or confirmed.
    """
    if event_request.coordinator_id is None:
        raise RequestNotReassignableError(NOT_ASSIGNED_MESSAGE)
    _check_assigned_to(actor_id, event_request)
    if event_request.status not in REASSIGNABLE_STATUSES:
        raise RequestNotReassignableError(NOT_REASSIGNABLE_MESSAGE)
    return event_request.coordinator_id


def _event_coordinator_id_by_email(email: str, session: Session) -> int:
    """The id of the Event Coordinator with this email; case is ignored (ADR-0021).

    An unknown email and another role's email get the same answer, a 400 on the
    field, so the reply doesn't say whether someone else holds that address.

    Raises:
        ValidationError: 400 — no Event Coordinator has that email.
    """
    user = get_user_by_email(email, session=session)
    if user is None or user.role is not Role.EVENT_COORDINATOR:
        raise ValidationError(
            "Invalid request.", details={"coordinator_email": [NOT_A_COORDINATOR_MESSAGE]}
        )
    return user.id


def reassign_coordinator(
    actor_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> tuple[EventRequest, CoordinatorContact]:
    """Move an event request to a different Event Coordinator (SCRUM-87).

    Only the request's current coordinator may do it, while it is submitted, under
    review or confirmed (ADR-0021). The request's one ``coordinator_id`` is replaced
    (AC1, AC2), and a ``coordinator_reassigned`` history entry is saved in the same
    commit: the previous and the new coordinator's ids and names as they were then,
    who did it and when (AC3, AC7). The event then lists, and gives access to, the new
    coordinator only (AC4, AC5). Once saved, the new coordinator gets the usual
    ``coordinator_assigned`` notification (AC4) and the organiser a ``request_assigned``
    one (SCRUM-39 AC1, ADR-0030); a failure there is logged, not raised (ADR-0015).
    The previous coordinator isn't notified, since they made the change.

    Args:
        actor_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``coordinator_email``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, and the new coordinator's name and email, as the organiser now
        sees them (AC6).

    Raises:
        ValidationError: 400 — payload invalid, or no Event Coordinator has that
            email.
        NotFoundError: 404 — no such request, or the caller isn't its coordinator.
        RequestNotReassignableError: 409 — the request has no coordinator, or isn't
            submitted, under review, approved or confirmed.
        ConflictError: 409 — that coordinator already has the request.
    """
    data = load_or_raise(ReassignCoordinatorSchema(), payload)
    sess = resolve_session(session)
    event_request = _event_request_for_staff(reference, sess)
    previous_coordinator_id = _coordinator_to_replace(actor_id, event_request)
    coordinator_id = _event_coordinator_id_by_email(data["coordinator_email"], sess)
    if coordinator_id == previous_coordinator_id:
        raise ConflictError(ALREADY_ASSIGNED_MESSAGE)
    previous_coordinator = _contact_of_coordinator(previous_coordinator_id, sess)
    coordinator = _contact_of_coordinator(coordinator_id, sess)

    event_request.coordinator_id = coordinator_id
    # The names are kept as they are now, so the history reads the same if a user is
    # renamed or removed later (AC3).
    record_event_history(
        event_request,
        EventHistoryKind.COORDINATOR_REASSIGNED,
        actor_id=int(actor_id),
        details={
            "previous_coordinator_id": previous_coordinator_id,
            "previous_coordinator_name": previous_coordinator.full_name,
            "coordinator_id": coordinator_id,
            "coordinator_name": coordinator.full_name,
        },
        session=sess,
    )
    sess.commit()
    # The previous coordinator isn't told: only they may reassign, so they did this.
    _notify_about_assignment(event_request, coordinator_id, sess)
    return event_request, coordinator


# --------------------------------------------------------------------------
# SCRUM-38 — the equipment requests awaiting Technical Support
# --------------------------------------------------------------------------

#: Statuses of events that won't run, so their equipment no longer needs arranging
#: (SCRUM-38 AC1, ADR-0022).
EQUIPMENT_NOT_NEEDED_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.COMPLETED, EventRequestStatus.CANCELLED, EventRequestStatus.REJECTED}
)
#: Why a reservation is refused for such an event; names the statuses above.
RESERVATIONS_CLOSED_MESSAGE = (
    "Equipment can't be reserved for an event that is completed, cancelled or rejected."
)


@dataclass(frozen=True)
class EquipmentAwaitingAction:
    """One event's equipment still to arrange, and how long is left (SCRUM-38 AC2).

    ``equipment_lines`` holds only the lines still ``requested``, in the order added.
    ``days_remaining`` counts whole days from today to the event's date: 0 on the day.
    """

    event_request: EventRequest
    equipment_lines: list[EventEquipmentLine]
    days_remaining: int


def _group_lines_by_event(
    rows: Iterable[Row[tuple[EventRequest, EventEquipmentLine]]], today: date
) -> list[EquipmentAwaitingAction]:
    """One entry per event, in the order the events first appear in ``rows``."""
    events: list[EventRequest] = []
    lines_by_event: dict[int, list[EventEquipmentLine]] = {}
    for event_request, line in rows:
        if event_request.id not in lines_by_event:
            events.append(event_request)
            lines_by_event[event_request.id] = []
        lines_by_event[event_request.id].append(line)

    awaiting = []
    for event_request in events:
        # The query above keeps only events with a proposed_date (SCRUM-38 AC1); only a
        # draft has none, and a draft never reaches this list (SCRUM-20, ADR-0024).
        days_remaining = (event_request.proposed_date - today).days  # type: ignore[operator]
        awaiting.append(
            EquipmentAwaitingAction(
                event_request=event_request,
                equipment_lines=lines_by_event[event_request.id],
                days_remaining=days_remaining,
            )
        )
    return awaiting


def list_equipment_requests_awaiting_action(
    *, session: Session | None = None, today: date | None = None
) -> list[EquipmentAwaitingAction]:
    """The equipment Technical Support still have to arrange, soonest event first.

    SCRUM-38 AC1-AC4, ADR-0022. An event is listed while at least one of its lines is
    still ``requested``, its proposed date is today or later, and it isn't completed,
    cancelled or rejected. Each entry holds only the lines still ``requested``, so an
    event drops off once none is. Events are ordered by date, then start time, then
    as submitted. One list for all Technical Support Staff.

    Args:
        session: Database session; defaults to ``db.session``.
        today: The business date "not yet taken place" and the days remaining are
            measured from; defaults to today in the business timezone (ADR-0001).

    Returns:
        One :class:`EquipmentAwaitingAction` per event.
    """
    sess = resolve_session(session)
    if today is None:
        today = local_today()
    # One query for the lines themselves: the event's ``equipment_lines`` would load
    # the lines already arranged too, and query once per event.
    stmt = (
        select(EventRequest, EventEquipmentLine)
        .join(EventEquipmentLine, EventEquipmentLine.event_request_id == EventRequest.id)
        .where(
            EventEquipmentLine.status == EquipmentLineStatus.REQUESTED,
            EventRequest.proposed_date >= today,
            EventRequest.status.not_in(EQUIPMENT_NOT_NEEDED_STATUSES),
        )
        .order_by(
            EventRequest.proposed_date,
            EventRequest.start_time,
            EventRequest.id,
            EventEquipmentLine.id,
        )
    )
    return _group_lines_by_event(sess.execute(stmt), today)


# --------------------------------------------------------------------------
# SCRUM-33 — update event information and flag significant changes
# --------------------------------------------------------------------------

#: Statuses in which an assigned coordinator may still edit a request (ADR-0025;
#: ``approved`` from SCRUM-31, ADR-0028).
#: A completed event is set in stone (SCRUM-68 only changes its status to that); a
#: draft has no coordinator to edit it, and a cancelled or rejected event is over.
#: A request awaiting clarification is the organiser's to change, not the
#: coordinator's, until the organiser answers (SCRUM-32, ADR-0029).
EDITABLE_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.APPROVED,
        EventRequestStatus.CONFIRMED,
    }
)
NOT_EDITABLE_MESSAGE = (
    "Only a submitted, under-review, approved or confirmed event request can be edited."
)

#: Changing when or how big an event is could affect a venue already booked or being
#: searched for, and equipment already requested for it (ADR-0025).
_TIMING_AND_SIZE_FIELDS = (
    "proposed_date",
    "end_date",
    "start_time",
    "end_time",
    "expected_attendance",
)

#: Fields whose change could mean a venue already booked, or being searched for, no
#: longer fits (ADR-0025). Nothing reads this yet: SCRUM-58 will, once SCRUM-42 gives
#: events venue bookings to reassess; declared now so that story doesn't have to
#: rediscover the field list.
VENUE_AFFECTING_FIELDS: frozenset[str] = frozenset({*_TIMING_AND_SIZE_FIELDS, "venue_requirements"})

#: Fields whose change could mean equipment already requested for the event no
#: longer fits (ADR-0025).
EQUIPMENT_AFFECTING_FIELDS: frozenset[str] = frozenset(
    {*_TIMING_AND_SIZE_FIELDS, "equipment_requirements"}
)

#: Every field whose change is marked significant in the event's history (ADR-0025).
SIGNIFICANT_FIELDS: frozenset[str] = VENUE_AFFECTING_FIELDS | EQUIPMENT_AFFECTING_FIELDS

#: What a changed field's value is stored as in the history's JSON ``details``
#: (ADR-0025): a date or time becomes its ISO string, everything else keeps its
#: native JSON type.
HistoryValue = str | int | None


class RequestNotEditableError(AppError):
    """The request isn't in a status that can be edited right now (409)."""

    status_code = 409
    error_code = "request_not_editable"


@dataclass(frozen=True)
class FieldChange:
    """One field an edit changed, as the history and the API show it (ADR-0025)."""

    field: str
    previous_value: HistoryValue
    new_value: HistoryValue
    significant: bool


@dataclass(frozen=True)
class EventEdit:
    """What :func:`update_event_request` did: the request, and what changed on it."""

    event_request: EventRequest
    changes: list[FieldChange]


def _as_history_value(value: Any) -> HistoryValue:
    """``value`` in the form the history's JSON ``details`` column can hold."""
    if isinstance(value, date | time):
        return value.isoformat()
    return value


def _event_request_editable_by(
    coordinator_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The coordinator's request, if it can still be edited (ADR-0025).

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own; a draft is
            never found (ADR-0024).
        RequestNotEditableError: 409 — the request isn't submitted, under review,
            approved or confirmed.
    """
    event_request = _event_request_assigned_to(coordinator_id, reference, session)
    if event_request.status not in EDITABLE_STATUSES:
        raise RequestNotEditableError(NOT_EDITABLE_MESSAGE)
    return event_request


def _changes_to(event_request: EventRequest, data: Mapping[str, Any]) -> list[FieldChange]:
    """What in ``data`` differs from ``event_request``'s values (ADR-0025).

    A sent value equal to what is already saved is not a change.
    """
    changes = []
    for field, new_value in data.items():
        previous_value = getattr(event_request, field)
        if new_value == previous_value:
            continue
        changes.append(
            FieldChange(
                field=field,
                previous_value=_as_history_value(previous_value),
                new_value=_as_history_value(new_value),
                significant=field in SIGNIFICANT_FIELDS,
            )
        )
    return changes


def _affects_equipment(changes: list[FieldChange]) -> bool:
    """Whether any of ``changes`` touches a field in EQUIPMENT_AFFECTING_FIELDS."""
    return any(change.field in EQUIPMENT_AFFECTING_FIELDS for change in changes)


def _reassess_arrangements(
    event_request: EventRequest, changes: list[FieldChange], session: Session
) -> None:
    """Warn whoever has arrangements riding on the event that it changed (ADR-0025).

    Technical Support Staff get one ``significant_change`` notification per edit
    when a changed field could affect equipment already requested and the event has
    at least one equipment line (AC2); with no lines there is nothing to reassess.
    Runs after the edit's own commit, so a failed notification never rolls back a
    saved edit; the failure is logged, not raised (ADR-0015).
    """
    # TODO: SCRUM-58 flags the event's venue booking here when a change touches
    # VENUE_AFFECTING_FIELDS, once SCRUM-42 has given events one to reassess.
    if not _affects_equipment(changes) or not event_request.equipment_lines:
        return
    _notify_technical_support(event_request, NotificationKind.SIGNIFICANT_CHANGE, session)


def _record_field_changes(
    event_request: EventRequest,
    actor_id: int,
    data: Mapping[str, Any],
    *,
    session: Session,
    now: datetime,
) -> list[FieldChange]:
    """Apply what in ``data`` differs from ``event_request``, without committing.

    Each changed field is set on the request and written to its history as a
    ``field_changed`` entry by ``actor_id`` at ``now`` (ADR-0025), in the caller's
    transaction.

    Returns:
        The changes made, in ``data``'s order; empty when nothing differs.
    """
    changes = _changes_to(event_request, data)
    for change in changes:
        setattr(event_request, change.field, data[change.field])
        record_event_history(
            event_request,
            EventHistoryKind.FIELD_CHANGED,
            actor_id=actor_id,
            details=asdict(change),
            session=session,
            now=now,
        )
    return changes


def update_event_request(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    today: date | None = None,
) -> EventEdit:
    """Change the fields sent on a request assigned to the caller (SCRUM-33 AC1-AC4).

    Only what is sent in ``payload`` changes (AC1, AC3); a value equal to what is
    already saved is not a change. Each changed field is written to the event
    history as its own ``field_changed`` entry, sharing one ``occurred_at``, in the
    same commit as the change itself (AC2, AC4); a field in
    :data:`SIGNIFICANT_FIELDS` is marked ``significant``. An edit that changes
    nothing writes and commits nothing.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The event request's ``EVR-…`` reference; case and surrounding
            spaces are ignored.
        payload: Decoded JSON body: any subset of the editable fields.
        session: Database session; defaults to ``db.session``.
        today: Reference date for the "not in the past" rule; defaults to today in
            the business timezone.

    Returns:
        The request, and the changes made, in the order
        :class:`EditEventRequestSchema` lists its fields. Empty when nothing changed.

    Raises:
        ValidationError: 400 — payload invalid (details per field).
        NotFoundError: 404 — no such event request among the coordinator's own.
        RequestNotEditableError: 409 — the request isn't submitted, under review,
            approved or confirmed.
    """
    sess = resolve_session(session)
    event_request = _event_request_editable_by(coordinator_id, reference, sess)
    data = load_or_raise(EditEventRequestSchema(event_request, today=today), payload)
    changes = _record_field_changes(
        event_request,
        int(coordinator_id),
        data,
        session=sess,
        now=datetime.now(timezone.utc),
    )
    if not changes:
        return EventEdit(event_request, [])

    sess.commit()
    _reassess_arrangements(event_request, changes, sess)
    return EventEdit(event_request, changes)


#: A field_changed entry about one of these is for internal eyes only (ADR-0025).
INTERNAL_ONLY_FIELDS: frozenset[str] = frozenset({"internal_planning_notes"})
#: Entries of these kinds are for internal eyes only: which equipment Technical
#: Support set aside is their working, not the organiser's (SCRUM-46, ADR-0037).
INTERNAL_ONLY_KINDS: frozenset[EventHistoryKind] = frozenset({EventHistoryKind.EQUIPMENT_RESERVED})


@dataclass(frozen=True)
class HistoryEntryAsShown:
    """One event history entry as the API shows it (ADR-0025): no user ids."""

    kind: EventHistoryKind
    occurred_at: datetime
    actor_name: str | None
    details: dict[str, Any]


def _history_entries(event_request: EventRequest, session: Session) -> list[EventHistoryEntry]:
    """``event_request``'s history, oldest first (ADR-0025)."""
    stmt = (
        select(EventHistoryEntry)
        .where(EventHistoryEntry.event_request_id == event_request.id)
        .order_by(EventHistoryEntry.occurred_at, EventHistoryEntry.id)
    )
    return list(session.scalars(stmt))


def _shown_to_organiser(entry: EventHistoryEntry) -> bool:
    """Whether the organiser may see ``entry`` (ADR-0025).

    Every kind but an internal-only kind and a ``field_changed`` entry about an
    internal-only field.
    """
    if entry.kind in INTERNAL_ONLY_KINDS:
        return False
    if entry.kind is not EventHistoryKind.FIELD_CHANGED:
        return True
    details = entry.details or {}
    return details.get("field") not in INTERNAL_ONLY_FIELDS


def _details_as_shown(entry: EventHistoryEntry, names: dict[int, str]) -> dict[str, Any]:
    """``entry.details`` as the API shows it: names resolved, no ids (ADR-0025).

    ``coordinator_assigned`` shows the coordinator's current name, looked up by id.
    ``coordinator_reassigned`` keeps the names its own ``details`` already stored from
    when the change happened, and drops the ids. ``field_changed`` is shown
    unchanged: its values are already JSON-safe and it carries no user id.
    """
    details = entry.details or {}
    if entry.kind is EventHistoryKind.COORDINATOR_ASSIGNED:
        coordinator_id = details.get("coordinator_id")
        coordinator_name = None
        if coordinator_id is not None:
            coordinator_name = names.get(coordinator_id)
        return {"coordinator_name": coordinator_name}
    if entry.kind is EventHistoryKind.COORDINATOR_REASSIGNED:
        return {
            "previous_coordinator_name": details.get("previous_coordinator_name"),
            "coordinator_name": details.get("coordinator_name"),
        }
    return details


def list_event_history(
    viewer_id: int | str, reference: str, *, viewer_role: Role, session: Session | None = None
) -> list[HistoryEntryAsShown]:
    """An event's history, oldest first, with names resolved and no user ids (SCRUM-33).

    Internal staff may see any event's history; an Event Organiser only their client
    organisation's, and never a ``field_changed`` entry about
    ``internal_planning_notes`` (ADR-0025) or an ``equipment_reserved`` entry
    (SCRUM-46).

    Args:
        viewer_id: The caller's user id, taken from their token.
        reference: The event request's ``EVR-…`` reference; case and surrounding
            spaces are ignored.
        viewer_role: The caller's role.
        session: Database session; defaults to ``db.session``.

    Returns:
        One :class:`HistoryEntryAsShown` per visible entry, oldest first.

    Raises:
        OrganiserWithoutOrganisationError: 403 — an organiser with no client
            organisation (ADR-0020).
        NotFoundError: 404 — no such event request, or for an organiser, none in
            their organisation.
    """
    sess = resolve_session(session)
    is_internal_viewer = viewer_role in INTERNAL_ROLES
    if is_internal_viewer:
        event_request = _event_request_for_staff(reference, sess)
    else:
        event_request = get_event_request_for_organiser(viewer_id, reference, session=sess)

    entries = _history_entries(event_request, sess)
    if not is_internal_viewer:
        entries = [entry for entry in entries if _shown_to_organiser(entry)]

    names = get_user_full_names(_user_ids_named_in(entries), session=sess)
    shown = []
    for entry in entries:
        shown.append(
            HistoryEntryAsShown(
                kind=entry.kind,
                occurred_at=entry.occurred_at,
                actor_name=_actor_name(entry, names),
                details=_details_as_shown(entry, names),
            )
        )
    return shown


# --------------------------------------------------------------------------
# SCRUM-24 — see the events my role is involved in
# --------------------------------------------------------------------------


def list_event_requests_with_equipment(*, session: Session | None = None) -> list[EventRequest]:
    """Every event with at least one equipment line, newest first (SCRUM-24 AC5).

    Whatever the event's status or date and whatever state its lines are in: this is
    everything Technical Support are involved in. SCRUM-38's list is the part still
    awaiting them (ADR-0026). An ``EXISTS`` on the lines, so an event with several lines
    is listed once.
    """
    return _list_event_requests_newest_first(
        EventRequest.equipment_lines.any(), resolve_session(session)
    )


def get_event_record_for_coordinator(
    coordinator_id: int | str, reference: str, *, session: Session | None = None
) -> EventRecord:
    """A request assigned to the coordinator, and its coordinator (SCRUM-24 AC9).

    The same sections as the organiser's record. Only a request assigned to the
    caller opens: the requests no coordinator has are the Event Coordinator Lead's
    queue (SCRUM-24 AC2, SCRUM-95, ADR-0034), not any coordinator's.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request's record: the request, and its coordinator's name and email.

    Raises:
        NotFoundError: 404 — no such request, or it isn't assigned to the caller.
    """
    sess = resolve_session(session)
    event_request = _event_request_by_reference(
        reference, sess, belongs_to=_assigned_to(coordinator_id)
    )
    return _event_record(event_request, sess)


# --------------------------------------------------------------------------
# SCRUM-68 — mark an event as completed after it has taken place
# --------------------------------------------------------------------------

NOT_CONFIRMED_MESSAGE = "Only a confirmed event can be marked completed."
PERIOD_INCOMPLETE_MESSAGE = "The event has no complete date and times yet."


class EventPeriodIncompleteError(AppError):
    """The event lacks a date or a time, so it has no period (409)."""

    status_code = 409
    error_code = "event_period_incomplete"


#: An event in one of these is over or will not happen, so no equipment can be
#: reserved for it (SCRUM-46).
RESERVATIONS_CLOSED_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.COMPLETED, EventRequestStatus.CANCELLED, EventRequestStatus.REJECTED}
)


@dataclass(frozen=True)
class EventEquipmentNeed:
    """When an event runs and how much of each equipment type it asks for (SCRUM-45).

    What the equipment module needs from an event, without handing it the models.
    """

    #: The event's id, which a reservation is linked to (SCRUM-46 AC4).
    event_id: int
    #: The event's start and end, timezone-aware UTC.
    starts_at: datetime
    ends_at: datetime
    #: Requested quantity by equipment type id; a type with no line is absent.
    requested: Mapping[int, int]
    #: Whether equipment may still be reserved for it: not once it is over or will
    #: not happen (SCRUM-46).
    accepts_reservations: bool


NOT_YET_ENDED_MESSAGE = "The event has not ended yet."


class RequestNotCompletableError(AppError):
    """The event can't be marked completed yet, or in its current state (409)."""

    status_code = 409
    error_code = "request_not_completable"


def _business_instant(day: date | None, at: time | None) -> datetime:
    """A date and wall-clock time in business time (ADR-0002) as a UTC-aware instant.

    Raises:
        EventPeriodIncompleteError: 409 — the date or the time is missing.
    """
    if day is None or at is None:
        raise EventPeriodIncompleteError(PERIOD_INCOMPLETE_MESSAGE)
    return as_utc(datetime.combine(day, at))


def _event_period(event_request: EventRequest) -> tuple[datetime, datetime]:
    """The event's start and end as UTC-aware instants (SCRUM-45 AC4).

    Raises:
        EventPeriodIncompleteError: 409 — a date or time is missing; the period is
            never guessed, for instance as the whole day.
    """
    starts_at = _business_instant(event_request.proposed_date, event_request.start_time)
    ends_at = _business_instant(event_request.end_date, event_request.end_time)
    return starts_at, ends_at


def _has_ended(event_request: EventRequest, now: datetime) -> bool:
    """Whether ``now`` is at or after the event's end (SCRUM-68 AC2, ADR-0027).

    The end is ``end_date`` + ``end_time``, a wall-clock time in business time.
    """
    # A draft may leave both empty, but a draft never reaches this check (ADR-0024).
    return now >= _business_instant(event_request.end_date, event_request.end_time)


def complete_event_request(
    coordinator_id: int | str,
    reference: str,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> EventRequest:
    """Mark a confirmed event completed once it has ended (SCRUM-68).

    Only the request's assigned coordinator may do it (ADR-0027). The checks run in
    the order edits and reassignment use: the reference, then ownership, then status,
    then the end time. The ``completed`` status and an ``event_completed`` history
    entry naming the caller are saved in one commit (AC5); the entry's
    ``occurred_at`` is the same ``now`` the end was checked against. No one is
    notified.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The request, now ``completed``.

    Raises:
        NotFoundError: 404 — no such request, a draft, or not the caller's.
        RequestNotCompletableError: 409 — the request isn't confirmed (AC3), or the
            event hasn't ended yet (AC2).
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)
    event_request = _event_request_assigned_to(coordinator_id, reference, sess)
    if event_request.status is not EventRequestStatus.CONFIRMED:
        raise RequestNotCompletableError(NOT_CONFIRMED_MESSAGE)
    if not _has_ended(event_request, now):
        raise RequestNotCompletableError(NOT_YET_ENDED_MESSAGE)

    event_request.status = EventRequestStatus.COMPLETED
    record_event_history(
        event_request,
        EventHistoryKind.EVENT_COMPLETED,
        actor_id=int(coordinator_id),
        session=sess,
        now=now,
    )
    sess.commit()
    return event_request


def get_event_equipment_need(
    reference: str, *, session: Session | None = None
) -> EventEquipmentNeed:
    """An event's period and the equipment it asks for, for the equipment module.

    For internal staff, so a draft is hidden as everywhere else (ADR-0024).

    Args:
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such request, or it is still a draft.
        EventPeriodIncompleteError: 409 — the event has no complete date and times.
    """
    event_request = _event_request_for_staff(reference, resolve_session(session))
    starts_at, ends_at = _event_period(event_request)
    requested = {}
    for line in event_request.equipment_lines:
        requested[line.equipment_type_id] = line.quantity
    return EventEquipmentNeed(
        event_id=event_request.id,
        starts_at=starts_at,
        ends_at=ends_at,
        requested=requested,
        accepts_reservations=event_request.status not in RESERVATIONS_CLOSED_STATUSES,
    )


def record_equipment_reserved(
    event_id: int,
    details: Mapping[str, Any],
    *,
    actor_id: int,
    session: Session | None = None,
) -> None:
    """Record in the event's history that equipment was reserved for it, uncommitted.

    The audit trail of a reservation (SCRUM-46, ADR-0037): the entry rides in the
    reservation's transaction, so it is saved with the reservation or not at all.
    Organisers never see it (:func:`_shown_to_organiser`).

    Args:
        event_id: The event's id, from :class:`EventEquipmentNeed`.
        details: ``equipment_type_id``, ``equipment_type_name``, ``quantity`` and
            ``reservation_id``.
        actor_id: Who reserved the equipment.
        session: Database session; defaults to ``db.session``.
    """
    sess = resolve_session(session)
    # By primary key, so the request the reservation was checked against comes
    # straight from the session rather than from a second query.
    event_request = sess.get(EventRequest, event_id)
    record_event_history(
        event_request,
        EventHistoryKind.EQUIPMENT_RESERVED,
        actor_id=actor_id,
        details=dict(details),
        session=sess,
    )


# --------------------------------------------------------------------------
# SCRUM-31 — review and decide a submitted request
# --------------------------------------------------------------------------

NOT_REVIEWABLE_MESSAGE = "Only a submitted event request can be moved to under review."

#: Statuses in which a request awaits its first decision: straight from submission,
#: or once its review has started (SCRUM-31 AC4, ADR-0028). One awaiting
#: clarification may be rejected, but not approved until the organiser answers
#: (SCRUM-32 AC3, ADR-0029).
AWAITING_DECISION_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.AWAITING_CLARIFICATION,
    }
)
#: Statuses in which a request has been decided, and may be decided again with a
#: reason until arrangements exist for it (SCRUM-31 AC6, AC7).
DECIDED_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.APPROVED, EventRequestStatus.REJECTED}
)
#: Statuses in which a request may be decided. A confirmed, completed or cancelled
#: event is past its decision (ADR-0028).
DECIDABLE_STATUSES: frozenset[EventRequestStatus] = AWAITING_DECISION_STATUSES | DECIDED_STATUSES
#: The status each outcome moves a request to (AC4).
STATUS_BY_OUTCOME: dict[DecisionOutcome, EventRequestStatus] = {
    DecisionOutcome.APPROVED: EventRequestStatus.APPROVED,
    DecisionOutcome.REJECTED: EventRequestStatus.REJECTED,
}
#: What the organiser is told for each outcome (AC10).
NOTIFICATION_KIND_BY_OUTCOME: dict[DecisionOutcome, NotificationKind] = {
    DecisionOutcome.APPROVED: NotificationKind.EVENT_REQUEST_APPROVED,
    DecisionOutcome.REJECTED: NotificationKind.EVENT_REQUEST_REJECTED,
}
NOT_DECIDABLE_MESSAGE = (
    "Only a submitted, under-review, awaiting-clarification, approved or rejected event "
    "request can be decided."
)
REASON_REQUIRED_MESSAGE = "A reason is required to reject a request or to change a decision."
DECISION_LOCKED_MESSAGE = (
    "The decision can't be changed once the event has an equipment request or a venue "
    "booking request."
)
#: SCRUM-32 AC3: an approval waits for the organiser's answer (ADR-0029).
CLARIFICATION_OUTSTANDING_MESSAGE = (
    "The request can't be approved until the organiser has answered the clarification request."
)


class RequestNotReviewableError(AppError):
    """The request isn't submitted, so it can't be moved to under review (409)."""

    status_code = 409
    error_code = "request_not_reviewable"


class RequestNotDecidableError(AppError):
    """The request's status doesn't allow a decision (409)."""

    status_code = 409
    error_code = "request_not_decidable"


class DecisionLockedError(AppError):
    """Arrangements have been made for the event, so its decision can't change (409)."""

    status_code = 409
    error_code = "decision_locked"


class ClarificationOutstandingError(AppError):
    """The organiser hasn't answered the clarification request yet (409, SCRUM-32)."""

    status_code = 409
    error_code = "clarification_outstanding"


def start_event_request_review(
    coordinator_id: int | str, reference: str, *, session: Session | None = None
) -> EventRequest:
    """Move a submitted request to under review (SCRUM-31 AC3).

    Only the request's assigned coordinator may (AC5), and only while it is
    submitted (ADR-0028). A ``review_started`` history entry, naming the coordinator,
    is saved in the same commit. Nobody is notified.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, now ``under_review``.

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own; a draft is
            never found (ADR-0024).
        RequestNotReviewableError: 409 — the request isn't submitted.
    """
    sess = resolve_session(session)
    event_request = _event_request_assigned_to(coordinator_id, reference, sess)
    if event_request.status is not EventRequestStatus.SUBMITTED:
        raise RequestNotReviewableError(NOT_REVIEWABLE_MESSAGE)

    event_request.status = EventRequestStatus.UNDER_REVIEW
    record_event_history(
        event_request,
        EventHistoryKind.REVIEW_STARTED,
        actor_id=int(coordinator_id),
        session=sess,
    )
    sess.commit()
    return event_request


def _has_arrangements(event_request: EventRequest) -> bool:
    """Whether arrangements have been made for the event (SCRUM-31 AC7, ADR-0028)."""
    # TODO: SCRUM-42 also counts the event's venue booking requests here.
    return len(event_request.equipment_lines) > 0


def _event_request_decidable_by(
    coordinator_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The coordinator's request, if it may be decided now (AC5, AC7, ADR-0028).

    A decided request may be decided again only until arrangements exist for it; its
    first decision is never blocked.

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own; a draft is
            never found (ADR-0024).
        RequestNotDecidableError: 409 — the request's status doesn't allow a decision.
        DecisionLockedError: 409 — it is decided and has arrangements.
    """
    event_request = _event_request_assigned_to(coordinator_id, reference, session)
    if event_request.status not in DECIDABLE_STATUSES:
        raise RequestNotDecidableError(NOT_DECIDABLE_MESSAGE)
    if event_request.status in DECIDED_STATUSES and _has_arrangements(event_request):
        raise DecisionLockedError(DECISION_LOCKED_MESSAGE)
    return event_request


def _check_reason_given(decision: Mapping[str, Any], event_request: EventRequest) -> None:
    """Refuse a rejection, or a change of decision, without a reason (AC4, AC6).

    Only a first approval may leave the reason out. ``event_request`` is still in the
    status it had before this decision.

    Raises:
        ValidationError: 400 — no reason where one is required.
    """
    if decision["reason"] is not None:
        return
    is_rejection = decision["outcome"] is DecisionOutcome.REJECTED
    is_new_decision = event_request.status in DECIDED_STATUSES
    if is_rejection or is_new_decision:
        raise ValidationError("Invalid request.", details={"reason": [REASON_REQUIRED_MESSAGE]})


def _apply_decision(
    coordinator_id: int | str,
    event_request: EventRequest,
    decision: Mapping[str, Any],
    session: Session,
) -> None:
    """Move the request to the outcome's status and record the decision (AC4, AC8).

    The ``decision_recorded`` entry names the coordinator and keeps the outcome and
    reason, so every decision stays in the history. Nothing is committed here.
    """
    outcome = decision["outcome"]
    event_request.status = STATUS_BY_OUTCOME[outcome]
    record_event_history(
        event_request,
        EventHistoryKind.DECISION_RECORDED,
        actor_id=int(coordinator_id),
        details={"outcome": outcome.value, "reason": decision["reason"]},
        session=session,
    )


def _notify_organiser_of_decision(
    event_request: EventRequest, decision: Mapping[str, Any], session: Session
) -> None:
    """Tell the organiser who submitted the request of the decision and its reason.

    Only the submitting organiser, not their whole organisation (AC10, ADR-0028); the
    reason goes in the notification's ``detail``.
    """
    _raise_notifications(
        [event_request.organiser_id],
        event_request,
        NOTIFICATION_KIND_BY_OUTCOME[decision["outcome"]],
        session,
        detail=decision["reason"],
    )


def _check_no_clarification_outstanding(
    decision: Mapping[str, Any], event_request: EventRequest
) -> None:
    """Refuse an approval while the organiser's answer is outstanding (SCRUM-32 AC3).

    A rejection is still allowed (ADR-0029).

    Raises:
        ClarificationOutstandingError: 409 — an approval of a request awaiting
            clarification.
    """
    if decision["outcome"] is not DecisionOutcome.APPROVED:
        return
    if event_request.status is EventRequestStatus.AWAITING_CLARIFICATION:
        raise ClarificationOutstandingError(CLARIFICATION_OUTSTANDING_MESSAGE)


def decide_event_request(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventRequest:
    """Approve or reject a request (SCRUM-31 AC1, AC4).

    Only the request's assigned coordinator may (AC5), while it is submitted or under
    review (ADR-0028). Approving moves it to ``approved``; rejecting moves it to
    ``rejected`` and needs a reason. An approved or rejected request may be decided
    again, with a reason, until the event has an equipment request (AC6, AC7). The
    status change and a ``decision_recorded`` history entry, with the outcome, the
    reason and the coordinator, are saved in one commit, so every decision stays in
    the history and the latest is current (AC8). Once saved, the organiser who
    submitted the request is notified, with the reason (AC10); a failure there is
    logged, not raised (ADR-0015). A request awaiting clarification may be rejected
    but not approved (SCRUM-32 AC3, ADR-0029). The checks run in this order: the
    reference, the coordinator, the status, the lock, the payload, then the
    outstanding clarification.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``outcome`` and an optional ``reason``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, in its new status.

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own; a draft is
            never found (ADR-0024).
        RequestNotDecidableError: 409 — the request is confirmed, completed or
            cancelled.
        DecisionLockedError: 409 — a new decision once the event has an equipment
            request.
        ValidationError: 400 — payload invalid, or no reason for a rejection or a new
            decision.
        ClarificationOutstandingError: 409 — an approval while a clarification
            request is outstanding.
    """
    sess = resolve_session(session)
    event_request = _event_request_decidable_by(coordinator_id, reference, sess)
    decision = load_or_raise(DecideEventRequestSchema(), payload)
    _check_reason_given(decision, event_request)
    _check_no_clarification_outstanding(decision, event_request)
    _apply_decision(coordinator_id, event_request, decision, sess)
    sess.commit()
    _notify_organiser_of_decision(event_request, decision, sess)
    return event_request


# --------------------------------------------------------------------------
# SCRUM-32 — ask the organiser for clarification
# --------------------------------------------------------------------------

CLARIFICATION_NOT_ALLOWED_MESSAGE = (
    "Clarification can only be requested while the event request is under review."
)


class ClarificationNotAllowedError(AppError):
    """The request isn't under review, so no clarification can be asked (409)."""

    status_code = 409
    error_code = "clarification_not_allowed"


def _event_request_under_review_by(
    coordinator_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The coordinator's request, if it is under review (SCRUM-32 AC1, ADR-0029).

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own; a draft is
            never found (ADR-0024).
        ClarificationNotAllowedError: 409 — the request isn't under review.
    """
    event_request = _event_request_assigned_to(coordinator_id, reference, session)
    if event_request.status is not EventRequestStatus.UNDER_REVIEW:
        raise ClarificationNotAllowedError(CLARIFICATION_NOT_ALLOWED_MESSAGE)
    return event_request


def _notify_organiser_of_question(
    event_request: EventRequest, message: str, session: Session
) -> None:
    """Tell the organiser who submitted the request of the question (SCRUM-32 AC1).

    Only the submitting organiser, not their whole organisation, as with a decision
    (ADR-0029); the question goes in the notification's ``detail``.
    """
    _raise_notifications(
        [event_request.organiser_id],
        event_request,
        NotificationKind.CLARIFICATION_REQUESTED,
        session,
        detail=message,
    )


def request_clarification(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventRequest:
    """Ask the organiser a question about a request under review (SCRUM-32 AC1, AC4).

    Only the request's assigned coordinator may, and only while it is under review,
    so a second question can't be asked while one is outstanding (ADR-0029). The
    request goes back to the organiser as ``awaiting_clarification``, and a
    ``clarification_requested`` history entry holding the question and naming the
    coordinator is saved in the same commit. The submitting organiser is then told,
    with the question as the notification's detail. The checks run in this order: the
    reference, the coordinator, the status, then the payload.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``{"message": ...}``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, now ``awaiting_clarification``.

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own; a draft is
            never found (ADR-0024).
        ClarificationNotAllowedError: 409 — the request isn't under review.
        ValidationError: 400 — payload invalid.
    """
    sess = resolve_session(session)
    event_request = _event_request_under_review_by(coordinator_id, reference, sess)
    question = load_or_raise(RequestClarificationSchema(), payload)

    event_request.status = EventRequestStatus.AWAITING_CLARIFICATION
    record_event_history(
        event_request,
        EventHistoryKind.CLARIFICATION_REQUESTED,
        actor_id=int(coordinator_id),
        details={"message": question["message"]},
        session=sess,
    )
    sess.commit()
    _notify_organiser_of_question(event_request, question["message"], sess)
    return event_request


NOT_AWAITING_CLARIFICATION_MESSAGE = (
    "Only an event request awaiting clarification can be answered and resubmitted."
)


class RequestNotAwaitingClarificationError(AppError):
    """The request isn't awaiting clarification, so it can't be resubmitted (409)."""

    status_code = 409
    error_code = "request_not_awaiting_clarification"


def _event_request_awaiting_clarification(
    organiser_id: int | str, reference: str, session: Session
) -> EventRequest:
    """The organiser's organisation's request, if it awaits clarification (ADR-0029).

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no organisation.
        NotFoundError: 404 — no such request in the organiser's organisation.
        RequestNotAwaitingClarificationError: 409 — the request isn't awaiting
            clarification.
    """
    event_request = get_event_request_for_organiser(organiser_id, reference, session=session)
    if event_request.status is not EventRequestStatus.AWAITING_CLARIFICATION:
        raise RequestNotAwaitingClarificationError(NOT_AWAITING_CLARIFICATION_MESSAGE)
    return event_request


def _notify_coordinator_of_answer(
    event_request: EventRequest, response: str, session: Session
) -> None:
    """Tell the request's current coordinator of the answer (SCRUM-32 AC2).

    Whoever holds the request now, which may not be who asked (ADR-0029); the answer
    goes in the notification's ``detail``. With no coordinator to tell, the answer is
    still saved, and that is logged so someone can pick it up.
    """
    if event_request.coordinator_id is None:
        _warn_unassigned(event_request)
        return
    _raise_notifications(
        [event_request.coordinator_id],
        event_request,
        NotificationKind.CLARIFICATION_ANSWERED,
        session,
        detail=response,
    )


def resubmit_event_request(
    organiser_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    today: date | None = None,
) -> EventRequest:
    """Answer the coordinator's question, amend the request and resubmit (SCRUM-32 AC2).

    Any organiser of the request's client organisation may (ADR-0029), while it awaits
    clarification. The body holds a required ``response`` and any amendments, each
    checked as on submission. Each amended field is written to the history as a
    ``field_changed`` entry by the organiser, then the answer as a
    ``clarification_answered`` entry holding the response, all at one instant; the
    request goes back to ``under_review`` in the same commit (AC2, AC4). The current
    coordinator is then told, with the answer as the notification's detail, and an
    amendment that could affect equipment already requested asks Technical Support
    to reassess it, as an edit does (ADR-0025). The checks run in this order: the
    organiser's organisation, the reference, the status, then the payload.

    Args:
        organiser_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``response`` and any fields to amend.
        session: Database session; defaults to ``db.session``.
        today: Reference date for the "not in the past" rule; defaults to today in
            the business timezone.

    Returns:
        The request, back ``under_review``.

    Raises:
        OrganiserWithoutOrganisationError: 403 — the organiser has no organisation.
        NotFoundError: 404 — no such request in the organiser's organisation.
        RequestNotAwaitingClarificationError: 409 — the request isn't awaiting
            clarification.
        ValidationError: 400 — payload invalid (details per field).
    """
    sess = resolve_session(session)
    event_request = _event_request_awaiting_clarification(organiser_id, reference, sess)
    schema = ResubmitEventRequestSchema(event_request, today=today)
    data = load_or_raise(schema, payload, partial=AMENDABLE_FIELDS)
    response = data.pop("response")

    answered_at = datetime.now(timezone.utc)
    changes = _record_field_changes(
        event_request, int(organiser_id), data, session=sess, now=answered_at
    )
    event_request.status = EventRequestStatus.UNDER_REVIEW
    record_event_history(
        event_request,
        EventHistoryKind.CLARIFICATION_ANSWERED,
        actor_id=int(organiser_id),
        details={"response": response},
        session=sess,
        now=answered_at,
    )
    sess.commit()
    _notify_coordinator_of_answer(event_request, response, sess)
    _reassess_arrangements(event_request, changes, sess)
    return event_request
