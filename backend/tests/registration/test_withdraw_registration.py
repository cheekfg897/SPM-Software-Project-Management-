"""Unit tests for SCRUM-53 "See and withdraw my registration".

AC1: an attendee sees each registration with its status, withdrawn ones included. AC2:
they can withdraw until the event's withdrawal cut-off, or until it starts when none is
set; the cut-off is optional and recorded by the coordinator (SCRUM-69 AC6, ADR-0032,
ADR-0086). AC3: a refusal says when withdrawals closed. AC4: a withdrawn place returns
to the event's capacity. AC5: nobody withdraws from an event already completed. AC6:
the Event Organiser sees the withdrawal. A withdrawal sets the row's status, nothing is
deleted, and registering again sets the same row back (ADR-0032).

Runs against ``db_session``, so the counts are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventRequest
from app.modules.registration import routes
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.schemas import MyEventsWindow
from app.modules.registration.services import (
    AlreadyWithdrawnError,
    EventFullError,
    MyRegistration,
    MyRegistrationList,
    WithdrawalClosedError,
    count_registered,
    list_catalogue,
    list_registrants,
    register_for_event,
    withdraw_registration,
)

pytestmark = pytest.mark.scrum_53

Act = Callable[[int, int], Registration]
RowsOf = Callable[[int], list[tuple[int, RegistrationStatus]]]
CallRoute = Callable[..., object]

ATTENDEE = 21
OTHER_ATTENDEE = 22

#: When the default open event starts: Tuesday 20 October 2026, 19:30 in Singapore.
EVENT_STARTS = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
#: When it ends, 22:00 in Singapore.
EVENT_ENDS = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
#: A withdrawal cut-off the day before, 19:30 in Singapore on Monday 19 October.
CUT_OFF = EVENT_STARTS - timedelta(days=1)

WITHDRAW_ENDPOINT = "registration.withdraw_from_catalogue_event"
WITHDRAW_PATH = "/api/events/catalogue/41/registrations"
WITHDRAW_KWARGS = {"event_id": 41}


@pytest.fixture()
def rows_of(db_session: Session) -> RowsOf:
    """Every registration row for an event, and its status, as committed.

    Rolls back first, so a change the service only flushed is not read back.
    """

    def _rows(event_id: int) -> list[tuple[int, RegistrationStatus]]:
        db_session.rollback()
        stmt = (
            select(Registration)
            .where(Registration.event_request_id == event_id)
            .order_by(Registration.id)
        )
        return [(row.attendee_id, row.status) for row in db_session.scalars(stmt)]

    return _rows


# --------------------------------------------------------------------------
# AC2 — an attendee withdraws; nothing is deleted
# --------------------------------------------------------------------------


def test_an_attendee_withdraws_their_registration(
    now: datetime, register: Act, withdraw: Act, open_event: EventRequest, rows_of: RowsOf
) -> None:
    register(ATTENDEE, open_event.id)

    registration = withdraw(ATTENDEE, open_event.id)

    assert registration.status is RegistrationStatus.WITHDRAWN
    assert registration.withdrawn_at == now
    assert rows_of(open_event.id) == [(ATTENDEE, RegistrationStatus.WITHDRAWN)]


def test_the_withdrawal_is_stamped_with_the_real_time_when_none_is_given(
    db_session: Session, register: Act, make_open_event: Callable[..., EventRequest]
) -> None:
    """The real clock decides, so the event is far off: open whenever this runs."""
    far_off = make_open_event(day=date(2099, 1, 1))
    register(ATTENDEE, far_off.id)

    registration = withdraw_registration(ATTENDEE, far_off.id, session=db_session)

    assert abs(registration.withdrawn_at - datetime.now(timezone.utc)) < timedelta(minutes=1)


def test_withdrawing_twice_is_refused(
    register: Act, withdraw: Act, open_event: EventRequest
) -> None:
    register(ATTENDEE, open_event.id)
    withdraw(ATTENDEE, open_event.id)

    with pytest.raises(AlreadyWithdrawnError) as exc_info:
        withdraw(ATTENDEE, open_event.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "already_withdrawn"
    assert exc_info.value.message == "You have already withdrawn from this event."


def test_an_attendee_cannot_withdraw_someone_elses_registration(
    register: Act, withdraw: Act, open_event: EventRequest, rows_of: RowsOf
) -> None:
    """The caller only names an event, so another attendee's place is never theirs."""
    register(ATTENDEE, open_event.id)

    with pytest.raises(NotFoundError) as exc_info:
        withdraw(OTHER_ATTENDEE, open_event.id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Registration not found."
    assert rows_of(open_event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


def test_withdrawing_touches_only_that_event_and_that_attendee(
    register: Act,
    withdraw: Act,
    make_open_event: Callable[..., EventRequest],
    rows_of: RowsOf,
) -> None:
    event = make_open_event()
    other_event = make_open_event()
    register(ATTENDEE, event.id)
    register(OTHER_ATTENDEE, event.id)
    register(ATTENDEE, other_event.id)

    withdraw(ATTENDEE, event.id)

    assert rows_of(event.id) == [
        (ATTENDEE, RegistrationStatus.WITHDRAWN),
        (OTHER_ATTENDEE, RegistrationStatus.REGISTERED),
    ]
    assert rows_of(other_event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


# --------------------------------------------------------------------------
# AC2, AC3 and AC5 — withdrawals close at the cut-off, or when the event starts
# --------------------------------------------------------------------------


def test_an_attendee_can_withdraw_until_the_moment_the_event_starts(
    db_session: Session, register: Act, open_event: EventRequest
) -> None:
    register(ATTENDEE, open_event.id)
    just_before = EVENT_STARTS - timedelta(seconds=1)

    registration = withdraw_registration(
        ATTENDEE, open_event.id, session=db_session, now=just_before
    )

    assert registration.status is RegistrationStatus.WITHDRAWN


@pytest.mark.parametrize(
    "moment",
    [EVENT_STARTS, EVENT_ENDS + timedelta(days=1)],
    ids=["as-it-starts", "once-completed"],
)
def test_withdrawing_is_refused_once_the_event_has_started(
    db_session: Session,
    register: Act,
    open_event: EventRequest,
    rows_of: RowsOf,
    moment: datetime,
) -> None:
    register(ATTENDEE, open_event.id)

    with pytest.raises(WithdrawalClosedError) as exc_info:
        withdraw_registration(ATTENDEE, open_event.id, session=db_session, now=moment)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "withdrawal_closed"
    assert exc_info.value.details == {"withdrawal_closed_at": "2026-10-20T19:30:00+08:00"}
    assert rows_of(open_event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


def test_an_attendee_can_withdraw_until_the_cut_off(
    db_session: Session, register: Act, make_open_event: Callable[..., EventRequest]
) -> None:
    event = make_open_event(cut_off=CUT_OFF)
    register(ATTENDEE, event.id)
    just_before = CUT_OFF - timedelta(seconds=1)

    registration = withdraw_registration(ATTENDEE, event.id, session=db_session, now=just_before)

    assert registration.status is RegistrationStatus.WITHDRAWN


@pytest.mark.parametrize(
    "moment", [CUT_OFF, EVENT_STARTS - timedelta(hours=1)], ids=["at-the-cut-off", "after-it"]
)
def test_withdrawing_is_refused_once_the_cut_off_has_passed_and_says_when(
    db_session: Session,
    register: Act,
    make_open_event: Callable[..., EventRequest],
    rows_of: RowsOf,
    moment: datetime,
) -> None:
    event = make_open_event(cut_off=CUT_OFF)
    register(ATTENDEE, event.id)

    with pytest.raises(WithdrawalClosedError) as exc_info:
        withdraw_registration(ATTENDEE, event.id, session=db_session, now=moment)

    assert exc_info.value.error_code == "withdrawal_closed"
    assert exc_info.value.details == {"withdrawal_closed_at": "2026-10-19T19:30:00+08:00"}
    assert rows_of(event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


def test_a_cut_off_left_after_the_start_by_a_change_of_date_closes_at_the_start(
    db_session: Session, register: Act, make_open_event: Callable[..., EventRequest]
) -> None:
    """The event moved earlier than its cut-off: withdrawals close as it starts."""
    event = make_open_event(cut_off=EVENT_STARTS + timedelta(hours=1))
    register(ATTENDEE, event.id)

    with pytest.raises(WithdrawalClosedError) as exc_info:
        withdraw_registration(ATTENDEE, event.id, session=db_session, now=EVENT_STARTS)

    assert exc_info.value.details == {"withdrawal_closed_at": "2026-10-20T19:30:00+08:00"}


# --------------------------------------------------------------------------
# AC4 — a withdrawn place returns to the event's capacity
# --------------------------------------------------------------------------


def test_a_withdrawal_frees_a_place_on_a_full_event(
    db_session: Session,
    register: Act,
    withdraw: Act,
    make_open_event: Callable[..., EventRequest],
) -> None:
    full_event = make_open_event(capacity=1)
    register(ATTENDEE, full_event.id)

    withdraw(ATTENDEE, full_event.id)
    register(OTHER_ATTENDEE, full_event.id)

    assert count_registered(full_event.id, session=db_session) == 1


def test_the_catalogue_shows_the_freed_place_and_the_attendee_as_not_registered(
    db_session: Session,
    now: datetime,
    register: Act,
    withdraw: Act,
    make_open_event: Callable[..., EventRequest],
) -> None:
    event = make_open_event(capacity=2)
    register(ATTENDEE, event.id)
    register(OTHER_ATTENDEE, event.id)

    withdraw(ATTENDEE, event.id)

    entry = list_catalogue({}, ATTENDEE, session=db_session, now=now).items[0]
    assert (entry.places_left, entry.is_full, entry.is_registered) == (1, False, False)


# --------------------------------------------------------------------------
# Registering again reuses the row (ADR-0032)
# --------------------------------------------------------------------------


def test_registering_again_after_withdrawing_reuses_the_row(
    db_session: Session,
    now: datetime,
    register: Act,
    open_event: EventRequest,
    rows_of: RowsOf,
) -> None:
    first = register(ATTENDEE, open_event.id)
    withdraw_registration(ATTENDEE, open_event.id, session=db_session, now=now)
    later = now + timedelta(hours=1)

    again = register_for_event(ATTENDEE, open_event.id, session=db_session, now=later)

    assert again.id == first.id
    assert again.status is RegistrationStatus.REGISTERED
    assert again.registered_at == later
    assert again.withdrawn_at is None
    assert rows_of(open_event.id) == [(ATTENDEE, RegistrationStatus.REGISTERED)]


def test_registering_again_is_refused_when_the_freed_place_was_taken(
    register: Act,
    withdraw: Act,
    make_open_event: Callable[..., EventRequest],
    rows_of: RowsOf,
) -> None:
    event = make_open_event(capacity=1)
    register(ATTENDEE, event.id)
    withdraw(ATTENDEE, event.id)
    register(OTHER_ATTENDEE, event.id)

    with pytest.raises(EventFullError):
        register(ATTENDEE, event.id)

    assert rows_of(event.id) == [
        (ATTENDEE, RegistrationStatus.WITHDRAWN),
        (OTHER_ATTENDEE, RegistrationStatus.REGISTERED),
    ]


def test_registering_again_is_refused_once_registration_is_closed(
    save: Callable[..., None],
    register: Act,
    withdraw: Act,
    open_event: EventRequest,
    rows_of: RowsOf,
) -> None:
    register(ATTENDEE, open_event.id)
    withdraw(ATTENDEE, open_event.id)
    open_event.registration_enabled = False
    save(open_event)

    with pytest.raises(NotFoundError):
        register(ATTENDEE, open_event.id)

    assert rows_of(open_event.id) == [(ATTENDEE, RegistrationStatus.WITHDRAWN)]


# --------------------------------------------------------------------------
# AC1 — the attendee's own list shows each registration with its status
# --------------------------------------------------------------------------


def test_my_list_shows_a_withdrawn_registration_with_its_status_and_when(
    now: datetime,
    register: Act,
    withdraw: Act,
    make_open_event: Callable[..., EventRequest],
    my_registrations: Callable[..., list[MyRegistration]],
) -> None:
    kept = make_open_event(name="Kept")
    dropped = make_open_event(name="Dropped")
    register(ATTENDEE, kept.id)
    register(ATTENDEE, dropped.id)

    withdraw(ATTENDEE, dropped.id)

    shown = {row.name: (row.status, row.withdrawn_at) for row in my_registrations(ATTENDEE)}
    assert shown == {
        "Kept": (RegistrationStatus.REGISTERED, None),
        "Dropped": (RegistrationStatus.WITHDRAWN, now),
    }


def test_the_catalogue_stops_showing_a_withdrawn_attendee_as_registered(
    db_session: Session,
    now: datetime,
    register: Act,
    withdraw: Act,
    open_event: EventRequest,
) -> None:
    register(ATTENDEE, open_event.id)
    before = list_catalogue({}, ATTENDEE, session=db_session, now=now)

    withdraw(ATTENDEE, open_event.id)

    after = list_catalogue({}, ATTENDEE, session=db_session, now=now)
    assert [entry.is_registered for entry in before.items] == [True]
    assert [entry.is_registered for entry in after.items] == [False]


# --------------------------------------------------------------------------
# AC6 — the Event Organiser sees the withdrawal in the event's registration list
# --------------------------------------------------------------------------


def test_the_organiser_sees_a_withdrawal_in_the_registration_list_but_it_is_not_counted(
    db_session: Session,
    register: Act,
    withdraw: Act,
    make_open_event: Callable[..., EventRequest],
    make_user: Callable[..., User],
    save: Callable[..., None],
    saved_users: list[User],
) -> None:
    """``saved_users`` has organiser 7, whose organisation owns these events."""
    event = make_open_event(capacity=5)
    save(
        make_user(
            email="alice@example.com", full_name="Alice Tan", role=Role.ATTENDEE, user_id=ATTENDEE
        )
    )
    save(
        make_user(
            email="bob@example.com", full_name="Bob Ong", role=Role.ATTENDEE, user_id=OTHER_ATTENDEE
        )
    )
    register(ATTENDEE, event.id)
    register(OTHER_ATTENDEE, event.id)

    withdraw(ATTENDEE, event.id)

    listing = list_registrants(
        7, event.reference, viewer_role=Role.EVENT_ORGANISER, session=db_session
    )
    assert [(row.name, row.status) for row in listing.items] == [
        ("Alice Tan", RegistrationStatus.WITHDRAWN),
        ("Bob Ong", RegistrationStatus.REGISTERED),
    ]
    assert (listing.registered_count, listing.places_left) == (1, 4)


# --------------------------------------------------------------------------
# DELETE /api/events/catalogue/<id>/registrations — attendees only, their own
# --------------------------------------------------------------------------


@pytest.fixture()
def attendee_token(token_for: Callable[..., str], make_user: Callable[..., User]) -> str:
    """A token for attendee 21."""
    return token_for(make_user(role=Role.ATTENDEE, user_id=ATTENDEE))


@pytest.fixture()
def withdraw_service(
    replace_services: Callable[..., dict[str, MagicMock]], now: datetime
) -> MagicMock:
    """Replace ``withdraw_registration`` with a mock returning a withdrawn one."""
    registration = Registration(
        id=7,
        event_request_id=41,
        attendee_id=ATTENDEE,
        status=RegistrationStatus.WITHDRAWN,
        registered_at=now,
        withdrawn_at=now,
    )
    mocks = replace_services(routes, {"withdraw_registration": registration})
    return mocks["withdraw_registration"]


def test_withdraw_route_allows_only_attendees(app: Flask) -> None:
    assert app.view_functions[WITHDRAW_ENDPOINT].allowed_roles == frozenset({"attendee"})


def test_withdrawing_answers_200_with_the_withdrawn_registration(
    call_route: CallRoute, withdraw_service: MagicMock, attendee_token: str
) -> None:
    response = call_route(
        WITHDRAW_ENDPOINT, "DELETE", WITHDRAW_PATH, WITHDRAW_KWARGS, attendee_token
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "id": 7,
        "event_id": 41,
        "status": "withdrawn",
        "registered_at": "2026-10-14T12:00:00+08:00",
        "withdrawn_at": "2026-10-14T12:00:00+08:00",
    }
    withdraw_service.assert_called_once_with("21", 41)


def test_other_roles_cannot_withdraw(
    call_route: CallRoute,
    token_for: Callable[..., str],
    withdraw_service: MagicMock,
    non_attendee_role: Role,
) -> None:
    with pytest.raises(AuthorizationError):
        call_route(
            WITHDRAW_ENDPOINT,
            "DELETE",
            WITHDRAW_PATH,
            WITHDRAW_KWARGS,
            token_for(role=non_attendee_role),
        )

    withdraw_service.assert_not_called()


def test_withdrawing_without_a_token_is_401(
    call_route: CallRoute, withdraw_service: MagicMock
) -> None:
    with pytest.raises(AuthenticationError):
        call_route(WITHDRAW_ENDPOINT, "DELETE", WITHDRAW_PATH, WITHDRAW_KWARGS, None)

    withdraw_service.assert_not_called()


# --------------------------------------------------------------------------
# GET /api/events/registrations — a withdrawn row, as the attendee's list sends it
# --------------------------------------------------------------------------


def test_my_list_sends_when_a_registration_was_withdrawn_in_business_time(
    call_route: CallRoute,
    replace_services: Callable[..., dict[str, MagicMock]],
    now: datetime,
    attendee_token: str,
) -> None:
    row = MyRegistration(
        event_id=41,
        reference="EVR-7K2M9Q4A",
        name="Jazz by the Bay",
        starts_at=EVENT_STARTS,
        ends_at=EVENT_ENDS,
        event_status="confirmed",
        status=RegistrationStatus.WITHDRAWN,
        registered_at=now - timedelta(days=1),
        withdrawn_at=now,
    )
    listing = MyRegistrationList(when=MyEventsWindow.UPCOMING, registrations=[row])
    replace_services(routes, {"list_my_registrations": listing})

    response = call_route(
        "registration.view_my_registrations", "GET", "/api/events/registrations", {}, attendee_token
    )

    shown = response.get_json()["registrations"][0]
    assert (shown["status"], shown["withdrawn_at"]) == ("withdrawn", "2026-10-14T12:00:00+08:00")
