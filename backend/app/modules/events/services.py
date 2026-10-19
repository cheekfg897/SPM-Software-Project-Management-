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
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Any, Literal

from marshmallow import Schema
from sqlalchemy import Row, and_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.common.clock import as_utc, local_today, to_business_time
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
    SafetyOutcome,
)
from app.modules.events.schemas import (
    AMENDABLE_FIELDS,
    AssignCoordinatorSchema,
    DecideEventRequestSchema,
    EditEquipmentLineSchema,
    EditEventRequestSchema,
    EventRequestSchema,
    ReassignCoordinatorSchema,
    RecordEquipmentOutcomeSchema,
    RecordSafetyOutcomeSchema,
    RejectEventSchema,
    RequestClarificationSchema,
    ResubmitEventRequestSchema,
    SaveDraftSchema,
    SubmitEventRequestSchema,
    UpdateRegistrationSettingsSchema,
)
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users

if TYPE_CHECKING:
    # Type only: the venue module imports this one, so it is imported where it is used.
    from app.modules.venue.services import ArrangedVenue

logger = logging.getLogger("connectsphere.events")

# Reference format (ADR-0004): "EVR-" + 8 characters with no look-alikes (0 O 1 I L).
REFERENCE_PREFIX = "EVR-"
REFERENCE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
REFERENCE_LENGTH = 8
MAX_REFERENCE_ATTEMPTS = 3

#: One answer for a reference that doesn't exist and one the caller may not see, so a
#: reference can't be probed (ADR-0012).
EVENT_REQUEST_NOT_FOUND_MESSAGE = "Event request not found."


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
class ActiveRequest:
    """One active event with the name of its coordinator, for the Lead (SCRUM-96 AC1).

    No user id: the coordinator is shown by name. ``coordinator_name`` is ``None``
    while a submitted request waits for the Lead to assign it.
    """

    event_request: EventRequest
    coordinator_name: str | None


@dataclass(frozen=True)
class CoordinatorWorkload:
    """A coordinator and their active events, for the Lead (SCRUM-96 AC2)."""

    coordinator_id: int
    coordinator_name: str
    assigned: list[EventRequest]


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
class EquipmentLineAsShown:
    """An equipment line with its review outcome, as staff see it (SCRUM-48 AC4).

    No user ids: the reviewing staff member is shown by name. The outcome fields stay
    ``None`` until an outcome is recorded.
    """

    id: int
    equipment_type_id: int
    quantity: int
    notes: str | None
    status: EquipmentLineStatus
    provided_quantity: int | None
    #: How many fewer units are provided than requested.
    shortfall: int | None
    outcome_note: str | None
    #: The reviewer's full name, or ``None`` if they no longer exist.
    reviewed_by: str | None
    reviewed_at: datetime | None


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


#: What a changed field's value is stored as in the history's JSON ``details``
#: (ADR-0025): a date or time becomes its ISO string, everything else keeps its
#: native JSON type.
HistoryValue = str | int | None


@dataclass(frozen=True)
class FieldChange:
    """One field an edit changed, as the history and the API show it (ADR-0025)."""

    field: str
    previous_value: HistoryValue
    new_value: HistoryValue
    significant: bool


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


def _mark_submitted(event_request: EventRequest) -> None:
    """Move ``event_request`` to ``submitted`` with no coordinator, uncommitted.

    Nobody is assigned on submission: the request waits in the Event Coordinator
    Lead's queue until the Lead gives it to a coordinator, which is where its
    ``coordinator_assigned`` history entry is written (SCRUM-95 AC1, AC3, ADR-0036,
    superseding SCRUM-30's assignment on submission). Shared by submitting a new
    request and submitting a draft (SCRUM-20), so both reach ``submitted`` the same
    way. Does not commit: the caller decides when.
    """
    event_request.status = EventRequestStatus.SUBMITTED
    event_request.coordinator_id = None


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


REASSIGNED_AWAY_DETAIL = (
    "This event has been reassigned to another Event Coordinator and is no longer yours."
)


def _notify_about_assignment(
    event_request: EventRequest,
    coordinator_id: int,
    session: Session,
    *,
    previous_id: int | None = None,
) -> None:
    """Tell the new coordinator, the organiser and any previous coordinator.

    The coordinator hears the event is theirs (SCRUM-30 AC4, SCRUM-87 AC4, SCRUM-39
    AC4), and the organiser who submitted it hears a coordinator has been assigned
    (SCRUM-39 AC1, ADR-0030). On a reassignment the coordinator who held the request
    hears it has moved on (SCRUM-96 AC5, ADR-0041): the ``request_assigned`` kind's
    default message is the organiser's, so their notice carries its own ``detail``
    saying the event is no longer theirs. A first assignment has no ``previous_id``.
    They are separate writes, so losing one notice doesn't lose the others (ADR-0015).
    """
    _raise_notifications(
        [coordinator_id], event_request, NotificationKind.COORDINATOR_ASSIGNED, session
    )
    _raise_notifications(
        [event_request.organiser_id], event_request, NotificationKind.REQUEST_ASSIGNED, session
    )
    if previous_id is not None:
        _raise_notifications(
            [previous_id],
            event_request,
            NotificationKind.REQUEST_ASSIGNED,
            session,
            detail=REASSIGNED_AWAY_DETAIL,
        )


def _notify_leads_of_queued_request(event_request: EventRequest, session: Session) -> None:
    """Tell every Event Coordinator Lead that ``event_request`` is waiting for one.

    Called once a submission is saved, for a new request and a submitted draft alike
    (SCRUM-95 AC4, ADR-0036). Each Lead hears it once, as a single write. This notice
    is also the only thing that says a request is unassigned: submission logs no
    warning for it, as it is the normal way for every request to start.
    """
    lead_ids = list_user_ids_with_role(Role.EVENT_COORDINATOR_LEAD, session=session)
    _raise_notifications(lead_ids, event_request, NotificationKind.REQUEST_QUEUED_FOR_LEAD, session)


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
    organisation (SCRUM-66 AC4). Nobody is assigned to it: it waits unassigned
    for the Event Coordinator Lead to give it to a coordinator, which supersedes
    SCRUM-30's least-loaded assignment and SCRUM-28 AC3's notice to the
    coordinators (SCRUM-95 AC1, ADR-0036). Every Event Coordinator Lead is then
    notified that it is waiting (SCRUM-95 AC4). If the reference is already taken,
    the save is rolled back and retried with a new one, up to
    :data:`MAX_REFERENCE_ATTEMPTS` times.

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

    def submitted_under(reference: str) -> EventRequest:
        """Build a request under ``reference``, then submit it unassigned."""
        event_request = EventRequest(
            organiser_id=int(organiser_id),
            organisation_id=organisation_id,
            reference=reference,
            **data,
        )
        sess.add(event_request)
        _mark_submitted(event_request)
        return event_request

    event_request = _save_under_new_reference(submitted_under, sess, reference_factory)
    _notify_leads_of_queued_request(event_request, sess)
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
    submission, it is saved with nobody assigned to it and waits for the Event
    Coordinator Lead to give it to a coordinator (SCRUM-95 AC1, ADR-0036), and every
    Lead is notified that it is waiting (SCRUM-95 AC4).

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
    _mark_submitted(draft)
    sess.commit()
    _notify_leads_of_queued_request(draft, sess)
    return draft


# --------------------------------------------------------------------------
# SCRUM-98 — whether an event's safety check is approved, and withdrawing it
# --------------------------------------------------------------------------

#: The history kinds that open, settle or unsettle a safety check. The newest of them
#: says whether the event's current check is approved (SCRUM-98, ADR-0047); a change
#: that needs a new check withdraws an approval (ADR-0053, ADR-0087).
SAFETY_CHECK_KINDS = (
    EventHistoryKind.SAFETY_REVIEW_REQUESTED,
    EventHistoryKind.SAFETY_OUTCOME_RECORDED,
    EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN,
)


def has_safety_approval(event_id: int, *, session: Session | None = None) -> bool:
    """Whether the Safety Officer has approved the event's current safety check.

    SCRUM-98 AC5. For SCRUM-49, which confirms only an approved event, and SCRUM-84/85,
    which prepare only one. The newest entry that opens or settles a check decides, so
    an approval counts until the event is sent to Safety Review again (ADR-0047).

    Args:
        event_id: The event request's id.
        session: Database session; defaults to ``db.session``.
    """
    stmt = (
        select(EventHistoryEntry)
        .where(
            EventHistoryEntry.event_request_id == event_id,
            EventHistoryEntry.kind.in_(SAFETY_CHECK_KINDS),
        )
        .order_by(EventHistoryEntry.occurred_at.desc(), EventHistoryEntry.id.desc())
        .limit(1)
    )
    latest = resolve_session(session).scalar(stmt)
    if latest is None or latest.kind is not EventHistoryKind.SAFETY_OUTCOME_RECORDED:
        return False
    return latest.details["outcome"] == SafetyOutcome.APPROVED.value


#: Statuses an event leaves when its safety approval is withdrawn. It goes back to
#: Approved, the only status it can be sent to Safety Review from, to pass a new
#: check (ADR-0053, ADR-0087).
RETURNED_TO_PLANNING_ON_WITHDRAWAL: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.SAFETY_REVIEW, EventRequestStatus.CONFIRMED}
)


def withdraw_safety_approval(
    event_id: int,
    *,
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> None:
    """Withdraw the event's safety approval, if it has one, without committing.

    For a change after which the event must pass a new safety check before it can be
    confirmed or prepared: a replacement venue (SCRUM-92 AC10), a significant change
    (SCRUM-33 AC7, SCRUM-37 AC4), equipment out of service (SCRUM-47 AC5) or a revised
    equipment outcome (SCRUM-48 AC7). The withdrawal is a history entry, which
    ``has_safety_approval`` then reads as no approval. An event in Safety Review or
    Confirmed goes back to Approved, so the coordinator can send it again (ADR-0087).
    An event with no approval is left alone. The entry rides in the caller's
    transaction (ADR-0018).

    Args:
        event_id: The event request's id.
        actor_id: The user whose change withdrew the approval.
        details: What the change was, for the history entry.
        session: Database session; defaults to ``db.session``.
    """
    sess = resolve_session(session)
    if not has_safety_approval(event_id, session=sess):
        return
    event_request = sess.get(EventRequest, event_id)
    if event_request.status in RETURNED_TO_PLANNING_ON_WITHDRAWAL:
        event_request.status = EventRequestStatus.APPROVED
    record_event_history(
        event_request,
        EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN,
        actor_id=actor_id,
        details=details,
        session=sess,
    )


# --------------------------------------------------------------------------
# SCRUM-37 — record what equipment an event needs
# --------------------------------------------------------------------------

#: Statuses in which an event's equipment may change: any time before the event is
#: Confirmed (SCRUM-37 AC2, ADR-0092). That includes awaiting clarification: the
#: organiser amends the request then, but never its equipment lines, which stay the
#: coordinator's. A Confirmed event's lines change through a change request
#: (SCRUM-56, SCRUM-57), and a completed, cancelled or rejected event is over.
EQUIPMENT_EDITABLE_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.AWAITING_CLARIFICATION,
        EventRequestStatus.APPROVED,
        EventRequestStatus.SAFETY_REVIEW,
    }
)
EQUIPMENT_NOT_EDITABLE_MESSAGE = (
    "Equipment can only be changed before the event is confirmed, and not once it is "
    "rejected or cancelled."
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
    #: The Event Coordinator assigned to the event now, whom the venue module tells
    #: about a hold (SCRUM-75 AC9, SCRUM-94 AC3); not always who raised the request.
    coordinator_id: int | None


def _for_booking(event_request: EventRequest) -> EventForBooking:
    """The event as the venue module needs it; the one place the two are mapped."""
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
        coordinator_id=event_request.coordinator_id,
    )


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
    return _for_booking(event_request)


def get_events_for_booking(
    event_ids: Collection[int], *, session: Session | None = None
) -> dict[int, EventForBooking]:
    """The events behind a set of booking requests, by id (SCRUM-43 AC1, AC2).

    Venue Staff see requests for events they coordinate nothing of, so there is no
    coordinator to check: whoever may read the queue may read the events on it. An id
    with no event is left out rather than raising, so one deleted event cannot hide
    the whole queue.
    """
    requests = resolve_session(session).scalars(
        select(EventRequest).where(EventRequest.id.in_(event_ids))
    )
    return {event_request.id: _for_booking(event_request) for event_request in requests}


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


#: Where a replacement venue may be requested from (SCRUM-92 AC6): the planning stage,
#: and Safety Review, which a flag leaves an event in because only a Confirmed event
#: goes back to Approved (AC3, ADR-0053).
REPLACEMENT_BOOKING_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW}
)


def get_event_for_replacement_booking(
    reference: str, coordinator_id: int | str, *, session: Session | None = None
) -> EventForBooking:
    """The coordinator's own event, if it may raise a replacement venue (SCRUM-92 AC6).

    Raises:
        NotFoundError: 404 — no such event, or it isn't assigned to this coordinator.
        ConflictError: 409 — the event is neither approved nor in Safety Review; the
            message names its status.
    """
    event = get_event_for_coordinator(reference, coordinator_id, session=session)
    if event.status not in REPLACEMENT_BOOKING_STATUSES:
        raise ConflictError(
            "Only an approved event or one in Safety Review can replace a venue;"
            f" this one is {event.status.value}."
        )
    return event


def record_alternative_venue_needed(
    event_id: int, *, details: dict[str, Any], session: Session | None = None
) -> None:
    """Record that one of the event's venues became unavailable, without committing.

    SCRUM-92 AC3: a Confirmed event goes back to Approved, the planning stage, for the
    change to be reviewed; it is not cancelled, and an event at any other status keeps
    it. The history entry says which, beside the venue module's ``details``. The system
    did it, so the entry has no actor. It rides in the caller's transaction, with the
    flag it records (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    returned_to_planning = event_request.status is EventRequestStatus.CONFIRMED
    if returned_to_planning:
        event_request.status = EventRequestStatus.APPROVED
    record_event_history(
        event_request,
        EventHistoryKind.ALTERNATIVE_VENUE_NEEDED,
        actor_id=None,
        details={**details, "returned_to_planning": returned_to_planning},
        session=session,
    )


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


#: Which history entry each venue booking decision writes (SCRUM-43 AC3). The venue
#: module may not import ``EventHistoryKind``, so it names its outcome and this maps it.
_VENUE_BOOKING_DECISION_KINDS = {
    "approved": EventHistoryKind.VENUE_BOOKING_APPROVED,
    "rejected": EventHistoryKind.VENUE_BOOKING_REJECTED,
}


def record_venue_booking_decided(
    event_id: int,
    *,
    outcome: Literal["approved", "rejected"],
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for a decided request, without committing (SCRUM-43).

    The entry rides in the caller's transaction, so it is saved with the decision it
    records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        _VENUE_BOOKING_DECISION_KINDS[outcome],
        actor_id=actor_id,
        details=details,
        session=session,
    )


def record_venue_arrangement_withdrawn(
    event_id: int,
    *,
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for a withdrawn arrangement, without committing (SCRUM-93).

    The entry rides in the caller's transaction, so it is saved with the withdrawal it
    records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN,
        actor_id=actor_id,
        details=details,
        session=session,
    )


def record_venue_arrangement_changed(
    event_id: int,
    *,
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for a changed arrangement, without committing (SCRUM-93).

    The entry rides in the caller's transaction, so it is saved with the change it
    records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        EventHistoryKind.VENUE_ARRANGEMENT_CHANGED,
        actor_id=actor_id,
        details=details,
        session=session,
    )


def record_venue_preparation_updated(
    event_id: int,
    *,
    actor_id: int,
    details: dict[str, Any],
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for venue preparation, without committing (SCRUM-84).

    The entry rides in the caller's transaction, so it is saved with the update it
    records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        EventHistoryKind.VENUE_PREPARATION_UPDATED,
        actor_id=actor_id,
        details=details,
        session=session,
    )


def record_venue_hold_expired(
    event_id: int,
    *,
    details: dict[str, Any],
    now: datetime,
    session: Session | None = None,
) -> EventHistoryEntry:
    """Add the history entry for a hold that ran out, without committing (SCRUM-94 AC6).

    The system expires a hold, so the entry has no actor. It rides in the caller's
    transaction, so it is saved with the expiry it records or not at all (ADR-0018).
    """
    event_request = resolve_session(session).get(EventRequest, event_id)
    return record_event_history(
        event_request,
        EventHistoryKind.VENUE_HOLD_EXPIRED,
        actor_id=None,
        details=details,
        session=session,
        now=now,
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
    # The schema has enforced every other rule, the type has been checked and a new
    # quantity clears any recorded outcome beforehand, so the only integrity
    # error left here is the unique (event, equipment type) pair.
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(DUPLICATE_LINE_MESSAGE) from exc


EQUIPMENT_LINE_NOT_FOUND_MESSAGE = "Equipment line not found."


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
        raise NotFoundError(EQUIPMENT_LINE_NOT_FOUND_MESSAGE)
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


#: The line fields whose change alters what Technical Support place for the event,
#: unlike its technical notes (SCRUM-37 AC4).
LINE_FIELDS_THAT_CHANGE_THE_EQUIPMENT = ("equipment_type_id", "quantity")


def _changes_the_equipment(line: EventEquipmentLine, data: Mapping[str, Any]) -> bool:
    """Whether ``data`` asks the line for a different equipment type or quantity."""
    for field in LINE_FIELDS_THAT_CHANGE_THE_EQUIPMENT:
        if field in data and data[field] != getattr(line, field):
            return True
    return False


def _withdraw_safety_approval_for_line(
    coordinator_id: int | str, line: EventEquipmentLine, change: str, session: Session
) -> None:
    """Withdraw the event's safety approval for a line ``change`` (SCRUM-37 AC4).

    ``change`` is ``added``, ``changed`` or ``removed``; the entry names the line's
    equipment type as it was before the change. Called before the line is written,
    so the approval lookup never flushes a line the commit may still refuse.
    """
    withdraw_safety_approval(
        line.event_request_id,
        actor_id=int(coordinator_id),
        details={"equipment_line_change": change, "equipment_type_id": line.equipment_type_id},
        session=session,
    )


#: The "field" a line change is recorded under in the event's history (SCRUM-37 AC4,
#: ADR-0092).
EQUIPMENT_LINE_FIELD = "equipment_line"


def _line_as_history_value(equipment_type_id: int, quantity: int, session: Session) -> str:
    """A line as the event's history shows it, e.g. ``"Projector, quantity 2"``.

    The type's name is copied in, so the entry reads the same if the catalogue's name
    changes later, like an outcome's entry (ADR-0092).
    """
    equipment_type = equipment_services.get_equipment_type(equipment_type_id, session=session)
    return f"{equipment_type.name}, quantity {quantity}"


def _record_line_change(
    coordinator_id: int | str,
    event_request: EventRequest,
    *,
    previous_value: str | None,
    new_value: str | None,
    session: Session,
) -> None:
    """Write a line change to the event's history as a significant change (AC4).

    The same ``field_changed`` entry an edit to the event's own fields writes
    (SCRUM-33, ADR-0025), on :data:`EQUIPMENT_LINE_FIELD`: ``previous_value`` is
    ``None`` for an added line and ``new_value`` is ``None`` for a removed one. It
    rides in the caller's transaction.
    """
    change = FieldChange(
        field=EQUIPMENT_LINE_FIELD,
        previous_value=previous_value,
        new_value=new_value,
        significant=True,
    )
    record_event_history(
        event_request,
        EventHistoryKind.FIELD_CHANGED,
        actor_id=int(coordinator_id),
        details=asdict(change),
        session=session,
    )


def _clear_outcome(line: EventEquipmentLine) -> None:
    """Take away the line's outcome, so it awaits Technical Support's review again.

    SCRUM-37 AC4. The outcome stays on record in its ``equipment_outcome_recorded``
    history entry (SCRUM-48), and the line is back on Technical Support's list
    (SCRUM-38 AC5).
    """
    line.status = EquipmentLineStatus.REQUESTED
    line.provided_quantity = None
    line.outcome_note = None
    line.reviewed_by = None
    line.reviewed_at = None


def _reopen_changed_line(
    coordinator_id: int | str,
    event_request: EventRequest,
    line: EventEquipmentLine,
    data: Mapping[str, Any],
    session: Session,
) -> None:
    """Treat a new equipment type or quantity as a significant change (SCRUM-37 AC4).

    Called before ``data`` is applied to the line, and without committing: withdraws
    any safety approval, records the line before and after the change, releases the
    old type's reservations if the line moves to another type (ADR-0092), and clears
    its outcome.
    """
    _withdraw_safety_approval_for_line(coordinator_id, line, "changed", session)
    new_equipment_type_id = data.get("equipment_type_id", line.equipment_type_id)
    new_quantity = data.get("quantity", line.quantity)
    _record_line_change(
        coordinator_id,
        event_request,
        previous_value=_line_as_history_value(line.equipment_type_id, line.quantity, session),
        new_value=_line_as_history_value(new_equipment_type_id, new_quantity, session),
        session=session,
    )
    if new_equipment_type_id != line.equipment_type_id:
        equipment_services.release_reservations(
            line.event_request_id, line.equipment_type_id, session=session
        )
    _clear_outcome(line)


def _event_request_for_equipment_viewer(
    viewer_id: int | str, reference: str, viewer_role: Role, session: Session
) -> EventRequest:
    """The request, if the viewer may see its equipment (ADR-0019, ADR-0037).

    Technical Support Staff may see any event's; a coordinator only an event assigned
    to them.

    Raises:
        NotFoundError: 404 — no such request, a draft, or for a coordinator, not one
            of their own.
    """
    if viewer_role is Role.TECHNICAL_SUPPORT_STAFF:
        return _event_request_for_staff(reference, session)
    return _event_request_assigned_to(viewer_id, reference, session)


def add_equipment_line(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventEquipmentLine:
    """Record one kind of equipment an event needs (SCRUM-37 AC1, AC3).

    Only the event's assigned coordinator may (ADR-0019). The line is saved with
    status ``requested``, as a significant change in the event's history and with any
    safety approval withdrawn (AC4); once it is saved, every Technical Support Staff
    member is notified that equipment was requested (AC6).

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
    _withdraw_safety_approval_for_line(coordinator_id, line, "added", sess)
    _record_line_change(
        coordinator_id,
        event_request,
        previous_value=None,
        new_value=_line_as_history_value(line.equipment_type_id, line.quantity, sess),
        session=sess,
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
    event_request = _event_request_for_equipment_viewer(
        viewer_id, reference, viewer_role, resolve_session(session)
    )
    return event_request, list(event_request.equipment_lines)


def equipment_lines_as_shown(
    lines: Iterable[EventEquipmentLine], *, session: Session | None = None
) -> list[EquipmentLineAsShown]:
    """The lines with their review outcome and the reviewers' names (SCRUM-48 AC4).

    Names are looked up now, in one query, so a removed reviewer shows as ``None``.
    """
    lines = list(lines)
    reviewer_ids = {line.reviewed_by for line in lines if line.reviewed_by is not None}
    names = get_user_full_names(reviewer_ids, session=session)

    shown: list[EquipmentLineAsShown] = []
    for line in lines:
        shortfall = None
        if line.provided_quantity is not None:
            shortfall = line.quantity - line.provided_quantity
        shown.append(
            EquipmentLineAsShown(
                id=line.id,
                equipment_type_id=line.equipment_type_id,
                quantity=line.quantity,
                notes=line.notes,
                status=line.status,
                provided_quantity=line.provided_quantity,
                shortfall=shortfall,
                outcome_note=line.outcome_note,
                reviewed_by=names.get(line.reviewed_by),
                reviewed_at=line.reviewed_at,
            )
        )
    return shown


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
    change (ADR-0019). A new equipment type or quantity is a significant change (AC4):
    it is written to the event's history, withdraws any safety approval and clears the
    line's outcome, so it awaits Technical Support's review again, and once it is
    saved every Technical Support Staff member is told. New notes alone are none of
    these.

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

    asks_for_new_equipment = _changes_the_equipment(line, data)
    if asks_for_new_equipment:
        _reopen_changed_line(coordinator_id, event_request, line, data, sess)

    for key, value in data.items():
        setattr(line, key, value)
    _commit_line_or_conflict(sess)
    if asks_for_new_equipment:
        _notify_technical_support(event_request, NotificationKind.SIGNIFICANT_CHANGE, sess)
    return line


def remove_equipment_line(
    coordinator_id: int | str, reference: str, line_id: int, *, session: Session | None = None
) -> None:
    """Delete one of an event's equipment lines (SCRUM-37 AC2).

    Only the event's assigned coordinator may, while its equipment may still change.
    It is a significant change (AC4): it is written to the event's history, any
    safety approval is withdrawn and the event's reservations of the line's type are
    released, and once it is saved every Technical Support Staff member is told.

    Raises:
        NotFoundError: 404 — no such event request among the coordinator's own, or no
            such line on it.
        EquipmentNotEditableError: 409 — the request's equipment can no longer change.
    """
    sess = resolve_session(session)
    event_request = _event_request_with_editable_equipment(coordinator_id, reference, sess)
    line = _line_of_event(event_request, line_id, sess)
    _withdraw_safety_approval_for_line(coordinator_id, line, "removed", sess)
    _record_line_change(
        coordinator_id,
        event_request,
        previous_value=_line_as_history_value(line.equipment_type_id, line.quantity, sess),
        new_value=None,
        session=sess,
    )
    equipment_services.release_reservations(event_request.id, line.equipment_type_id, session=sess)
    sess.delete(line)
    sess.commit()
    _notify_technical_support(event_request, NotificationKind.SIGNIFICANT_CHANGE, sess)


# --------------------------------------------------------------------------
# SCRUM-87 — reassign an event to a different coordinator
# --------------------------------------------------------------------------

#: The active statuses, from submission until the event is over. A request in one may
#: move to another coordinator (SCRUM-87, ADR-0021; ``approved`` from SCRUM-31,
#: ADR-0028; ``awaiting_clarification`` from SCRUM-32, ADR-0029; ``safety_review`` from
#: SCRUM-97, ADR-0047). A completed, cancelled or rejected event has nothing left to
#: coordinate; a draft is hidden from coordinators altogether, so it never reaches this
#: check (SCRUM-20, ADR-0024). The Event Coordinator Lead's list of every active event
#: reads the same set, so the two can't drift (SCRUM-96 AC1, ADR-0041).
ACTIVE_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {
        EventRequestStatus.SUBMITTED,
        EventRequestStatus.UNDER_REVIEW,
        EventRequestStatus.AWAITING_CLARIFICATION,
        EventRequestStatus.APPROVED,
        EventRequestStatus.SAFETY_REVIEW,
        EventRequestStatus.CONFIRMED,
    }
)
NOT_REASSIGNABLE_MESSAGE = (
    "Only a submitted, under-review, awaiting-clarification, approved, safety-review or "
    "confirmed event request can be reassigned."
)
NOT_ASSIGNED_MESSAGE = "This event request has no coordinator to reassign from."
NOT_A_COORDINATOR_MESSAGE = "No Event Coordinator has this email address."
ALREADY_ASSIGNED_MESSAGE = "That coordinator is already assigned to this event request."


class RequestNotReassignableError(AppError):
    """The request can't move to another coordinator in its current state (409)."""

    status_code = 409
    error_code = "request_not_reassignable"


def _coordinator_to_replace(event_request: EventRequest) -> int:
    """The request's current coordinator, if it can be handed on (ADR-0021).

    Who may reassign is the route's business (SCRUM-96: the Lead only); this checks
    the request. The "no coordinator" check comes first, because giving a request its
    first coordinator is the Lead's assignment route, not a reassignment.

    Raises:
        RequestNotReassignableError: 409 — the request has no coordinator.
        RequestNotReassignableError: 409 — the request isn't in one of the
            ``ACTIVE_STATUSES``.
    """
    if event_request.coordinator_id is None:
        raise RequestNotReassignableError(NOT_ASSIGNED_MESSAGE)
    if event_request.status not in ACTIVE_STATUSES:
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
    """Move an event request to a different Event Coordinator (SCRUM-87, SCRUM-96).

    The Event Coordinator Lead does it, whichever coordinator holds the request (the
    route admits no one else, SCRUM-96 AC3), while it is submitted, under review,
    awaiting clarification, approved or confirmed (ADR-0021). The request's one
    ``coordinator_id`` is replaced (AC1, AC2), and a ``coordinator_reassigned`` history
    entry is saved in the same commit: the previous and the new coordinator's ids and
    names as they were then, who did it and when (AC3, AC7). The event then lists, and
    gives access to, the new coordinator only (AC4, AC5). Once saved, the new
    coordinator gets the usual ``coordinator_assigned`` notification (AC4) and the
    organiser a ``request_assigned`` one (SCRUM-39 AC1, ADR-0030); a failure there is
    logged, not raised (ADR-0015). The previous coordinator is told too, with a
    ``request_assigned`` notification (SCRUM-96 AC5).

    Args:
        actor_id: The Lead's user id, taken from their token, recorded as the actor.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``coordinator_email``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, and the new coordinator's name and email, as the organiser now
        sees them (AC6).

    Raises:
        ValidationError: 400 — payload invalid, or no Event Coordinator has that
            email.
        NotFoundError: 404 — no such request.
        RequestNotReassignableError: 409 — the request has no coordinator, or isn't
            submitted, under review, awaiting clarification, approved or confirmed.
        ConflictError: 409 — that coordinator already has the request.
    """
    data = load_or_raise(ReassignCoordinatorSchema(), payload)
    sess = resolve_session(session)
    event_request = _event_request_for_staff(reference, sess)
    previous_coordinator_id = _coordinator_to_replace(event_request)
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
    _notify_about_assignment(
        event_request, coordinator_id, sess, previous_id=previous_coordinator_id
    )
    return event_request, coordinator


# --------------------------------------------------------------------------
# SCRUM-38 — the equipment requests awaiting Technical Support
# --------------------------------------------------------------------------

#: Statuses of events that won't run, so their equipment no longer needs arranging
#: (SCRUM-38 AC1, ADR-0022), none can be reserved for them (SCRUM-46, ADR-0037) and no
#: outcome can be recorded on their lines (SCRUM-48 AC8, ADR-0040).
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

#: When the event happens. Every venue arrangement was booked against it, so changing
#: any of these affects each one (ADR-0094).
_TIMING_FIELDS = ("proposed_date", "end_date", "start_time", "end_time")

#: Changing when or how big an event is could affect a venue already booked or being
#: searched for, and equipment already requested for it (ADR-0025).
_TIMING_AND_SIZE_FIELDS = (*_TIMING_FIELDS, "expected_attendance")

#: Fields whose change could mean a venue already booked, or being searched for, no
#: longer fits (ADR-0025). :func:`_flag_venue_arrangements` reassesses each of the
#: event's arrangements against whichever of them changed (ADR-0094).
VENUE_AFFECTING_FIELDS: frozenset[str] = frozenset({*_TIMING_AND_SIZE_FIELDS, "venue_requirements"})

#: Fields whose change could mean equipment already requested for the event no
#: longer fits (ADR-0025).
EQUIPMENT_AFFECTING_FIELDS: frozenset[str] = frozenset(
    {*_TIMING_AND_SIZE_FIELDS, "equipment_requirements"}
)

#: Every field whose change is marked significant in the event's history (ADR-0025).
SIGNIFICANT_FIELDS: frozenset[str] = VENUE_AFFECTING_FIELDS | EQUIPMENT_AFFECTING_FIELDS


class RequestNotEditableError(AppError):
    """The request isn't in a status that can be edited right now (409)."""

    status_code = 409
    error_code = "request_not_editable"


@dataclass(frozen=True)
class EventEdit:
    """What :func:`update_event_request` did: the request, and what changed on it."""

    event_request: EventRequest
    changes: list[FieldChange]


def _as_history_value(value: Any) -> HistoryValue:
    """``value`` in the form the history's JSON ``details`` column can hold.

    An instant is shown in business time, as the API shows it (ADR-0009).
    """
    if isinstance(value, datetime):
        return to_business_time(value).isoformat()
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
    """Warn Technical Support that equipment riding on the event may not fit (ADR-0025).

    Technical Support Staff get one ``significant_change`` notification per edit
    when a changed field could affect equipment already requested and the event has
    at least one equipment line (AC2); with no lines there is nothing to reassess.
    Runs after the edit's own commit, so a failed notification never rolls back a
    saved edit; the failure is logged, not raised (ADR-0015). Venue arrangements are
    flagged in the edit's own commit instead (:func:`_flag_venue_arrangements`).
    """
    if not _affects_equipment(changes) or not event_request.equipment_lines:
        return
    _notify_technical_support(event_request, NotificationKind.SIGNIFICANT_CHANGE, session)


def _flag_venue_arrangements(
    event_request: EventRequest,
    changes: list[FieldChange],
    attendance_before: int,
    session: Session,
) -> list[str]:
    """Reassess each of the event's venue arrangements, without committing (AC6).

    ``changes`` are already applied to ``event_request``, so the expected attendance
    from before them is passed in. Each arrangement is reassessed on its own, and only
    those the change affects are flagged (ADR-0094), in the edit's own transaction, so
    a saved edit never leaves an arrangement unflagged.

    Returns:
        What Venue Staff are to be told about each arrangement flagged, once the edit
        is saved.
    """
    from app.modules.venue import services as venue_services  # circular at import time

    changed_fields = set()
    for change in changes:
        changed_fields.add(change.field)
    venue_change = venue_services.SignificantChange(
        timing_changed=not changed_fields.isdisjoint(_TIMING_FIELDS),
        venue_requirements_changed="venue_requirements" in changed_fields,
        previous_attendance=attendance_before,
        new_attendance=event_request.expected_attendance,
    )
    return venue_services.flag_arrangements_after_change(
        event_request.id, venue_change, session=session
    )


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


def _tell_venue_staff_of_flags(
    event_request: EventRequest, notices: list[str], session: Session
) -> None:
    """Tell Venue Staff about each arrangement the saved edit flagged (SCRUM-58 AC1)."""
    from app.modules.venue import services as venue_services  # circular at import time

    venue_services.tell_venue_staff_of_flags(_for_booking(event_request), notices, session=session)


def update_event_request(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    today: date | None = None,
) -> EventEdit:
    """Change the fields sent on a request assigned to the caller (SCRUM-33).

    Only what is sent in ``payload`` changes (AC1, AC3); a value equal to what is
    already saved is not a change. Each changed field is written to the event
    history as its own ``field_changed`` entry, sharing one ``occurred_at``, in the
    same commit as the change itself (AC2, AC4); a field in
    :data:`SIGNIFICANT_FIELDS` is marked ``significant``. A significant change
    withdraws a safety approval in the same commit, naming the significant fields
    (AC7, :func:`withdraw_safety_approval`), and flags only the venue arrangements
    it affects, each reassessed on its own (AC6, ADR-0094); Venue Staff are told
    about each one flagged once the edit is saved. An edit that changes nothing
    writes and commits nothing.

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
    attendance_before = event_request.expected_attendance
    changes = _record_field_changes(
        event_request,
        int(coordinator_id),
        data,
        session=sess,
        now=datetime.now(timezone.utc),
    )
    if not changes:
        return EventEdit(event_request, [])

    significant_fields = [change.field for change in changes if change.significant]
    if significant_fields:
        withdraw_safety_approval(
            event_request.id,
            actor_id=int(coordinator_id),
            details={"significant_fields": significant_fields},
            session=sess,
        )
    venue_notices = _flag_venue_arrangements(event_request, changes, attendance_before, sess)
    sess.commit()
    _reassess_arrangements(event_request, changes, sess)
    _tell_venue_staff_of_flags(event_request, venue_notices, sess)
    return EventEdit(event_request, changes)


#: A field_changed entry about one of these is for internal eyes only (ADR-0025).
INTERNAL_ONLY_FIELDS: frozenset[str] = frozenset({"internal_planning_notes"})
#: Entries of these kinds are for internal eyes only: which equipment Technical
#: Support set aside, and what they ruled on a request, is their working, not the
#: organiser's (SCRUM-46, ADR-0037, SCRUM-48).
INTERNAL_ONLY_KINDS: frozenset[EventHistoryKind] = frozenset(
    {
        EventHistoryKind.EQUIPMENT_RESERVED,
        EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED,
        EventHistoryKind.SAFETY_OUTCOME_RECORDED,
        EventHistoryKind.VENUE_PREPARATION_UPDATED,
        EventHistoryKind.EQUIPMENT_PREPARATION_UPDATED,
        # Venue Staff's note on why a venue is unavailable, which the calendar shows
        # only to them, and the safety check it unsettles (SCRUM-92, ADR-0053).
        EventHistoryKind.ALTERNATIVE_VENUE_NEEDED,
        EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN,
    }
)


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

    Internal staff may see any event's history, except an Event Coordinator, who may
    see only the events assigned to them (SCRUM-96 AC6, SCRUM-24 AC2/AC9, ADR-0034 and
    ADR-0041). An Event Organiser sees only their client organisation's, and never a
    ``field_changed`` entry about ``internal_planning_notes`` (ADR-0025) or an
    ``equipment_reserved`` entry (SCRUM-46).

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
            their organisation, or for a coordinator, none assigned to them.
    """
    sess = resolve_session(session)
    is_internal_viewer = viewer_role in INTERNAL_ROLES
    if viewer_role is Role.EVENT_COORDINATOR:
        event_request = _event_request_assigned_to(viewer_id, reference, sess)
    elif is_internal_viewer:
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


def list_event_requests_with_venue_bookings(
    *, session: Session | None = None
) -> list[EventRequest]:
    """Every event with a venue booking request or a booking, newest first (AC4).

    Whatever the event's status or date, and whatever Venue Staff made of the request:
    this is everything Venue Staff are involved in, as Technical Support's list is for
    equipment. A withdrawn or released request no longer counts (ADR-0085), and a draft
    never shows, as on every staff list (ADR-0024). Every Venue Staff user sees the
    same list, since none is assigned to particular venues (ADR-0035 decision 1).
    """
    from app.modules.venue import services as venue_services  # circular at import time

    sess = resolve_session(session)
    event_ids = venue_services.list_event_ids_with_active_arrangements(session=sess)
    has_a_venue_request = EventRequest.id.in_(event_ids)
    return _list_event_requests_newest_first(and_(has_a_venue_request, _not_a_draft()), sess)


# --------------------------------------------------------------------------
# SCRUM-95 — the Event Coordinator Lead's queue of unassigned requests
# --------------------------------------------------------------------------

#: The one status in which a request is waiting for the Event Coordinator Lead: it has
#: been submitted and nothing has happened to it since. The queue lists the requests
#: with this status and no coordinator, and the Lead may assign exactly those, so the
#: list and the assignment read the same definition and can't drift apart (SCRUM-95
#: AC2, AC3, ADR-0036).
WAITING_FOR_LEAD_STATUS = EventRequestStatus.SUBMITTED

#: Refusing a first assignment: the request already has a coordinator, in the idiom of
#: SCRUM-87's :data:`ALREADY_ASSIGNED_MESSAGE`, or it is no longer waiting at all.
ALREADY_HAS_COORDINATOR_MESSAGE = "This event request already has a coordinator."
NOT_ASSIGNABLE_MESSAGE = "Only a submitted event request can be assigned to a coordinator."


class RequestNotAssignableError(AppError):
    """The request isn't waiting for the Lead to assign it, in its state (409)."""

    status_code = 409
    error_code = "request_not_assignable"


def list_unassigned_requests(*, session: Session | None = None) -> list[EventRequest]:
    """Submitted requests with no coordinator, oldest submission first (SCRUM-95 AC2).

    A queue: the request that has waited longest is first, and one with the same time
    goes by id, the mirror of :func:`_list_event_requests_newest_first`. Nothing waiting
    is an empty list, not an error.

    Only :data:`WAITING_FOR_LEAD_STATUS` requests are listed, not everything past the
    draft stage: a draft hasn't been submitted, and a cancelled or rejected request is
    no longer waiting for anybody, even though it can still have no coordinator. A
    request SCRUM-30 assigned before the Lead existed keeps its coordinator, so
    ``coordinator_id IS NULL`` leaves it out without any data migration (ADR-0036).

    The submission time is the request's ``created_at`` (ADR-0036). There is no separate
    submission instant, so a request that sat as a draft shows when the draft was
    started, not when it was submitted.

    Args:
        session: Database session; defaults to ``db.session``.

    Returns:
        The waiting requests, oldest first.
    """
    stmt = (
        select(EventRequest)
        .where(
            EventRequest.status == WAITING_FOR_LEAD_STATUS,
            EventRequest.coordinator_id.is_(None),
        )
        .order_by(EventRequest.created_at.asc(), EventRequest.id.asc())
    )
    return list(resolve_session(session).scalars(stmt))


def _active_requests_newest_first(session: Session) -> list[EventRequest]:
    """Every request in an :data:`ACTIVE_STATUSES` status, newest first."""
    return _list_event_requests_newest_first(EventRequest.status.in_(ACTIVE_STATUSES), session)


def list_active_requests(*, session: Session | None = None) -> list[ActiveRequest]:
    """Every active event with its coordinator's name, newest first (SCRUM-96 AC1).

    "Active" is :data:`ACTIVE_STATUSES`, the same set a reassignment accepts (ADR-0041):
    drafts, and completed, cancelled and rejected events, are left out. The Lead
    supervises every coordinator, so the list is not filtered by Lead (SCRUM-96
    Assumption). A submitted request still waiting to be assigned is active, and is
    listed with no coordinator.

    Args:
        session: Database session; defaults to ``db.session``.

    Returns:
        The active events, each with its coordinator's full name or ``None``.
    """
    sess = resolve_session(session)
    event_requests = _active_requests_newest_first(sess)
    coordinator_ids = {r.coordinator_id for r in event_requests if r.coordinator_id is not None}
    names = get_user_full_names(coordinator_ids, session=sess)
    active = []
    for event_request in event_requests:
        coordinator_name = names.get(event_request.coordinator_id)
        active.append(ActiveRequest(event_request, coordinator_name))
    return active


def list_requests_for_each_coordinator(
    *, session: Session | None = None
) -> list[CoordinatorWorkload]:
    """Each coordinator's active events, coordinators by name (SCRUM-96 AC2).

    A coordinator with no active event is left out rather than listed empty, so the
    list shows who has work to supervise; a request nobody holds yet is in no one's
    list. A coordinator's events are newest first, as in :func:`list_active_requests`.

    Args:
        session: Database session; defaults to ``db.session``.

    Returns:
        One entry per coordinator who holds an active event, ordered by name then id.
    """
    sess = resolve_session(session)
    held_by: dict[int, list[EventRequest]] = {}
    for event_request in _active_requests_newest_first(sess):
        if event_request.coordinator_id is None:
            continue
        held_by.setdefault(event_request.coordinator_id, []).append(event_request)
    names = get_user_full_names(held_by, session=sess)
    workloads = [
        CoordinatorWorkload(coordinator_id, names[coordinator_id], assigned)
        for coordinator_id, assigned in held_by.items()
    ]
    return sorted(workloads, key=lambda w: (w.coordinator_name, w.coordinator_id))


def _request_waiting_for_the_lead(reference: str, session: Session) -> EventRequest:
    """The request behind ``reference``, if the Lead still has it to give (ADR-0036).

    Resolved the way every internal role resolves a reference, so a draft can't be found
    at all rather than refused (SCRUM-20 AC4, ADR-0024). A request that already has a
    coordinator is a conflict: giving it to someone else would be a reassignment, which
    is its own story (ADR-0021 decision 6). The already-assigned check comes first
    because it has its own answer; the status check then covers a cancelled or rejected
    request, which has no coordinator and is no longer waiting.

    Raises:
        NotFoundError: 404 — no such request, or it is still a draft.
        ConflictError: 409 — the request already has a coordinator.
        RequestNotAssignableError: 409 — the request isn't waiting for the Lead.
    """
    event_request = _event_request_for_staff(reference, session)
    if event_request.coordinator_id is not None:
        raise ConflictError(ALREADY_HAS_COORDINATOR_MESSAGE)
    if event_request.status is not WAITING_FOR_LEAD_STATUS:
        raise RequestNotAssignableError(NOT_ASSIGNABLE_MESSAGE)
    return event_request


def assign_coordinator_to_request(
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    assigned_by: int | str,
    session: Session | None = None,
) -> tuple[EventRequest, CoordinatorContact]:
    """Give a request waiting in the Lead's queue to one Event Coordinator (SCRUM-95).

    AC3: the request gets exactly one ``coordinator_id``, and so leaves the queue, which
    lists only the requests that have none. The coordinator is named by email, as a
    reassignment names them, since user ids are never shown to other users (ADR-0021
    decision 3). A ``coordinator_assigned`` history entry is saved in the same commit as
    the change it records, with the Lead as its actor: SCRUM-30 wrote that entry with a
    NULL actor because the system chose, and it is the Lead who chooses now (ADR-0018,
    ADR-0036). Once saved, the coordinator gets the usual ``coordinator_assigned``
    notification and the organiser a ``request_assigned`` one (AC5, SCRUM-39 AC1,
    ADR-0030); a failure there is logged, not raised (ADR-0015). The event then appears
    in the coordinator's list, which reads ``coordinator_id`` (AC5, ADR-0018).

    This is a first assignment and never a move: a request that already has a
    coordinator is refused. Changing one is a reassignment, which the Lead does through
    SCRUM-87's ``/reassign`` (SCRUM-96).

    The checks run in this order, so the first failure decides the answer: payload
    ``400``; reference ``404``; already assigned ``409``; not waiting ``409``; email
    ``400``. The body comes first because it is the caller's own and says nothing about
    any request. The request's own state comes next, and the email lookup last, so a
    refused assignment never resolves an address and the route can't be used to find out
    which emails belong to Event Coordinators.

    Args:
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``coordinator_email``, matched ignoring case.
        assigned_by: The Lead's user id, taken from their token, recorded as the actor
            of the history entry. Their role isn't checked here: the route's
            ``@requires_role(Role.EVENT_COORDINATOR_LEAD)`` is what proves it, which is
            also how no Event Coordinator can assign anything (AC6).
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, and the coordinator's name and email as the organiser now sees
        them, so the route can answer with no user id in it (ADR-0021 decision 12).

    Raises:
        ValidationError: 400 — payload invalid, or no Event Coordinator has that email.
        NotFoundError: 404 — no such request, or it is still a draft.
        ConflictError: 409 — the request already has a coordinator.
        RequestNotAssignableError: 409 — the request isn't waiting for the Lead.
    """
    data = load_or_raise(AssignCoordinatorSchema(), payload)
    sess = resolve_session(session)
    event_request = _request_waiting_for_the_lead(reference, sess)
    coordinator_id = _event_coordinator_id_by_email(data["coordinator_email"], sess)
    coordinator = _contact_of_coordinator(coordinator_id, sess)

    event_request.coordinator_id = coordinator_id
    record_event_history(
        event_request,
        EventHistoryKind.COORDINATOR_ASSIGNED,
        actor_id=int(assigned_by),
        details={"coordinator_id": coordinator_id},
        session=sess,
    )
    sess.commit()
    _notify_about_assignment(event_request, coordinator_id, sess)
    return event_request, coordinator


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
# SCRUM-45 / SCRUM-46 — equipment availability and reservation
# --------------------------------------------------------------------------

PERIOD_INCOMPLETE_MESSAGE = "The event has no complete date and times yet."


class EventPeriodIncompleteError(AppError):
    """The event lacks a date or a time, so it has no period (409)."""

    status_code = 409
    error_code = "event_period_incomplete"


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


def _equipment_need_of(event_request: EventRequest) -> EventEquipmentNeed:
    """The request's period and the equipment it asks for.

    Raises:
        EventPeriodIncompleteError: 409 — the event has no complete date and times.
    """
    starts_at, ends_at = _event_period(event_request)
    requested = {}
    for line in event_request.equipment_lines:
        requested[line.equipment_type_id] = line.quantity
    return EventEquipmentNeed(
        event_id=event_request.id,
        starts_at=starts_at,
        ends_at=ends_at,
        requested=requested,
        accepts_reservations=event_request.status not in EQUIPMENT_NOT_NEEDED_STATUSES,
    )


def get_event_equipment_need(
    reference: str, *, session: Session | None = None
) -> EventEquipmentNeed:
    """An event's period and the equipment it asks for, for the equipment module.

    For Technical Support reserving, who may reserve for any event, so a draft is
    hidden as everywhere else (ADR-0024) and nothing more.

    Args:
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such request, or it is still a draft.
        EventPeriodIncompleteError: 409 — the event has no complete date and times.
    """
    event_request = _event_request_for_staff(reference, resolve_session(session))
    return _equipment_need_of(event_request)


def get_event_equipment_need_for_viewer(
    viewer_id: int | str, reference: str, *, viewer_role: Role, session: Session | None = None
) -> EventEquipmentNeed:
    """An event's period and equipment, if the viewer may read its equipment.

    For the equipment module's reads, scoped as the event's equipment lines are
    (ADR-0019, ADR-0037): Technical Support Staff may read any event's, a coordinator
    only an event assigned to them.

    Args:
        viewer_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        viewer_role: The caller's role.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such request, a draft, or for a coordinator, not one
            of their own (the same answer, ADR-0012).
        EventPeriodIncompleteError: 409 — the event has no complete date and times.
    """
    event_request = _event_request_for_equipment_viewer(
        viewer_id, reference, viewer_role, resolve_session(session)
    )
    return _equipment_need_of(event_request)


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


def record_equipment_preparation_updated(
    event_id: int,
    details: Mapping[str, Any],
    *,
    actor_id: int,
    session: Session | None = None,
) -> None:
    """Record in the event's history that a reservation's preparation was updated.

    The audit trail of an update (SCRUM-85 AC4, ADR-0050), uncommitted: the entry rides
    in the update's transaction, so it is saved with the update or not at all.
    Organisers never see it (:func:`_shown_to_organiser`).

    Args:
        event_id: The event's id, from the reservation.
        details: ``reservation_id``, ``equipment_type_id``, ``equipment_type_name``,
            ``status`` and ``notes``.
        actor_id: Who recorded the preparation.
        session: Database session; defaults to ``db.session``.
    """
    sess = resolve_session(session)
    event_request = sess.get(EventRequest, event_id)
    record_event_history(
        event_request,
        EventHistoryKind.EQUIPMENT_PREPARATION_UPDATED,
        actor_id=actor_id,
        details=dict(details),
        session=sess,
    )


def _notify_assigned_coordinator(
    event_request: EventRequest,
    kind: NotificationKind,
    session: Session,
    *,
    detail: str | None = None,
) -> None:
    """Tell the event's assigned coordinator that ``kind`` happened, if there is one.

    With nobody assigned, nobody is told, and that is logged. ``detail`` says more,
    such as the Safety Officer's reason (SCRUM-98 AC8).
    """
    if event_request.coordinator_id is None:
        _warn_unassigned(event_request)
        return
    _raise_notifications(
        [event_request.coordinator_id], event_request, kind, session, detail=detail
    )


def notify_coordinator_equipment_reserved(event_id: int, *, session: Session | None = None) -> None:
    """Tell the event's assigned coordinator that equipment was reserved (SCRUM-46 AC5).

    For the equipment module, after the reservation's own commit (ADR-0015): only the
    assigned coordinator hears, once for every reservation (ADR-0018). With nobody
    assigned the reservation stands, nobody is told, and that is logged.

    Args:
        event_id: The event's id, from :class:`EventEquipmentNeed`.
        session: Database session; defaults to ``db.session``.
    """
    sess = resolve_session(session)
    event_request = sess.get(EventRequest, event_id)
    _notify_assigned_coordinator(event_request, NotificationKind.EQUIPMENT_RESERVED, sess)


EQUIPMENT_SHORT_DETAIL = (
    "Equipment reserved for this event is no longer all available: "
    "some units were taken out of service."
)


def notify_coordinators_equipment_short(
    event_ids: Iterable[int], *, session: Session | None = None
) -> None:
    """Tell each event's assigned coordinator its reserved equipment is now short.

    For the equipment module (SCRUM-47 AC3, ADR-0046), after the change's own commit
    (ADR-0015). It reuses the significant-change kind: the event's arrangements need
    another look. Each coordinator hears once per event, with the reason as the detail.

    Args:
        event_ids: The ids of the events whose reservations were left short.
        session: Database session; defaults to ``db.session``.
    """
    sess = resolve_session(session)
    for event_id in event_ids:
        event_request = sess.get(EventRequest, event_id)
        _notify_assigned_coordinator(
            event_request,
            NotificationKind.SIGNIFICANT_CHANGE,
            sess,
            detail=EQUIPMENT_SHORT_DETAIL,
        )


def notify_coordinator_alternative_venue_needed(
    event_id: int, *, detail: str, session: Session | None = None
) -> None:
    """Tell the event's assigned coordinator a venue became unavailable (SCRUM-92 AC5).

    For the venue module, after the flag's own commit (ADR-0015). ``detail`` names the
    venue, the reason and the period. With nobody assigned the flag stands, nobody is
    told, and that is logged.
    """
    sess = resolve_session(session)
    event_request = sess.get(EventRequest, event_id)
    _notify_assigned_coordinator(
        event_request, NotificationKind.ALTERNATIVE_VENUE_NEEDED, sess, detail=detail
    )


# --------------------------------------------------------------------------
# SCRUM-68 — mark an event as completed after it has taken place
# --------------------------------------------------------------------------

NOT_CONFIRMED_MESSAGE = "Only a confirmed event can be marked completed."
NOT_YET_ENDED_MESSAGE = "The event has not ended yet."


class RequestNotCompletableError(AppError):
    """The event can't be marked completed yet, or in its current state (409)."""

    status_code = 409
    error_code = "request_not_completable"


def _starts_at(event_request: EventRequest) -> datetime:
    """When the event starts, as a UTC instant (ADR-0009).

    The start is ``proposed_date`` and ``start_time``, a wall-clock time in business
    time (ADR-0002).
    """
    return _business_instant(event_request.proposed_date, event_request.start_time)


def _ends_at(event_request: EventRequest) -> datetime:
    """When the event ends, as a UTC instant: ``end_date`` and ``end_time`` likewise."""
    return _business_instant(event_request.end_date, event_request.end_time)


def _has_ended(event_request: EventRequest, now: datetime) -> bool:
    """Whether ``now`` is at or after the event's end (SCRUM-68 AC2, ADR-0027)."""
    return now >= _ends_at(event_request)


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


def _has_arrangements(event_request: EventRequest, session: Session) -> bool:
    """Whether arrangements have been made for the event (SCRUM-31 AC7, ADR-0028).

    An equipment request, or a venue booking request that is still one of the event's
    arrangements, whatever Venue Staff made of it. A withdrawn or released one is not,
    just as a removed equipment request is gone (ADR-0084).
    """
    from app.modules.venue import services as venue_services  # circular at import time

    if len(event_request.equipment_lines) > 0:
        return True
    return venue_services.count_active_arrangements(event_request.id, session=session) > 0


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
    if event_request.status in DECIDED_STATUSES and _has_arrangements(event_request, session):
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


# --------------------------------------------------------------------------
# SCRUM-48 — record the outcome of an equipment review
# --------------------------------------------------------------------------


def outcome_status_for(quantity: int, provided: int) -> EquipmentLineStatus:
    """Which outcome ``provided`` units against a request for ``quantity`` is.

    The only place the outcome status is decided, so it can never disagree with the
    quantity stored beside it (SCRUM-48 AC1-AC3).
    """
    if provided == quantity:
        return EquipmentLineStatus.FULFILLED
    if provided == 0:
        return EquipmentLineStatus.UNAVAILABLE
    return EquipmentLineStatus.PARTIALLY_FULFILLED


def lines_without_outcome(
    event_id: int, *, session: Session | None = None
) -> list[EventEquipmentLine]:
    """The event's equipment lines Technical Support has not yet ruled on (SCRUM-48).

    SCRUM-97 and SCRUM-49 refuse to let an event into Safety Review while this is
    not empty: every equipment request must carry a recorded outcome first.
    """
    query = (
        select(EventEquipmentLine)
        .where(
            EventEquipmentLine.event_request_id == event_id,
            EventEquipmentLine.provided_quantity.is_(None),
        )
        .order_by(EventEquipmentLine.id)
    )
    return list(resolve_session(session).scalars(query).all())


def all_outcomes_recorded(event_id: int, *, session: Session | None = None) -> bool:
    """Whether every one of the event's equipment lines has an outcome (SCRUM-48).

    ``True`` for an event with no equipment at all, because nothing is outstanding.
    """
    return not lines_without_outcome(event_id, session=session)


OUTCOME_NOTE_REQUIRED_MESSAGE = "A note is required unless the whole request can be provided."
PROVIDED_ABOVE_REQUESTED_MESSAGE = "Cannot provide more than was requested."
#: Why an outcome is refused on an event that won't run; names the event's own status.
OUTCOMES_CLOSED_MESSAGE = (
    "An equipment outcome can't be recorded for an event that is completed, cancelled"
    " or rejected; this one is {status}."
)


def _check_outcome_is_possible(line: EventEquipmentLine, outcome: Mapping[str, Any]) -> None:
    """Refuse an outcome that provides more than was asked, or a shortfall unexplained.

    Raises:
        ValidationError: 400 — on ``provided_quantity`` or on ``note``.
    """
    provided = outcome["provided_quantity"]
    if provided > line.quantity:
        raise ValidationError(
            "Invalid request.", details={"provided_quantity": [PROVIDED_ABOVE_REQUESTED_MESSAGE]}
        )
    if provided < line.quantity and outcome["note"] is None:
        raise ValidationError("Invalid request.", details={"note": [OUTCOME_NOTE_REQUIRED_MESSAGE]})


#: How an outcome notice names each outcome (SCRUM-50 AC4).
OUTCOME_WORDS = {
    EquipmentLineStatus.FULFILLED: "fulfilled",
    EquipmentLineStatus.PARTIALLY_FULFILLED: "partially fulfilled",
    EquipmentLineStatus.UNAVAILABLE: "unavailable",
}


def _outcome_notice_detail(line: EventEquipmentLine, equipment_name: str) -> str:
    """The outcome as the coordinator is told it, with the note if there is one (AC4).

    For example ``"Projector: partially fulfilled, 6 of 10 provided. Note: Only six in
    stock"`` (ADR-0055).
    """
    detail = (
        f"{equipment_name}: {OUTCOME_WORDS[line.status]},"
        f" {line.provided_quantity} of {line.quantity} provided."
    )
    if line.outcome_note is None:
        return detail
    return f"{detail} Note: {line.outcome_note}"


def record_equipment_outcome(
    reviewer_id: int | str,
    reference: str,
    line_id: int,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> EventEquipmentLine:
    """Record, or revise, how much of an equipment line Technical Support will provide.

    SCRUM-48 AC1-AC5, AC7-AC8. The status follows from the quantity provided; a
    shortfall needs a note, and a line met in full keeps none. Every call adds a history
    entry, so a revision leaves the earlier outcome on record. A revision, a line that
    already had an outcome, also withdraws a safety approval (AC7, ADR-0087). Both are
    saved with the outcome; the event's coordinator is told afterwards (ADR-0015), with
    the equipment, the outcome and the note (SCRUM-50 AC4, ADR-0055). An event that
    won't run takes no outcome at all, first or revised (AC8).

    Args:
        reviewer_id: The Technical Support user's id, taken from their token.
        reference: The event request's ``EVR-…`` reference.
        line_id: The equipment line the outcome is for.
        payload: Decoded JSON body: ``provided_quantity`` and optional ``note``.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The updated :class:`EventEquipmentLine`.

    Raises:
        ValidationError: 400 — invalid payload, more provided than requested, or a
            shortfall with no note.
        NotFoundError: 404 — no such request, or no such line on it.
        ConflictError: 409 — the event is completed, cancelled or rejected; the
            message names its status (AC8).
    """
    outcome = load_or_raise(RecordEquipmentOutcomeSchema(), payload)
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)
    reviewer = int(reviewer_id)
    event_request = _event_request_for_staff(reference, sess)
    if event_request.status in EQUIPMENT_NOT_NEEDED_STATUSES:
        raise ConflictError(OUTCOMES_CLOSED_MESSAGE.format(status=event_request.status.value))
    line = _line_of_event(event_request, line_id, sess)
    _check_outcome_is_possible(line, outcome)
    equipment_type = equipment_services.get_equipment_type(line.equipment_type_id, session=sess)
    previous_provided_quantity = line.provided_quantity

    line.provided_quantity = outcome["provided_quantity"]
    line.status = outcome_status_for(line.quantity, line.provided_quantity)
    # A line met in full carries no note, so a revision never keeps a stale reason.
    line.outcome_note = None if line.status is EquipmentLineStatus.FULFILLED else outcome["note"]
    line.reviewed_by = reviewer
    line.reviewed_at = now
    record_event_history(
        event_request,
        EventHistoryKind.EQUIPMENT_OUTCOME_RECORDED,
        actor_id=reviewer,
        details={
            "equipment_line_id": line.id,
            "equipment_type_id": line.equipment_type_id,
            "equipment_type_name": equipment_type.name,
            "quantity": line.quantity,
            "provided_quantity": line.provided_quantity,
            "status": line.status.value,
            "note": line.outcome_note,
        },
        session=sess,
        now=now,
    )
    is_revision = previous_provided_quantity is not None
    if is_revision:
        withdraw_safety_approval(
            event_request.id,
            actor_id=reviewer,
            details={
                "equipment_line_id": line.id,
                "equipment_type_name": equipment_type.name,
                "previous_provided_quantity": previous_provided_quantity,
            },
            session=sess,
        )
    sess.commit()
    _notify_assigned_coordinator(
        event_request,
        NotificationKind.EQUIPMENT_OUTCOME_RECORDED,
        sess,
        detail=_outcome_notice_detail(line, equipment_type.name),
    )
    return line


# --------------------------------------------------------------------------
# SCRUM-69 — enable registration for an event and set its capacity
# --------------------------------------------------------------------------

CAPACITY_REQUIRED_MESSAGE = "A capacity is required to enable registration."
REGISTRATION_NOT_CONFIRMED_MESSAGE = "Registration can be enabled only for a confirmed event."
CAPACITY_BELOW_REGISTERED_MESSAGE = (
    "Capacity cannot be lower than the {registered} places already taken."
)
CUT_OFF_NOT_BEFORE_START_MESSAGE = "The withdrawal cut-off must be before the event starts."


class RegistrationNotEnablableError(AppError):
    """Registration can't be enabled while the event is not confirmed (409)."""

    status_code = 409
    error_code = "registration_not_enablable"


def _settings_after(event_request: EventRequest, data: Mapping[str, Any]) -> dict[str, Any]:
    """The registration settings the event will have once ``data`` is applied.

    A setting left out of ``data`` keeps its current value, except ``enabled`` on an
    event that has never had a capacity: that follows what the organiser asked for
    (SCRUM-69 AC1, ADR-0043). A cut-off sent as ``None`` is cleared (ADR-0086).
    """
    capacity = data.get("registration_capacity", event_request.registration_capacity)
    cut_off = data.get("withdrawal_cut_off", event_request.withdrawal_cut_off)
    if "registration_enabled" in data:
        enabled = data["registration_enabled"]
    elif event_request.registration_capacity is None:
        enabled = event_request.registration_required
    else:
        enabled = event_request.registration_enabled
    return {
        "registration_enabled": enabled,
        "registration_capacity": capacity,
        "withdrawal_cut_off": cut_off,
    }


def _check_registration_may_be_enabled(
    event_request: EventRequest, settings: Mapping[str, Any]
) -> None:
    """Refuse settings that enable registration without a capacity or before confirming.

    Disabled settings are always allowed (SCRUM-69 AC2, AC4, ADR-0043).

    Raises:
        ValidationError: 400 — enabled with no capacity.
        RegistrationNotEnablableError: 409 — enabled while the event isn't confirmed.
    """
    if not settings["registration_enabled"]:
        return
    if settings["registration_capacity"] is None:
        raise ValidationError(
            "Invalid request.", details={"registration_capacity": [CAPACITY_REQUIRED_MESSAGE]}
        )
    if event_request.status is not EventRequestStatus.CONFIRMED:
        raise RegistrationNotEnablableError(REGISTRATION_NOT_CONFIRMED_MESSAGE)


def _check_capacity_covers_registrations(
    event_request: EventRequest, settings: Mapping[str, Any], session: Session
) -> None:
    """Refuse a capacity below the number already registered (SCRUM-69 AC5, ADR-0043).

    The check applies whether or not registration is enabled: a capacity is kept and
    used again when it is. A capacity of exactly the number registered is allowed.

    Raises:
        ValidationError: 400 — the capacity is lower than the places already taken.
    """
    capacity = settings["registration_capacity"]
    if capacity is None:
        return
    # Imported here because the registration module imports this one for event facts.
    from app.modules.registration.services import count_registered

    registered = count_registered(event_request.id, session=session)
    if capacity < registered:
        message = CAPACITY_BELOW_REGISTERED_MESSAGE.format(registered=registered)
        raise ValidationError("Invalid request.", details={"registration_capacity": [message]})


def _check_cut_off_before_start(event_request: EventRequest, data: Mapping[str, Any]) -> None:
    """Refuse a withdrawal cut-off sent for the event's start or later (SCRUM-69 AC6).

    Only a cut-off in ``data`` is checked: one already saved is left alone if the event
    has since moved earlier, and withdrawals then close at the start (ADR-0086).

    Raises:
        ValidationError: 400 — the cut-off is not before the event starts.
    """
    cut_off = data.get("withdrawal_cut_off")
    if cut_off is None:
        return
    if cut_off >= _starts_at(event_request):
        raise ValidationError(
            "Invalid request.", details={"withdrawal_cut_off": [CUT_OFF_NOT_BEFORE_START_MESSAGE]}
        )


def update_registration_settings(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> EventRequest:
    """Enable or disable registration for an event, and set its capacity (SCRUM-69).

    Only the request's assigned coordinator may (ADR-0043). Only what is sent changes;
    when ``registration_enabled`` is left out of an event that has never had a capacity,
    it follows the organiser's ``registration_required`` (AC1). Enabling needs a
    capacity (AC2) and a confirmed event (AC4); the capacity is whatever the organiser
    decided, whatever the venue holds (AC3), but can't be lower than the number
    already registered (AC5). An optional withdrawal cut-off must be before the event
    starts (AC6, ADR-0086). Each setting that changes is written to the event history
    as a ``field_changed`` entry naming the caller, sharing one ``occurred_at``, in
    the same commit as the change (AC7). A call that changes nothing writes and
    commits nothing.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: any of ``registration_enabled``,
            ``registration_capacity`` and ``withdrawal_cut_off``.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The request, with its settings as they now are.

    Raises:
        NotFoundError: 404 — no such request, a draft, or not the caller's.
        ValidationError: 400 — payload invalid, registration enabled with no capacity,
            a capacity below the number registered, or a cut-off not before the event
            starts (details per field).
        RegistrationNotEnablableError: 409 — registration enabled while the event isn't
            confirmed.
    """
    sess = resolve_session(session)
    event_request = _event_request_assigned_to(coordinator_id, reference, sess)
    data = load_or_raise(UpdateRegistrationSettingsSchema(), payload)
    settings = _settings_after(event_request, data)
    _check_registration_may_be_enabled(event_request, settings)
    _check_capacity_covers_registrations(event_request, settings, sess)
    _check_cut_off_before_start(event_request, data)
    if now is None:
        now = datetime.now(timezone.utc)

    changes = _record_field_changes(
        event_request, int(coordinator_id), settings, session=sess, now=now
    )
    if changes:
        sess.commit()
    return event_request


# --------------------------------------------------------------------------
# SCRUM-52 — the event facts the registration module asks for
# --------------------------------------------------------------------------

REGISTRABLE_EVENT_NOT_FOUND_MESSAGE = "Event not found."


@dataclass(frozen=True)
class RegistrableEvent:
    """An event Attendees may register for, as the registration module sees it.

    ``starts_at`` and ``ends_at`` are aware UTC instants (ADR-0009); ``description`` is
    empty rather than ``None``, since the catalogue always shows some text.
    """

    id: int
    reference: str
    name: str
    description: str
    starts_at: datetime
    ends_at: datetime
    capacity: int


@dataclass(frozen=True)
class EventHeading:
    """The name, times and status of any event, for a list that mentions it.

    ``status`` is the status's plain value (``"confirmed"``), so a module reading it
    never needs the events module's models. ``withdrawal_cut_off`` is the one the
    coordinator recorded, or ``None`` (SCRUM-69 AC6, ADR-0086).
    """

    id: int
    name: str
    starts_at: datetime
    ends_at: datetime
    status: str
    withdrawal_cut_off: datetime | None


def _is_open_for_registration() -> ColumnElement[bool]:
    """The condition for a confirmed event with registration on (SCRUM-52 AC1, AC4)."""
    return and_(
        EventRequest.status == EventRequestStatus.CONFIRMED,
        EventRequest.registration_enabled.is_(True),
    )


def _as_registrable_event(event_request: EventRequest) -> RegistrableEvent:
    """The facts about an event that is open for registration."""
    return RegistrableEvent(
        id=event_request.id,
        reference=event_request.reference,
        name=event_request.name,
        description=event_request.description or "",
        starts_at=_starts_at(event_request),
        ends_at=_ends_at(event_request),
        # A check constraint gives every enabled event a capacity (ADR-0043).
        capacity=event_request.registration_capacity,  # type: ignore[arg-type]
    )


def _mentions(event: RegistrableEvent, search: str) -> bool:
    """Whether the event's name or description contains ``search``, ignoring case.

    A blank search is contained in every text, so it matches every event.
    """
    text = f"{event.name} {event.description}"
    return search.lower() in text.lower()


def list_registrable_events(
    *,
    search: str = "",
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
    session: Session | None = None,
    now: datetime | None = None,
) -> list[RegistrableEvent]:
    """List the confirmed events open for registration, soonest first (SCRUM-52 AC1).

    Leaves out an event that has already ended (ADR-0032). The start, held as a date and
    a time, is worked out here rather than in SQL, so the filters on it read plainly.

    Args:
        search: Text the event's name or description must contain, ignoring case.
        starts_from: The earliest start, inclusive; ``None`` for no limit.
        starts_to: The latest start, inclusive; ``None`` for no limit.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The events that match, as :class:`RegistrableEvent` facts.
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)

    stmt = select(EventRequest).where(_is_open_for_registration())
    events = []
    for event_request in sess.scalars(stmt):
        event = _as_registrable_event(event_request)
        if event.ends_at <= now or not _mentions(event, search):
            continue
        if starts_from is not None and event.starts_at < starts_from:
            continue
        if starts_to is not None and event.starts_at > starts_to:
            continue
        events.append(event)
    return sorted(events, key=lambda event: (event.starts_at, event.id))


def get_registrable_event_for_update(
    event_id: int, *, session: Session | None = None, now: datetime | None = None
) -> RegistrableEvent:
    """Find an event Attendees may register for, and lock its row until the commit.

    The lock makes two Attendees asking for the last place take turns: the second
    counts the registrations only after the first has committed (SCRUM-54 AC4).

    Args:
        event_id: The event's id.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The event's :class:`RegistrableEvent` facts.

    Raises:
        NotFoundError: 404 — no such event, it isn't confirmed with registration
            enabled, or it has already ended (SCRUM-52 AC4, ADR-0032).
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)
    stmt = (
        select(EventRequest)
        .where(EventRequest.id == event_id, _is_open_for_registration())
        .with_for_update()
    )
    event_request = sess.scalar(stmt)
    if event_request is None or _has_ended(event_request, now):
        raise NotFoundError(REGISTRABLE_EVENT_NOT_FOUND_MESSAGE)
    return _as_registrable_event(event_request)


def list_event_headings(
    event_ids: Iterable[int], *, session: Session | None = None
) -> list[EventHeading]:
    """The name, times and status of each event in ``event_ids``, whatever its status.

    Args:
        event_ids: The events' ids; one that doesn't exist is left out.
        session: Database session; defaults to ``db.session``.

    Returns:
        One :class:`EventHeading` per event found, in no particular order.
    """
    sess = resolve_session(session)
    stmt = select(EventRequest).where(EventRequest.id.in_(list(event_ids)))
    headings = []
    for row in sess.scalars(stmt):
        headings.append(
            EventHeading(
                id=row.id,
                name=row.name,
                starts_at=_starts_at(row),
                ends_at=_ends_at(row),
                status=row.status.value,
                withdrawal_cut_off=row.withdrawal_cut_off,
            )
        )
    return headings


# --------------------------------------------------------------------------
# SCRUM-97 — submit an event for operational safety check
# --------------------------------------------------------------------------

NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE = "Only an approved event can go to Safety Review."
SAFETY_REVIEW_NOT_READY_MESSAGE = (
    "The event can go to Safety Review once every venue arrangement is approved and every "
    "equipment request has an outcome from Technical Support."
)


class SafetyReviewNotAllowedError(AppError):
    """The event isn't approved, or its venues or equipment aren't settled (409)."""

    status_code = 409
    error_code = "safety_review_not_allowed"


def _venue_gaps(event_id: int, session: Session) -> list[str]:
    """Why the event's venues keep it out of Safety Review; empty when they don't.

    It needs at least one venue arranged, and every active arrangement approved
    (SCRUM-97 AC1, ADR-0047), not needing an alternative venue (SCRUM-92) and not
    flagged by a significant change (SCRUM-33 AC6, SCRUM-58 AC3, ADR-0094).
    """
    from app.modules.venue import services as venue_services  # circular at import time

    if venue_services.count_active_arrangements(event_id, session=session) == 0:
        return ["The event has no venue arranged."]

    gaps = []
    for arrangement in venue_services.list_unapproved_arrangements(event_id, session=session):
        gaps.append(f"Venue arrangement {arrangement.id} is {arrangement.status.value}.")
    # SCRUM-49 AC6: an Approved booking whose venue became unavailable doesn't count.
    for arrangement in venue_services.list_flagged_arrangements(event_id, session=session):
        gaps.append(f"Venue arrangement {arrangement.id} needs an alternative venue.")
    # SCRUM-58 AC3: nor does one a significant change flagged, once for each reason.
    flagged_after_change = venue_services.list_arrangements_flagged_after_change(
        event_id, session=session
    )
    for arrangement in flagged_after_change:
        for flag in arrangement.reassessment_flags:
            gaps.append(
                f"Venue arrangement {arrangement.id} is flagged ({flag.kind.label}): {flag.reason}"
            )
    return gaps


def _equipment_gaps(event_id: int, session: Session) -> list[str]:
    """Each equipment request still waiting on Technical Support (SCRUM-97 AC1, AC2).

    An event with no equipment requests has none waiting, so it passes (AC2).
    """
    gaps = []
    for line in lines_without_outcome(event_id, session=session):
        gaps.append(f"Equipment request {line.id} has no outcome from Technical Support.")
    return gaps


def _arrangement_gaps(event_id: int, session: Session) -> dict[str, list[str]]:
    """The venue and equipment gaps that hold the event back, by area.

    Shared by the Safety Review gate (SCRUM-97) and confirmation (SCRUM-49), which ask
    the same of the venues and equipment. An area with no gap is left out.
    """
    held_back = {}
    venue_gaps = _venue_gaps(event_id, session)
    if venue_gaps:
        held_back["venue_arrangements"] = venue_gaps
    equipment_gaps = _equipment_gaps(event_id, session)
    if equipment_gaps:
        held_back["equipment"] = equipment_gaps
    return held_back


def _notify_safety_officers(event_request: EventRequest, session: Session) -> None:
    """Tell every Safety Officer the event has entered Safety Review (SCRUM-97 AC4).

    Called once the move is saved. Each Safety Officer hears it once, as a single write.
    """
    officer_ids = list_user_ids_with_role(Role.SAFETY_OFFICER, session=session)
    _raise_notifications(
        officer_ids, event_request, NotificationKind.SAFETY_REVIEW_REQUESTED, session
    )


def submit_for_safety_review(
    coordinator_id: int | str, reference: str, *, session: Session | None = None
) -> EventRequest:
    """Send an approved event to the Safety Officer (SCRUM-97 AC1, AC2, ADR-0047).

    Only the event's assigned coordinator may. The event must be approved, have at
    least one venue arranged, every active arrangement approved (a Withdrawn one is
    ignored) and every equipment request an outcome from Technical Support; an event
    with no equipment requests passes that check. The ``safety_review`` status and a
    ``safety_review_requested`` history entry naming the coordinator are saved in one
    commit.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, now ``safety_review``.

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own.
        SafetyReviewNotAllowedError: 409 — the event isn't approved, or a venue or
            equipment check fails; ``details`` names each one that fails.
    """
    sess = resolve_session(session)
    event_request = _event_request_assigned_to(coordinator_id, reference, sess)
    if event_request.status is not EventRequestStatus.APPROVED:
        raise SafetyReviewNotAllowedError(NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE)

    held_back = _arrangement_gaps(event_request.id, sess)
    if held_back:
        raise SafetyReviewNotAllowedError(SAFETY_REVIEW_NOT_READY_MESSAGE, details=held_back)

    event_request.status = EventRequestStatus.SAFETY_REVIEW
    record_event_history(
        event_request,
        EventHistoryKind.SAFETY_REVIEW_REQUESTED,
        actor_id=int(coordinator_id),
        session=sess,
    )
    sess.commit()
    _notify_safety_officers(event_request, sess)
    return event_request


# --------------------------------------------------------------------------
# SCRUM-97 part B — the Safety Officer's list of events awaiting review
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SafetyReviewEquipment:
    """One equipment request with its outcome, as the Safety Officer sees it (AC6).

    No ids: the equipment type is shown by name. ``status`` and ``provided_quantity``
    are Technical Support's outcome, which exists for every request of an event in
    Safety Review (ADR-0047).
    """

    equipment_type_name: str
    quantity: int
    notes: str | None
    status: EquipmentLineStatus
    provided_quantity: int | None
    outcome_note: str | None


@dataclass(frozen=True)
class EventAwaitingSafetyReview:
    """An event in Safety Review with the venues and equipment under review (AC6).

    The event's own fields carry its date, times, expected attendance and
    accessibility needs.
    """

    event_request: EventRequest
    venues: list[ArrangedVenue]
    equipment: list[SafetyReviewEquipment]


def _equipment_for_safety_review(
    event_request: EventRequest, session: Session
) -> list[SafetyReviewEquipment]:
    """The event's equipment requests in the order added, each with its type's name."""
    type_names = {}
    for equipment_type in equipment_services.list_equipment_types(session=session):
        type_names[equipment_type.id] = equipment_type.name

    equipment = []
    for line in event_request.equipment_lines:
        equipment.append(
            SafetyReviewEquipment(
                equipment_type_name=type_names[line.equipment_type_id],
                quantity=line.quantity,
                notes=line.notes,
                status=line.status,
                provided_quantity=line.provided_quantity,
                outcome_note=line.outcome_note,
            )
        )
    return equipment


def list_events_awaiting_safety_review(
    *, session: Session | None = None
) -> list[EventAwaitingSafetyReview]:
    """The events in Safety Review, soonest first (SCRUM-97 AC5, AC6, ADR-0047).

    Ordered by the event's date, then start time, then as submitted. One list for all
    Safety Officers. An event the Safety Officer has approved stays in Safety Review
    until it is confirmed, but is no longer awaiting them, so it is left out
    (SCRUM-98). Each event comes with its active venue arrangements and its
    equipment requests with their outcomes; the venues are read through the venue
    module's service.

    Args:
        session: Database session; defaults to ``db.session``.
    """
    from app.modules.venue import services as venue_services  # circular at import time

    sess = resolve_session(session)
    stmt = (
        select(EventRequest)
        .where(EventRequest.status == EventRequestStatus.SAFETY_REVIEW)
        .order_by(EventRequest.proposed_date, EventRequest.start_time, EventRequest.id)
    )
    awaiting = []
    for event_request in sess.scalars(stmt):
        if has_safety_approval(event_request.id, session=sess):
            continue
        awaiting.append(
            EventAwaitingSafetyReview(
                event_request=event_request,
                venues=venue_services.list_arranged_venues(event_request.id, session=sess),
                equipment=_equipment_for_safety_review(event_request, sess),
            )
        )
    return awaiting


# --------------------------------------------------------------------------
# SCRUM-98 — record the operational safety check outcome
# --------------------------------------------------------------------------

NOT_IN_SAFETY_REVIEW_MESSAGE = "Only an event in Safety Review can get a safety outcome."
ALREADY_SAFETY_APPROVED_MESSAGE = "The Safety Officer has already approved this event."


class SafetyOutcomeNotAllowedError(AppError):
    """The event isn't in Safety Review, or is already approved (409)."""

    status_code = 409
    error_code = "safety_outcome_not_allowed"


#: Where each outcome leaves the event. An approval keeps it in Safety Review for
#: the coordinator to confirm (SCRUM-49); the others return it to planning, which is
#: ``approved``, never to Rejected (AC5, AC6, ADR-0047).
STATUS_AFTER_SAFETY_OUTCOME = {
    SafetyOutcome.APPROVED: EventRequestStatus.SAFETY_REVIEW,
    SafetyOutcome.REJECTED: EventRequestStatus.APPROVED,
    SafetyOutcome.CHANGES_REQUESTED: EventRequestStatus.APPROVED,
}
#: What the assigned coordinator is told for each outcome (AC8).
NOTIFICATION_BY_SAFETY_OUTCOME = {
    SafetyOutcome.APPROVED: NotificationKind.SAFETY_CHECK_APPROVED,
    SafetyOutcome.REJECTED: NotificationKind.SAFETY_CHECK_REJECTED,
    SafetyOutcome.CHANGES_REQUESTED: NotificationKind.SAFETY_CHANGES_REQUESTED,
}


def record_safety_outcome(
    officer_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> EventRequest:
    """Record the Safety Officer's outcome for an event in Safety Review (SCRUM-98).

    AC1-AC8. The checklist is required with every outcome, and a reason unless it is
    an approval. An approval leaves the event in Safety Review, approved; Reject and
    Request Changes return it to planning (``approved``). A
    ``safety_outcome_recorded`` history entry, naming the officer and keeping the
    outcome, checklist and reason, is saved with the status. The assigned coordinator
    is told afterwards, with the reason (ADR-0015).

    Args:
        officer_id: The Safety Officer's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``outcome``, ``checklist`` and ``reason``.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The request, in the status the outcome leaves it in.

    Raises:
        ValidationError: 400 — invalid payload, a checklist note missing or blank, or
            no reason for Reject or Request Changes.
        NotFoundError: 404 — no such request, or it is still a draft.
        SafetyOutcomeNotAllowedError: 409 — the event isn't in Safety Review, or the
            Safety Officer has already approved it.
    """
    recorded = load_or_raise(RecordSafetyOutcomeSchema(), payload)
    sess = resolve_session(session)
    event_request = _event_request_for_staff(reference, sess)
    if event_request.status is not EventRequestStatus.SAFETY_REVIEW:
        raise SafetyOutcomeNotAllowedError(NOT_IN_SAFETY_REVIEW_MESSAGE)
    if has_safety_approval(event_request.id, session=sess):
        raise SafetyOutcomeNotAllowedError(ALREADY_SAFETY_APPROVED_MESSAGE)

    outcome = recorded["outcome"]
    event_request.status = STATUS_AFTER_SAFETY_OUTCOME[outcome]
    record_event_history(
        event_request,
        EventHistoryKind.SAFETY_OUTCOME_RECORDED,
        actor_id=int(officer_id),
        details={
            "outcome": outcome.value,
            "checklist": recorded["checklist"],
            "reason": recorded["reason"],
        },
        session=sess,
        now=now,
    )
    sess.commit()
    _notify_assigned_coordinator(
        event_request, NOTIFICATION_BY_SAFETY_OUTCOME[outcome], sess, detail=recorded["reason"]
    )
    return event_request


# --------------------------------------------------------------------------
# SCRUM-55 — the event facts behind an event's list of registrants
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EventCapacity:
    """An event's id and capacity, for the list of who registered (SCRUM-55 AC4).

    ``capacity`` is ``None`` for an event that never had one set (SCRUM-69).
    """

    id: int
    capacity: int | None


def _events_the_viewer_runs(
    viewer_id: int | str, viewer_role: Role, session: Session
) -> ColumnElement[bool]:
    """The events an organiser or a coordinator is responsible for (SCRUM-55 AC1, AC2).

    An organiser's are their client organisation's (ADR-0020), a coordinator's those
    assigned to them (ADR-0034).
    """
    if viewer_role is Role.EVENT_COORDINATOR:
        return _assigned_to(viewer_id)
    return _visible_to_organiser(viewer_id, session)


def get_event_capacity_for_viewer(
    viewer_id: int | str, reference: str, *, viewer_role: Role, session: Session | None = None
) -> EventCapacity:
    """The event's id and capacity, if the viewer is responsible for it (SCRUM-55).

    An Event Organiser is responsible for their client organisation's events, an Event
    Coordinator for those assigned to them. An event that isn't the viewer's gets the
    same 404 as a reference that doesn't exist (ADR-0012).

    Args:
        viewer_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        viewer_role: The caller's role: an organiser or a coordinator.
        session: Database session; defaults to ``db.session``.

    Raises:
        NotFoundError: 404 — no such event, or none among the viewer's own.
        OrganiserWithoutOrganisationError: 403 — the organiser has no organisation.
    """
    sess = resolve_session(session)
    belongs_to = _events_the_viewer_runs(viewer_id, viewer_role, sess)
    event_request = _event_request_by_reference(reference, sess, belongs_to=belongs_to)
    return EventCapacity(id=event_request.id, capacity=event_request.registration_capacity)


# --------------------------------------------------------------------------
# SCRUM-49 — confirm an event once its arrangements are in place
# --------------------------------------------------------------------------

NOT_IN_SAFETY_REVIEW_FOR_CONFIRMATION_MESSAGE = "Only an event in Safety Review can be confirmed."
CONFIRMATION_NOT_READY_MESSAGE = (
    "The event can be confirmed once the Safety Officer has approved it, every venue "
    "arrangement is approved and every equipment request has an outcome from Technical "
    "Support."
)
SAFETY_NOT_APPROVED_GAP = "The Safety Officer has not approved the event."


class EventConfirmationNotAllowedError(AppError):
    """The event isn't in Safety Review, or its approvals aren't all in (409)."""

    status_code = 409
    error_code = "confirmation_not_allowed"


def confirm_event_request(
    coordinator_id: int | str, reference: str, *, session: Session | None = None
) -> EventRequest:
    """Confirm an event once its venue, equipment and safety are approved (SCRUM-49).

    Only the event's assigned coordinator may, and only by asking: nothing confirms an
    event on its own (AC3). The event must be in Safety Review with the Safety
    Officer's approval (``has_safety_approval``), have at least one venue arranged,
    every active arrangement Approved (a Withdrawn one is ignored) and every equipment
    request an outcome; an event with no equipment requests passes that check (AC2).
    The ``confirmed`` status and an ``event_confirmed`` history entry naming the
    coordinator are saved in one commit. The organiser who submitted the request is
    told afterwards (AC12, ADR-0015).

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, now ``confirmed``.

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own.
        EventConfirmationNotAllowedError: 409 — the event isn't in Safety Review, or
            an approval is missing; ``details`` names each gap under ``safety_check``,
            ``venue_arrangements`` and ``equipment``.
    """
    sess = resolve_session(session)
    event_request = _event_request_assigned_to(coordinator_id, reference, sess)
    if event_request.status is not EventRequestStatus.SAFETY_REVIEW:
        raise EventConfirmationNotAllowedError(NOT_IN_SAFETY_REVIEW_FOR_CONFIRMATION_MESSAGE)

    held_back = {}
    if not has_safety_approval(event_request.id, session=sess):
        held_back["safety_check"] = [SAFETY_NOT_APPROVED_GAP]
    held_back.update(_arrangement_gaps(event_request.id, sess))
    if held_back:
        raise EventConfirmationNotAllowedError(CONFIRMATION_NOT_READY_MESSAGE, details=held_back)

    event_request.status = EventRequestStatus.CONFIRMED
    record_event_history(
        event_request,
        EventHistoryKind.EVENT_CONFIRMED,
        actor_id=int(coordinator_id),
        session=sess,
    )
    sess.commit()
    _raise_notifications(
        [event_request.organiser_id], event_request, NotificationKind.EVENT_CONFIRMED, sess
    )
    return event_request


# --------------------------------------------------------------------------
# SCRUM-49 AC9, AC10 — reject an event during planning
# --------------------------------------------------------------------------

#: Planning runs from the coordinator's approval to confirmation: the event is Approved
#: while its venues and equipment are arranged, then in Safety Review (ADR-0047). A
#: request still awaiting its first decision is rejected through SCRUM-31's decision,
#: and a confirmed event is past planning: it would be cancelled (SCRUM-61).
PLANNING_STATUSES: frozenset[EventRequestStatus] = frozenset(
    {EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW}
)
NOT_IN_PLANNING_FOR_REJECTION_MESSAGE = (
    "Only an approved event or one in Safety Review can be rejected during planning."
)


class EventRejectionNotAllowedError(AppError):
    """The event isn't in planning, so it can't be rejected this way (409)."""

    status_code = 409
    error_code = "rejection_not_allowed"


def _release_arrangements(event_id: int, coordinator_id: int, session: Session) -> None:
    """Free the venues and equipment of an event that won't run, without committing.

    Its venue arrangements are withdrawn or released, bookings and holds included, and
    its reserved equipment goes back to stock (SCRUM-49 AC10). Written for a rejection
    during planning; SCRUM-61's cancellation releases the same things, "as for a
    cancelled event", so it is meant to share this. Open equipment requests close with
    the event's status (``EQUIPMENT_NOT_NEEDED_STATUSES``), not here.
    """
    from app.modules.venue import services as venue_services  # circular at import time

    venue_services.release_event_arrangements(
        event_id, coordinator_id=coordinator_id, session=session
    )
    equipment_services.release_event_reservations(event_id, session=session)


def reject_event_during_planning(
    coordinator_id: int | str,
    reference: str,
    payload: Mapping[str, Any] | None,
    *,
    session: Session | None = None,
) -> EventRequest:
    """Reject an event whose essential arrangements can't be met (SCRUM-49 AC9, AC10).

    Only the event's assigned coordinator may, and only by asking: nothing rejects an
    event on its own. The event must be in planning, Approved or in Safety Review, and
    a reason is required. The rejection is a decision, like SCRUM-31's: the
    ``rejected`` status and a ``decision_recorded`` entry with the coordinator and the
    reason, so it is the event's current decision. In the same commit its venue
    arrangements are released or withdrawn and its reserved equipment returned, as for
    a cancelled event (SCRUM-61, ADR-0093); its open equipment requests close with the
    status (SCRUM-48 AC8). The organiser who submitted the request is told afterwards,
    with the reason (ADR-0015). The checks run in this order: the reference, the
    coordinator, the status, then the payload.

    Args:
        coordinator_id: The caller's user id, taken from their token.
        reference: The ``EVR-…`` reference; case and surrounding spaces are ignored.
        payload: Decoded JSON body: ``reason``.
        session: Database session; defaults to ``db.session``.

    Returns:
        The request, now ``rejected``.

    Raises:
        NotFoundError: 404 — no such request among the coordinator's own.
        EventRejectionNotAllowedError: 409 — the event isn't Approved or in Safety
            Review.
        ValidationError: 400 — no reason, or a field the body may not carry.
    """
    sess = resolve_session(session)
    event_request = _event_request_assigned_to(coordinator_id, reference, sess)
    if event_request.status not in PLANNING_STATUSES:
        raise EventRejectionNotAllowedError(NOT_IN_PLANNING_FOR_REJECTION_MESSAGE)
    rejection = load_or_raise(RejectEventSchema(), payload)

    decision = {"outcome": DecisionOutcome.REJECTED, "reason": rejection["reason"]}
    _apply_decision(coordinator_id, event_request, decision, sess)
    _release_arrangements(event_request.id, int(coordinator_id), sess)
    sess.commit()
    _notify_organiser_of_decision(event_request, decision, sess)
    return event_request
