"""Unit tests for SCRUM-52 "Register for a confirmed event", the registering itself.

AC2: an Attendee registers for an event, and the account is the registration
information (ADR-0032). AC3: nobody registers twice. AC4: an event that isn't confirmed,
or doesn't have registration enabled, can't be registered for. SCRUM-54 AC1 and AC2: the
last place can be taken and a full event refuses; AC4: of two Attendees asking for the
last place, one gets it.

Runs against ``db_session``, so the counts are real SQL. SQLite cannot hold a row lock
or run two transactions at once, so the race itself is not tested here; what is tested
is that the event row is locked (``tests/events/test_registrable_events.py``) and that
the database refuses a second registration the check missed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.registration import services
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import (
    AlreadyRegisteredError,
    EventFullError,
    register_for_event,
)
from tests.events.cases import UNCONFIRMED_STATUSES

pytestmark = pytest.mark.scrum_52

Register = Callable[[int | str, int], Registration]
RegistrationsOf = Callable[[int], list[tuple[int, RegistrationStatus]]]

ATTENDEE = 21
OTHER_ATTENDEE = 22
THIRD_ATTENDEE = 23

ALREADY_REGISTERED = "You are already registered for this event."
EVENT_FULL = "This event is full."
EVENT_NOT_FOUND = "Event not found."


@pytest.fixture()
def register(db_session: Session, now: datetime) -> Register:
    """Register an attendee for an event at ``now``."""

    def _register(attendee_id: int | str, event_id: int) -> Registration:
        return register_for_event(attendee_id, event_id, session=db_session, now=now)

    return _register


@pytest.fixture()
def registrations_of(db_session: Session) -> RegistrationsOf:
    """Who holds a place at an event, and their status, read back from the database."""

    def _registrations(event_id: int) -> list[tuple[int, RegistrationStatus]]:
        db_session.expire_all()
        stmt = (
            select(Registration)
            .where(Registration.event_request_id == event_id)
            .order_by(Registration.id)
        )
        return [(row.attendee_id, row.status) for row in db_session.scalars(stmt)]

    return _registrations


# --------------------------------------------------------------------------
# AC2 — an Attendee registers
# --------------------------------------------------------------------------


def test_an_attendee_registers_for_an_open_event(
    now: datetime,
    register: Register,
    open_event: EventRequest,
    registrations_of: RegistrationsOf,
) -> None:
    registration = register(ATTENDEE, open_event.id)

    assert registration.id is not None
    assert registration.event_request_id == open_event.id
    assert registration.attendee_id == ATTENDEE
    assert registration.status is RegistrationStatus.REGISTERED
    assert registration.registered_at == now
    assert registrations_of(open_event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


def test_the_registration_is_stamped_with_the_real_time_when_none_is_given(
    db_session: Session, open_event: EventRequest
) -> None:
    registration = register_for_event(ATTENDEE, open_event.id, session=db_session)

    assert abs(registration.registered_at - datetime.now(timezone.utc)) < timedelta(minutes=1)


def test_the_attendee_id_from_the_token_is_read_as_a_number(
    register: Register, open_event: EventRequest, registrations_of: RegistrationsOf
) -> None:
    register("21", open_event.id)

    assert registrations_of(open_event.id) == [(21, RegistrationStatus.REGISTERED)]


def test_two_attendees_both_register_for_the_same_event(
    register: Register, open_event: EventRequest, registrations_of: RegistrationsOf
) -> None:
    register(ATTENDEE, open_event.id)
    register(OTHER_ATTENDEE, open_event.id)

    assert registrations_of(open_event.id) == [
        (ATTENDEE, RegistrationStatus.REGISTERED),
        (OTHER_ATTENDEE, RegistrationStatus.REGISTERED),
    ]


# --------------------------------------------------------------------------
# AC3 — never twice for the same event
# --------------------------------------------------------------------------


def test_registering_twice_for_the_same_event_is_refused(
    register: Register, open_event: EventRequest, registrations_of: RegistrationsOf
) -> None:
    register(ATTENDEE, open_event.id)

    with pytest.raises(AlreadyRegisteredError) as exc_info:
        register(ATTENDEE, open_event.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "already_registered"
    assert exc_info.value.message == ALREADY_REGISTERED
    assert registrations_of(open_event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


def test_an_attendee_holding_the_last_place_is_told_they_are_registered_not_that_it_is_full(
    register: Register, make_open_event: Callable[..., EventRequest]
) -> None:
    event = make_open_event(capacity=1)
    register(ATTENDEE, event.id)

    with pytest.raises(AlreadyRegisteredError):
        register(ATTENDEE, event.id)


def test_the_database_refuses_a_second_registration_the_check_missed(
    register: Register,
    open_event: EventRequest,
    registrations_of: RegistrationsOf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(ATTENDEE, open_event.id)
    # What a second request that read "not registered" before the first committed
    # would do: skip the check and let the unique constraint decide.
    monkeypatch.setattr(services, "_check_not_registered", lambda *args, **kwargs: None)

    with pytest.raises(AlreadyRegisteredError) as exc_info:
        register(ATTENDEE, open_event.id)

    assert exc_info.value.message == ALREADY_REGISTERED
    assert registrations_of(open_event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


# --------------------------------------------------------------------------
# AC4 — only a confirmed event with registration enabled
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", UNCONFIRMED_STATUSES, ids=lambda status: status.value)
def test_an_event_that_is_not_confirmed_cannot_be_registered_for(
    register: Register,
    make_open_event: Callable[..., EventRequest],
    registrations_of: RegistrationsOf,
    status: EventRequestStatus,
) -> None:
    event = make_open_event(status=status)

    with pytest.raises(NotFoundError) as exc_info:
        register(ATTENDEE, event.id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_NOT_FOUND
    assert registrations_of(event.id) == []


def test_an_event_without_registration_enabled_cannot_be_registered_for(
    register: Register,
    make_open_event: Callable[..., EventRequest],
    registrations_of: RegistrationsOf,
) -> None:
    event = make_open_event(enabled=False)

    with pytest.raises(NotFoundError) as exc_info:
        register(ATTENDEE, event.id)

    assert exc_info.value.message == EVENT_NOT_FOUND
    assert registrations_of(event.id) == []


def test_an_event_that_has_already_ended_cannot_be_registered_for(
    register: Register,
    make_open_event: Callable[..., EventRequest],
    registrations_of: RegistrationsOf,
) -> None:
    # Confirmed and enabled, but over at 09:00 today; "now" is 12:00 in Singapore.
    event = make_open_event(day=date(2026, 10, 14), start=time(7, 0), end=time(9, 0))

    with pytest.raises(NotFoundError) as exc_info:
        register(ATTENDEE, event.id)

    assert exc_info.value.message == EVENT_NOT_FOUND
    assert registrations_of(event.id) == []


def test_an_event_that_does_not_exist_cannot_be_registered_for(register: Register) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        register(ATTENDEE, 9999)

    assert exc_info.value.message == EVENT_NOT_FOUND


# --------------------------------------------------------------------------
# SCRUM-54 AC1, AC2, AC4 — the last place, a full event
# --------------------------------------------------------------------------


def test_the_last_place_can_be_taken(
    register: Register,
    make_open_event: Callable[..., EventRequest],
    registrations_of: RegistrationsOf,
) -> None:
    event = make_open_event(capacity=2)
    register(ATTENDEE, event.id)

    register(OTHER_ATTENDEE, event.id)

    assert registrations_of(event.id) == [
        (ATTENDEE, RegistrationStatus.REGISTERED),
        (OTHER_ATTENDEE, RegistrationStatus.REGISTERED),
    ]


def test_a_full_event_refuses_another_attendee(
    register: Register,
    make_open_event: Callable[..., EventRequest],
    registrations_of: RegistrationsOf,
) -> None:
    event = make_open_event(capacity=2)
    register(ATTENDEE, event.id)
    register(OTHER_ATTENDEE, event.id)

    with pytest.raises(EventFullError) as exc_info:
        register(THIRD_ATTENDEE, event.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "event_full"
    assert exc_info.value.message == EVENT_FULL
    assert len(registrations_of(event.id)) == 2


def test_places_taken_at_another_event_do_not_fill_this_one(
    register: Register,
    make_open_event: Callable[..., EventRequest],
    make_registration: Callable[..., Registration],
    registrations_of: RegistrationsOf,
) -> None:
    full = make_open_event(name="Full", capacity=2)
    make_registration(full, OTHER_ATTENDEE)
    make_registration(full, THIRD_ATTENDEE)
    empty = make_open_event(name="Empty", capacity=2)

    register(ATTENDEE, empty.id)

    assert registrations_of(empty.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


def test_of_two_attendees_asking_for_the_last_place_exactly_one_gets_it(
    register: Register,
    make_open_event: Callable[..., EventRequest],
    registrations_of: RegistrationsOf,
) -> None:
    event = make_open_event(capacity=1)
    outcomes: list[int | str] = []

    for attendee_id in (ATTENDEE, OTHER_ATTENDEE):
        try:
            outcomes.append(register(attendee_id, event.id).attendee_id)
        except EventFullError:
            outcomes.append("full")

    assert outcomes == [ATTENDEE, "full"]
    assert registrations_of(event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]
