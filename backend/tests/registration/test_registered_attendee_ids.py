"""Unit tests for ``list_registered_attendee_ids``, who holds a place at an event.

The events module asks for them to tell every registered Attendee when the event is
cancelled (SCRUM-61 AC4, ADR-0122). Only a place still held counts: an Attendee who
withdrew (SCRUM-53) has no place to lose. Runs against ``db_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import EventRequest
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import list_registered_attendee_ids

pytestmark = pytest.mark.scrum_61

MakeRegistration = Callable[..., Registration]


@pytest.fixture()
def two_events(make_open_event: Callable[..., EventRequest]) -> list[EventRequest]:
    """Two events open for registration."""
    return [make_open_event(), make_open_event()]


def test_every_attendee_holding_a_place_is_listed_oldest_registration_first(
    db_session: Session,
    saved_attendees: list[User],
    two_events: list[EventRequest],
    make_registration: MakeRegistration,
    now: datetime,
) -> None:
    event = two_events[0]
    make_registration(event, 21, registered_at=now)
    make_registration(event, 22, registered_at=now - timedelta(hours=1))

    assert list_registered_attendee_ids(event.id, session=db_session) == [22, 21]


def test_an_attendee_who_withdrew_is_left_out(
    db_session: Session,
    saved_attendees: list[User],
    two_events: list[EventRequest],
    make_registration: MakeRegistration,
    save: Callable[..., None],
) -> None:
    event = two_events[0]
    make_registration(event, 20)
    withdrawn = make_registration(event, 21)
    withdrawn.status = RegistrationStatus.WITHDRAWN
    save(withdrawn)

    assert list_registered_attendee_ids(event.id, session=db_session) == [20]


def test_another_events_attendees_are_left_out(
    db_session: Session,
    saved_attendees: list[User],
    two_events: list[EventRequest],
    make_registration: MakeRegistration,
) -> None:
    event, other_event = two_events
    make_registration(other_event, 20)

    assert list_registered_attendee_ids(event.id, session=db_session) == []
