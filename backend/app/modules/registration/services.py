"""Business logic for the registration module (SCRUM-52).

These functions are the module's public API: routes call them, tests call them
directly, and the events module calls :func:`count_registered` and
:func:`list_registered_attendee_ids`.

Facts about events come from :mod:`app.modules.events.services`, never from the events
table (module boundary). Every function takes an optional ``session`` so unit tests can
pass their own database session; in production the default ``db.session`` is used.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.clock import as_utc, local_today, to_business_time
from app.common.database import resolve_session
from app.common.errors import AppError, NotFoundError
from app.common.validation import load_or_raise
from app.modules.auth.permissions import Role
from app.modules.auth.services import get_user_contacts
from app.modules.events.services import (
    EventHeading,
    RegistrableEvent,
    find_public_event,
    get_event_capacity_for_viewer,
    get_registrable_event_for_update,
    list_event_headings,
    list_registrable_events,
)
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.schemas import (
    CatalogueQuerySchema,
    CatalogueWindow,
    MyEventsWindow,
    MyRegistrationsQuerySchema,
)
from app.modules.venue.services import BookedVenue, list_booked_venues

ALREADY_REGISTERED_MESSAGE = "You are already registered for this event."
EVENT_FULL_MESSAGE = "This event is full."
REGISTRATION_NOT_FOUND_MESSAGE = "Registration not found."
ALREADY_WITHDRAWN_MESSAGE = "You have already withdrawn from this event."
WITHDRAWAL_CLOSED_MESSAGE = "Withdrawals for this event have closed."
MY_EVENT_NOT_FOUND_MESSAGE = "Event not found."

#: The statuses of an event a change sent back to planning, where places stay held
#: (ADR-0087): its page says the arrangements are being reviewed (SCRUM-24 AC11,
#: ADR-0109). Plain values: the events module's models are not imported (module
#: boundary).
BEING_REVIEWED_EVENT_STATUSES = frozenset({"approved", "safety_review"})
#: The event statuses whose page offers Withdraw: the event is still going ahead,
#: confirmed or being reviewed (ADR-0109).
WITHDRAWABLE_EVENT_STATUSES = frozenset({"confirmed"}) | BEING_REVIEWED_EVENT_STATUSES

#: Monday is 0 and Sunday is 6, as :meth:`datetime.date.weekday` counts.
SATURDAY = 5
SUNDAY = 6


class AlreadyRegisteredError(AppError):
    """The Attendee already holds a place at this event (409)."""

    status_code = 409
    error_code = "already_registered"


class EventFullError(AppError):
    """The event has no places left (409)."""

    status_code = 409
    error_code = "event_full"


class AlreadyWithdrawnError(AppError):
    """The Attendee has already withdrawn from this event (409)."""

    status_code = 409
    error_code = "already_withdrawn"


class WithdrawalClosedError(AppError):
    """Withdrawals for this event have closed (409)."""

    status_code = 409
    error_code = "withdrawal_closed"


@dataclass(frozen=True)
class CatalogueEntry:
    """One event in the catalogue, with its places counted (ADR-0032)."""

    id: int
    reference: str
    name: str
    description: str
    starts_at: datetime
    ends_at: datetime
    capacity: int
    places_left: int
    is_full: bool
    is_registered: bool


@dataclass(frozen=True)
class CataloguePage:
    """One page of the catalogue and the totals behind it (ADR-0032)."""

    items: list[CatalogueEntry]
    page: int
    page_size: int
    total: int
    total_pages: int


@dataclass(frozen=True)
class MyRegistration:
    """One of an attendee's registrations, with the event it is for."""

    event_id: int
    reference: str
    name: str
    starts_at: datetime
    ends_at: datetime
    event_status: str
    status: RegistrationStatus
    registered_at: datetime
    withdrawn_at: datetime | None


@dataclass(frozen=True)
class MyRegistrationList:
    """The registrations in one of an attendee's windows, and which window it is."""

    when: MyEventsWindow
    registrations: list[MyRegistration]


@dataclass(frozen=True)
class MyRegisteredEvent:
    """An event an attendee registered for, as its page shows it (SCRUM-24 AC11).

    What SCRUM-52 shows of any event, its booked venues, the attendee's own
    registration, when withdrawals close, whether the page offers Withdraw, and
    whether the event's arrangements are being reviewed after a change (ADR-0109).
    Nothing from the event's internal planning.
    """

    id: int
    reference: str
    name: str
    description: str
    starts_at: datetime
    ends_at: datetime
    event_status: str
    venues: list[BookedVenue]
    status: RegistrationStatus
    registered_at: datetime
    withdrawn_at: datetime | None
    withdrawals_close_at: datetime
    can_withdraw: bool
    is_being_reviewed: bool


@dataclass(frozen=True)
class Registrant:
    """One person's registration, as the people running the event see it (SCRUM-55 AC3).

    No user id: the Attendee is shown by name and email.
    """

    name: str
    email: str
    registered_at: datetime
    status: RegistrationStatus


@dataclass(frozen=True)
class RegistrantList:
    """An event's registrants and places, for its organiser and coordinator (SCRUM-55).

    ``capacity`` and ``places_left`` are ``None`` for an event that never had a capacity
    set (SCRUM-69).
    """

    capacity: int | None
    registered_count: int
    places_left: int | None
    items: list[Registrant]


# --------------------------------------------------------------------------
# Counting places
# --------------------------------------------------------------------------


def count_registered(event_id: int, *, session: Session | None = None) -> int:
    """How many places are taken at an event.

    The events module calls this to keep a capacity from dropping below it
    (SCRUM-69 AC5, ADR-0043).
    """
    stmt = select(func.count(Registration.id)).where(
        Registration.event_request_id == event_id,
        Registration.status == RegistrationStatus.REGISTERED,
    )
    return resolve_session(session).scalar(stmt)


def list_registered_attendee_ids(event_id: int, *, session: Session | None = None) -> list[int]:
    """The Attendees holding a place at an event, oldest registration first.

    The events module calls this to tell each of them when the event is cancelled
    (SCRUM-61 AC4, ADR-0122). An Attendee who withdrew holds no place, so is left out.
    """
    stmt = (
        select(Registration.attendee_id)
        .where(
            Registration.event_request_id == event_id,
            Registration.status == RegistrationStatus.REGISTERED,
        )
        .order_by(Registration.registered_at, Registration.id)
    )
    return list(resolve_session(session).scalars(stmt))


def _registered_counts(event_ids: list[int], session: Session) -> dict[int, int]:
    """How many places are taken at each event; an event nobody joined is absent."""
    stmt = (
        select(Registration.event_request_id, func.count(Registration.id))
        .where(
            Registration.event_request_id.in_(event_ids),
            Registration.status == RegistrationStatus.REGISTERED,
        )
        .group_by(Registration.event_request_id)
    )
    counts = {}
    for event_id, taken in session.execute(stmt):
        counts[event_id] = taken
    return counts


def _events_held_by(
    attendee_id: int | str | None, event_ids: list[int], session: Session
) -> set[int]:
    """The ids among ``event_ids`` the attendee holds a place at; none for a visitor."""
    if attendee_id is None:
        return set()
    stmt = select(Registration.event_request_id).where(
        Registration.attendee_id == int(attendee_id),
        Registration.event_request_id.in_(event_ids),
        Registration.status == RegistrationStatus.REGISTERED,
    )
    return set(session.scalars(stmt))


# --------------------------------------------------------------------------
# The catalogue (SCRUM-52 AC1)
# --------------------------------------------------------------------------


def _window_dates(window: CatalogueWindow, today: date) -> tuple[date, date] | None:
    """The first and last business dates a preset covers, or ``None`` for no limit."""
    if window is CatalogueWindow.UPCOMING:
        return None
    if window is CatalogueWindow.TODAY:
        return today, today
    sunday = today + timedelta(days=SUNDAY - today.weekday())
    if window is CatalogueWindow.THIS_WEEK:
        return today, sunday
    # This weekend: the coming Saturday, or today if the weekend has started.
    days_to_saturday = max(SATURDAY - today.weekday(), 0)
    return today + timedelta(days=days_to_saturday), sunday


def _starts_between(
    query: Mapping[str, Any], today: date
) -> tuple[datetime | None, datetime | None]:
    """The earliest and latest start the query allows, as UTC instants (ADR-0032).

    A custom range replaces the preset; a time sent without an offset is business time.
    """
    if "starts_from" in query or "starts_to" in query:
        starts_from = query.get("starts_from")
        starts_to = query.get("starts_to")
        return (
            as_utc(starts_from) if starts_from is not None else None,
            as_utc(starts_to) if starts_to is not None else None,
        )

    dates = _window_dates(query.get("when", CatalogueWindow.UPCOMING), today)
    if dates is None:
        return None, None
    first_date, last_date = dates
    return (
        as_utc(datetime.combine(first_date, time.min)),
        as_utc(datetime.combine(last_date, time.max)),
    )


def _as_entry(event: RegistrableEvent, taken: int, is_registered: bool) -> CatalogueEntry:
    """The event with its places counted: a full event has none left, never fewer."""
    places_left = max(event.capacity - taken, 0)
    return CatalogueEntry(
        id=event.id,
        reference=event.reference,
        name=event.name,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        capacity=event.capacity,
        places_left=places_left,
        is_full=places_left == 0,
        is_registered=is_registered,
    )


def list_catalogue(
    params: Mapping[str, Any],
    viewer_id: int | str | None,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> CataloguePage:
    """One page of the events an attendee may register for, soonest first (SCRUM-52).

    Only confirmed events with registration enabled that haven't ended are listed. A
    full event stays listed, shown as full, so a place freed by a withdrawal can be
    taken (ADR-0032). The searching, the date windows, the paging and every count are
    done here, never by the client.

    Args:
        params: The query string: ``q``, ``when``, ``starts_from``, ``starts_to``,
            ``page`` and ``page_size``, all optional.
        viewer_id: Who is asking, from their token; ``None`` for a visitor.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The page, with the totals for the whole catalogue.

    Raises:
        ValidationError: 400 — a parameter is invalid (details per parameter).
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)
    query = load_or_raise(CatalogueQuerySchema(), params)
    starts_from, starts_to = _starts_between(query, local_today(now))

    events = list_registrable_events(
        search=query.get("q", ""),
        starts_from=starts_from,
        starts_to=starts_to,
        session=sess,
        now=now,
    )

    page = query["page"]
    page_size = query["page_size"]
    first = (page - 1) * page_size
    on_page = events[first : first + page_size]
    event_ids = [event.id for event in on_page]
    taken = _registered_counts(event_ids, sess)
    held = _events_held_by(viewer_id, event_ids, sess)

    items = []
    for event in on_page:
        items.append(_as_entry(event, taken.get(event.id, 0), event.id in held))
    return CataloguePage(
        items=items,
        page=page,
        page_size=page_size,
        total=len(events),
        total_pages=math.ceil(len(events) / page_size),
    )


# --------------------------------------------------------------------------
# Registering (SCRUM-52 AC2, AC3, AC4; SCRUM-54 AC1, AC2, AC4)
# --------------------------------------------------------------------------


def _registration_of(attendee_id: int, event_id: int, session: Session) -> Registration | None:
    """The attendee's row for the event, held or withdrawn, or ``None``."""
    stmt = select(Registration).where(
        Registration.event_request_id == event_id,
        Registration.attendee_id == attendee_id,
    )
    return session.scalars(stmt).first()


def _commit_or_already_registered(session: Session) -> None:
    """Commit; a second registration the check missed is a 409 too (SCRUM-52 AC3)."""
    # The event is locked and the attendee has just been checked, so the only integrity
    # error left here is the unique (event, attendee) pair.
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AlreadyRegisteredError(ALREADY_REGISTERED_MESSAGE) from exc


def register_for_event(
    attendee_id: int | str,
    event_id: int,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> Registration:
    """Register an attendee for an event that is open for registration (SCRUM-52).

    The account is the registration information (ADR-0032). The event's row is locked
    from the first read to the commit, so of two attendees asking for the last place
    one waits, then finds it taken (SCRUM-54 AC4). Someone who already holds a place is
    told so even if the event is also full. Someone who withdrew gets their row back,
    since the pair (event, attendee) is unique (SCRUM-53, ADR-0032).

    Args:
        attendee_id: The caller's user id, taken from their token.
        event_id: The event to register for.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The saved :class:`Registration`.

    Raises:
        NotFoundError: 404 — no such event, it isn't confirmed with registration
            enabled, or it has already ended (AC4).
        AlreadyRegisteredError: 409 — the attendee already holds a place (AC3).
        EventFullError: 409 — no places are left (SCRUM-54 AC2).
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)

    event = get_registrable_event_for_update(event_id, session=sess, now=now)
    registration = _registration_of(int(attendee_id), event.id, sess)
    if registration is not None and registration.status is RegistrationStatus.REGISTERED:
        raise AlreadyRegisteredError(ALREADY_REGISTERED_MESSAGE)
    if count_registered(event.id, session=sess) >= event.capacity:
        raise EventFullError(EVENT_FULL_MESSAGE)

    if registration is None:
        registration = Registration(event_request_id=event.id, attendee_id=int(attendee_id))
        sess.add(registration)
    registration.status = RegistrationStatus.REGISTERED
    registration.registered_at = now
    registration.withdrawn_at = None
    _commit_or_already_registered(sess)
    return registration


# --------------------------------------------------------------------------
# Withdrawing (SCRUM-53 AC2-AC5)
# --------------------------------------------------------------------------


def _withdrawal_closes_at(event: EventHeading) -> datetime:
    """When the attendees of ``event`` can no longer withdraw (SCRUM-53 AC2, AC3, AC5).

    The withdrawal cut-off the coordinator recorded (SCRUM-69 AC6), or the event's start
    when there is none. A cut-off left after the start, because the event has since
    moved earlier, gives way to the start (ADR-0086). An event that has started cannot
    be withdrawn from, so a completed one cannot either (AC5).
    """
    if event.withdrawal_cut_off is None:
        return event.starts_at
    return min(event.withdrawal_cut_off, event.starts_at)


def withdraw_registration(
    attendee_id: int | str,
    event_id: int,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> Registration:
    """Withdraw an attendee's place at an event, freeing it for someone else (SCRUM-53).

    The row is kept with status ``withdrawn``; only held places are counted, so the
    place returns to the event's capacity (AC4). A refusal once withdrawals have closed
    says when they closed, in business time (AC3).

    Args:
        attendee_id: The caller's user id, taken from their token.
        event_id: The event to withdraw from.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The withdrawn :class:`Registration`.

    Raises:
        NotFoundError: 404 — the attendee never registered for the event.
        AlreadyWithdrawnError: 409 — they have already withdrawn.
        WithdrawalClosedError: 409 — withdrawals have closed; ``details`` says when.
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)

    registration = _registration_of(int(attendee_id), event_id, sess)
    if registration is None:
        raise NotFoundError(REGISTRATION_NOT_FOUND_MESSAGE)
    if registration.status is RegistrationStatus.WITHDRAWN:
        raise AlreadyWithdrawnError(ALREADY_WITHDRAWN_MESSAGE)
    event = list_event_headings([event_id], session=sess)[0]
    closes_at = _withdrawal_closes_at(event)
    if now >= closes_at:
        shown = to_business_time(closes_at).isoformat()
        raise WithdrawalClosedError(
            WITHDRAWAL_CLOSED_MESSAGE, details={"withdrawal_closed_at": shown}
        )

    registration.status = RegistrationStatus.WITHDRAWN
    registration.withdrawn_at = now
    sess.commit()
    return registration


# --------------------------------------------------------------------------
# An attendee's own registrations (SCRUM-52 AC5)
# --------------------------------------------------------------------------


def _headings_by_id(
    registrations: Iterable[Registration], session: Session
) -> dict[int, EventHeading]:
    """The heading of each event the registrations are for, by event id."""
    event_ids = [registration.event_request_id for registration in registrations]
    headings = {}
    for heading in list_event_headings(event_ids, session=session):
        headings[heading.id] = heading
    return headings


def _by_start(row: MyRegistration) -> tuple[datetime, int]:
    """Sort key: the event's start, then its id for events that start together."""
    return (row.starts_at, row.event_id)


def _in_window(
    rows: list[MyRegistration], window: MyEventsWindow, now: datetime
) -> list[MyRegistration]:
    """The rows in ``window``, in that window's order (ADR-0044).

    An event has ended once ``now`` reaches its end, as the catalogue decides it.
    Upcoming events come soonest first, past ones most recent first.
    """
    if window is MyEventsWindow.PAST:
        ended = [row for row in rows if now >= row.ends_at]
        return sorted(ended, key=_by_start, reverse=True)
    not_ended = [row for row in rows if now < row.ends_at]
    return sorted(not_ended, key=_by_start)


def list_my_registrations(
    attendee_id: int | str,
    params: Mapping[str, Any],
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> MyRegistrationList:
    """List an attendee's upcoming or past registrations (SCRUM-52 AC5, SCRUM-24 AC7).

    ``when`` picks the events that haven't ended, soonest first (the default), or the
    ones that have, most recent first (ADR-0044). SCRUM-53 reads the same list to show
    each registration with its status.

    Args:
        attendee_id: The caller's user id, taken from their token.
        params: The query string: ``when``, optional.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The window, and one :class:`MyRegistration` per registration in it, with its
        event's name, times and status.

    Raises:
        ValidationError: 400 — ``when`` isn't ``upcoming`` or ``past``, or a parameter
            is unknown (details per parameter).
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)
    query = load_or_raise(MyRegistrationsQuerySchema(), params)
    stmt = select(Registration).where(Registration.attendee_id == int(attendee_id))
    registrations = list(sess.scalars(stmt))
    headings = _headings_by_id(registrations, sess)

    rows = []
    for registration in registrations:
        heading = headings[registration.event_request_id]
        rows.append(
            MyRegistration(
                event_id=heading.id,
                reference=heading.reference,
                name=heading.name,
                starts_at=heading.starts_at,
                ends_at=heading.ends_at,
                event_status=heading.status,
                status=registration.status,
                registered_at=registration.registered_at,
                withdrawn_at=registration.withdrawn_at,
            )
        )
    window = query["when"]
    return MyRegistrationList(when=window, registrations=_in_window(rows, window, now))


# --------------------------------------------------------------------------
# One event an attendee registered for (SCRUM-24 AC11)
# --------------------------------------------------------------------------


def _may_withdraw(registration: Registration, event: EventHeading, now: datetime) -> bool:
    """Whether the page offers Withdraw, as SCRUM-53 allows it (ADR-0109).

    The place is still held, the event is still going ahead, and its withdrawals
    haven't closed: the cut-off, or the start when there is none. A Completed or
    Cancelled event is read-only (AC11).
    """
    if registration.status is not RegistrationStatus.REGISTERED:
        return False
    if event.status not in WITHDRAWABLE_EVENT_STATUSES:
        return False
    return now < _withdrawal_closes_at(event)


def get_my_registered_event(
    attendee_id: int | str,
    reference: str,
    *,
    session: Session | None = None,
    now: datetime | None = None,
) -> MyRegisteredEvent:
    """One event the attendee registered for, whatever its status (SCRUM-24 AC11).

    Someone who withdrew still opens it, read-only (ADR-0109). An event they never
    registered for is not found, in the same words as one that doesn't exist, so
    whether it exists can't be told (ADR-0012).

    Args:
        attendee_id: The caller's user id, taken from their token.
        reference: The event's ``EVR-`` reference; case and spaces are ignored.
        session: Database session; defaults to ``db.session``.
        now: The current instant, timezone-aware; defaults to the real clock.

    Returns:
        The event as its page shows it.

    Raises:
        NotFoundError: 404 — no such event, or the attendee never registered for it.
    """
    sess = resolve_session(session)
    if now is None:
        now = datetime.now(timezone.utc)

    event = find_public_event(reference, session=sess)
    if event is None:
        raise NotFoundError(MY_EVENT_NOT_FOUND_MESSAGE)
    registration = _registration_of(int(attendee_id), event.id, sess)
    if registration is None:
        raise NotFoundError(MY_EVENT_NOT_FOUND_MESSAGE)

    return MyRegisteredEvent(
        id=event.id,
        reference=event.reference,
        name=event.name,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        event_status=event.status,
        venues=list_booked_venues(event.id, session=sess),
        status=registration.status,
        registered_at=registration.registered_at,
        withdrawn_at=registration.withdrawn_at,
        withdrawals_close_at=_withdrawal_closes_at(event),
        can_withdraw=_may_withdraw(registration, event, now),
        is_being_reviewed=event.status in BEING_REVIEWED_EVENT_STATUSES,
    )


# --------------------------------------------------------------------------
# Who has registered for an event (SCRUM-55)
# --------------------------------------------------------------------------


def _places_left(capacity: int | None, registered_count: int) -> int | None:
    """Places still free: none left rather than fewer, and ``None`` with no capacity."""
    if capacity is None:
        return None
    return max(capacity - registered_count, 0)


def list_registrants(
    viewer_id: int | str,
    reference: str,
    *,
    viewer_role: Role,
    session: Session | None = None,
) -> RegistrantList:
    """List who has registered for an event, oldest registration first (SCRUM-55).

    Only an Event Organiser of the event's client organisation (AC1) and the event's
    assigned Event Coordinator (AC2) may. Each registrant shows their name, email,
    registration date and status (AC3), beside the number registered and the capacity
    (AC4). The Attendee role never reaches this: the route refuses it (AC5).

    Args:
        viewer_id: The caller's user id, taken from their token.
        reference: The event's ``EVR-…`` reference; case and spaces are ignored.
        viewer_role: The caller's role: an organiser or a coordinator.
        session: Database session; defaults to ``db.session``.

    Returns:
        The registrants and the event's places.

    Raises:
        NotFoundError: 404 — no such event, or none among the viewer's own (ADR-0012).
        OrganiserWithoutOrganisationError: 403 — the organiser has no client
            organisation (ADR-0020).
    """
    sess = resolve_session(session)
    event = get_event_capacity_for_viewer(
        viewer_id, reference, viewer_role=viewer_role, session=sess
    )
    stmt = (
        select(Registration)
        .where(Registration.event_request_id == event.id)
        .order_by(Registration.registered_at, Registration.id)
    )
    registrations = list(sess.scalars(stmt))
    contacts = get_user_contacts(
        [registration.attendee_id for registration in registrations], session=sess
    )

    items = []
    for registration in registrations:
        contact = contacts[registration.attendee_id]
        items.append(
            Registrant(
                name=contact.full_name,
                email=contact.email,
                registered_at=registration.registered_at,
                status=registration.status,
            )
        )
    registered_count = count_registered(event.id, session=sess)
    return RegistrantList(
        capacity=event.capacity,
        registered_count=registered_count,
        places_left=_places_left(event.capacity, registered_count),
        items=items,
    )
