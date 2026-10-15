"""Unit tests for SCRUM-24 AC7: an Attendee's events, upcoming and past (ADR-0044).

``list_my_registrations`` reads the query's ``when``. ``upcoming``, the default, lists
the events that haven't ended, soonest first; ``past`` lists the ones that have, most
recent first. An event has ended once now reaches its end. Ties go by the event's id.

Runs against ``db_session`` at ``now``: Wednesday 14 October 2026, 12:00 in Singapore.
Events are saved, and registered for, in an order that is neither the expected one nor
the order of their ids, so a list that isn't sorted can't pass by luck.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.events.models import EventRequest
from app.modules.registration.models import Registration
from app.modules.registration.services import MyRegistration, list_my_registrations

pytestmark = pytest.mark.scrum_24

MakeOpenEvent = Callable[..., EventRequest]
MakeRegistration = Callable[..., Registration]
MyRegistrations = Callable[..., list[MyRegistration]]

ATTENDEE = 21
TODAY = date(2026, 10, 14)
EARLY_OCTOBER = date(2026, 10, 1)


def _names(rows: list[MyRegistration]) -> list[str]:
    return [row.name for row in rows]


# --------------------------------------------------------------------------
# Upcoming and past
# --------------------------------------------------------------------------


def test_upcoming_is_the_default_and_lists_the_soonest_event_first(
    now: datetime,
    my_registrations: MyRegistrations,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    latest = make_open_event(name="22 Oct", day=date(2026, 10, 22))
    soonest = make_open_event(name="20 Oct", day=date(2026, 10, 20))
    middle = make_open_event(name="21 Oct", day=date(2026, 10, 21))
    make_registration(soonest, ATTENDEE, registered_at=now - timedelta(days=3))
    make_registration(latest, ATTENDEE, registered_at=now - timedelta(days=2))
    make_registration(middle, ATTENDEE, registered_at=now - timedelta(days=1))

    expected = ["20 Oct", "21 Oct", "22 Oct"]
    assert _names(my_registrations(ATTENDEE)) == expected
    assert _names(my_registrations(ATTENDEE, {"when": "upcoming"})) == expected


def test_past_lists_the_events_that_have_ended_most_recent_first(
    my_registrations: MyRegistrations,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    first = make_open_event(name="1 Oct", day=EARLY_OCTOBER)
    fifth = make_open_event(name="5 Oct", day=date(2026, 10, 5))
    third = make_open_event(name="3 Oct", day=date(2026, 10, 3))
    still_to_come = make_open_event(name="20 Oct")
    for event in (third, still_to_come, first, fifth):
        make_registration(event, ATTENDEE)

    assert _names(my_registrations(ATTENDEE, {"when": "past"})) == ["5 Oct", "3 Oct", "1 Oct"]


def test_an_event_is_past_once_now_reaches_its_end(
    my_registrations: MyRegistrations,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    ended = make_open_event(name="Ended at noon", day=TODAY, start=time(9, 0), end=time(12, 0))
    running = make_open_event(name="Still running", day=TODAY, start=time(10, 0), end=time(13, 0))
    make_registration(ended, ATTENDEE)
    make_registration(running, ATTENDEE)

    assert _names(my_registrations(ATTENDEE)) == ["Still running"]
    assert _names(my_registrations(ATTENDEE, {"when": "past"})) == ["Ended at noon"]


def test_upcoming_events_starting_together_are_in_id_order(
    my_registrations: MyRegistrations,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    first = make_open_event(name="First saved")
    second = make_open_event(name="Second saved")
    make_registration(second, ATTENDEE)
    make_registration(first, ATTENDEE)

    assert _names(my_registrations(ATTENDEE)) == ["First saved", "Second saved"]


def test_past_events_starting_together_are_in_reverse_id_order(
    my_registrations: MyRegistrations,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    first = make_open_event(name="First saved", day=EARLY_OCTOBER)
    second = make_open_event(name="Second saved", day=EARLY_OCTOBER)
    make_registration(first, ATTENDEE)
    make_registration(second, ATTENDEE)

    assert _names(my_registrations(ATTENDEE, {"when": "past"})) == ["Second saved", "First saved"]


def test_the_real_clock_decides_what_has_ended_when_no_time_is_given(
    db_session: Session, make_open_event: MakeOpenEvent, make_registration: MakeRegistration
) -> None:
    make_registration(make_open_event(name="Long over", day=date(2000, 1, 1)), ATTENDEE)
    make_registration(make_open_event(name="Far off", day=date(2099, 1, 1)), ATTENDEE)

    rows = list_my_registrations(ATTENDEE, {}, session=db_session)

    assert _names(rows) == ["Far off"]


# --------------------------------------------------------------------------
# Bad input is a 400 naming the query parameter
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "details"),
    [
        ({"when": "today"}, {"when": ["Must be one of: upcoming, past."]}),
        ({"colour": "red"}, {"colour": ["Unknown field."]}),
    ],
    ids=["unknown window", "unknown parameter"],
)
def test_bad_query_parameters_are_a_validation_error_naming_the_parameter(
    my_registrations: MyRegistrations, params: dict[str, str], details: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        my_registrations(ATTENDEE, params)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == details
