"""Unit tests for SCRUM-52 AC5: the event appears in the Attendee's registrations.

``list_my_registrations`` is the Attendee's own list: the event's id, name, start, end
and status, the registration's status and when it was made. It is the list SCRUM-53
reads to show each registration with its current status (ADR-0032). Its upcoming and
past split and its order are SCRUM-24's, tested in ``test_attendee_events_list.py``
(ADR-0044).

Runs against ``db_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import MyRegistration

pytestmark = pytest.mark.scrum_52

MakeOpenEvent = Callable[..., EventRequest]
MakeRegistration = Callable[..., Registration]
MyRegistrations = Callable[..., list[MyRegistration]]

ATTENDEE = 21
OTHER_ATTENDEE = 22


def test_a_registration_shows_the_event_and_when_it_was_made(
    now: datetime,
    my_registrations: MyRegistrations,
    open_event: EventRequest,
    make_registration: MakeRegistration,
) -> None:
    make_registration(open_event, ATTENDEE)

    assert my_registrations(ATTENDEE) == [
        MyRegistration(
            event_id=open_event.id,
            name="Jazz by the Bay",
            starts_at=datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc),
            event_status="confirmed",
            status=RegistrationStatus.REGISTERED,
            registered_at=now,
        )
    ]


def test_the_list_holds_only_the_callers_registrations(
    my_registrations: MyRegistrations,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    mine = make_open_event(name="Mine")
    theirs = make_open_event(name="Theirs")
    make_registration(mine, ATTENDEE)
    make_registration(theirs, OTHER_ATTENDEE)

    assert [row.name for row in my_registrations(ATTENDEE)] == ["Mine"]
    assert [row.name for row in my_registrations(OTHER_ATTENDEE)] == ["Theirs"]


def test_the_attendee_id_from_the_token_is_read_as_a_number(
    my_registrations: MyRegistrations,
    open_event: EventRequest,
    make_registration: MakeRegistration,
) -> None:
    make_registration(open_event, ATTENDEE)

    assert [row.event_id for row in my_registrations("21")] == [open_event.id]


def test_an_event_that_has_since_completed_is_still_listed(
    my_registrations: MyRegistrations,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
    db_session: Session,
) -> None:
    event = make_open_event(name="Done")
    make_registration(event, ATTENDEE)
    event.status = EventRequestStatus.COMPLETED
    db_session.commit()

    rows = my_registrations(ATTENDEE)
    assert [(row.name, row.event_status) for row in rows] == [("Done", "completed")]


def test_an_attendee_with_no_registrations_has_an_empty_list(
    my_registrations: MyRegistrations, open_event: EventRequest
) -> None:
    assert my_registrations(ATTENDEE) == []
