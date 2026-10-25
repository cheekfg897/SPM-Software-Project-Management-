"""Unit tests for the event facts the events module gives the registration module.

SCRUM-52 needs to know which events Attendees may register for (AC1, AC4), to lock the
one an Attendee is registering for so the last place goes to one of two (SCRUM-54 AC4),
and to name the events an Attendee has registered for (AC5). The registration module
never reads the events table (module boundary), so it asks these functions (ADR-0032).

Runs against ``db_session`` with the events saved by ``make_open_event``; the lock is
checked on the SQL a ``mock_session`` is given, because SQLite cannot hold a row lock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    EventHeading,
    RegistrableEvent,
    get_registrable_event_for_update,
    list_event_headings,
    list_registrable_events,
)
from tests.events.cases import UNCONFIRMED_STATUSES

pytestmark = pytest.mark.scrum_52

MakeOpenEvent = Callable[..., EventRequest]

STARTS_AT = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# list_registrable_events — confirmed, registration enabled, not yet ended
# --------------------------------------------------------------------------


def test_a_registrable_event_is_described_with_its_times_and_capacity(
    now: datetime, db_session: Session, open_event: EventRequest
) -> None:
    events = list_registrable_events(session=db_session, now=now)

    assert events == [
        RegistrableEvent(
            id=open_event.id,
            reference="EVR-OPEN0001",
            name="Jazz by the Bay",
            description="An evening of music.",
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
            capacity=100,
        )
    ]


@pytest.mark.parametrize("status", UNCONFIRMED_STATUSES, ids=lambda status: status.value)
def test_only_confirmed_events_are_registrable(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent, status: EventRequestStatus
) -> None:
    make_open_event(name="Open event")
    make_open_event(name="Not confirmed", status=status)

    events = list_registrable_events(session=db_session, now=now)

    assert [event.name for event in events] == ["Open event"]


def test_only_events_with_registration_enabled_are_registrable(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Open event")
    make_open_event(name="Registration off", enabled=False)

    events = list_registrable_events(session=db_session, now=now)

    assert [event.name for event in events] == ["Open event"]


def test_a_registrable_event_with_no_description_has_an_empty_one(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    event = make_open_event()
    event.description = None
    db_session.commit()

    assert list_registrable_events(session=db_session, now=now)[0].description == ""


def test_registrable_events_are_soonest_first_and_leave_out_those_that_have_ended(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Later", day=date(2026, 10, 21))
    make_open_event(name="Sooner", day=date(2026, 10, 20))
    make_open_event(name="Ended", day=date(2026, 10, 14), start=time(9, 0), end=time(11, 0))

    events = list_registrable_events(session=db_session, now=now)

    assert [event.name for event in events] == ["Sooner", "Later"]


def test_registrable_events_are_searched_by_name_or_description_ignoring_case(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Jazz by the Bay", description="Standards.")
    make_open_event(name="Orchid Masterclass", description="With the JAZZ club.")
    make_open_event(name="Poetry Night", description="Verse.")

    events = list_registrable_events(search="jazz", session=db_session, now=now)

    assert sorted(event.name for event in events) == ["Jazz by the Bay", "Orchid Masterclass"]


def test_registrable_events_are_bounded_by_their_start(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    for name, hour in [("Ten", 10), ("Two", 14), ("Six", 18)]:
        make_open_event(name=name, start=time(hour, 0), end=time(hour, 30))
    two_pm = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)

    events = list_registrable_events(
        starts_from=two_pm, starts_to=two_pm, session=db_session, now=now
    )

    assert [event.name for event in events] == ["Two"]


def test_the_real_clock_decides_what_has_ended_when_no_time_is_given(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Long over", day=date(2000, 1, 1))
    make_open_event(name="Far off", day=date(2099, 1, 1))

    events = list_registrable_events(session=db_session)

    assert [event.name for event in events] == ["Far off"]


# --------------------------------------------------------------------------
# get_registrable_event_for_update — one event, its row locked
# --------------------------------------------------------------------------


def test_the_event_being_registered_for_is_found_by_its_id(
    now: datetime, db_session: Session, open_event: EventRequest
) -> None:
    event = get_registrable_event_for_update(open_event.id, session=db_session, now=now)

    assert (event.id, event.name, event.capacity) == (open_event.id, "Jazz by the Bay", 100)


@pytest.mark.parametrize("status", UNCONFIRMED_STATUSES, ids=lambda status: status.value)
def test_an_event_that_is_not_confirmed_is_not_found_for_registering(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent, status: EventRequestStatus
) -> None:
    event = make_open_event(status=status)

    with pytest.raises(NotFoundError) as exc_info:
        get_registrable_event_for_update(event.id, session=db_session, now=now)

    assert exc_info.value.message == "Event not found."


def test_an_event_without_registration_enabled_is_not_found_for_registering(
    now: datetime, db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    event = make_open_event(enabled=False)

    with pytest.raises(NotFoundError):
        get_registrable_event_for_update(event.id, session=db_session, now=now)


def test_the_real_clock_decides_whether_the_event_has_ended_when_no_time_is_given(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    far_off = make_open_event(name="Far off", day=date(2099, 1, 1))
    long_over = make_open_event(name="Long over", day=date(2000, 1, 1))

    found = get_registrable_event_for_update(far_off.id, session=db_session)

    assert found.name == "Far off"
    with pytest.raises(NotFoundError):
        get_registrable_event_for_update(long_over.id, session=db_session)


def test_an_unknown_event_is_not_found_for_registering(now: datetime, db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        get_registrable_event_for_update(9999, session=db_session, now=now)


def test_the_event_row_is_locked_while_an_attendee_registers(
    now: datetime, mock_session: MagicMock, make_open_event: MakeOpenEvent
) -> None:
    mock_session.scalar.return_value = make_open_event()

    get_registrable_event_for_update(1, session=mock_session, now=now)

    statement = mock_session.scalar.call_args.args[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))


# --------------------------------------------------------------------------
# list_event_headings — what an Attendee's registrations say about each event
# --------------------------------------------------------------------------


def test_event_headings_give_each_event_its_name_times_status_and_cut_off(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    """Poetry's withdrawals close a day before it starts (SCRUM-69 AC6)."""
    jazz = make_open_event(name="Jazz")
    poetry = make_open_event(name="Poetry", day=date(2026, 10, 21), cut_off=STARTS_AT)
    make_open_event(name="Not asked for")

    headings = list_event_headings([jazz.id, poetry.id], session=db_session)

    assert sorted(headings, key=lambda heading: heading.id) == [
        EventHeading(
            id=jazz.id,
            reference="EVR-OPEN0001",
            name="Jazz",
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
            status="confirmed",
            withdrawal_cut_off=None,
        ),
        EventHeading(
            id=poetry.id,
            reference="EVR-OPEN0002",
            name="Poetry",
            starts_at=datetime(2026, 10, 21, 11, 30, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc),
            status="confirmed",
            withdrawal_cut_off=STARTS_AT,
        ),
    ]


def test_event_headings_include_an_event_that_is_no_longer_open(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    event = make_open_event(name="Done", status=EventRequestStatus.COMPLETED)

    headings = list_event_headings([event.id], session=db_session)

    assert [(heading.name, heading.status) for heading in headings] == [("Done", "completed")]
