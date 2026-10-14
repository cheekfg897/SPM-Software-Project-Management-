"""Unit tests for SCRUM-52 "Register for a confirmed event", the catalogue.

AC1: an Attendee (or a visitor) sees the name, description, date and time of every
confirmed event with registration enabled, and no other (ADR-0032). The catalogue is
soonest first, never lists an event that has ended, and is searched, filtered and paged
by the backend. ``places_left``, ``is_full`` and ``is_registered`` come from the real
registrations; a full event stays listed (ADR-0032). SCRUM-54 AC1 and AC2 show the
event as full.

``venue`` is always ``null`` until the venue stack merges (ADR-0032), so a search by
venue name matches nothing yet.

Runs against ``db_session`` with ``now`` pinned to Wednesday 14 October 2026, 12:00 in
Singapore. Events default to Tuesday 20 October at 19:30.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.registration.models import Registration
from app.modules.registration.services import CataloguePage, list_catalogue
from tests.events.cases import UNCONFIRMED_STATUSES

pytestmark = pytest.mark.scrum_52

Catalogue = Callable[..., CataloguePage]
MakeOpenEvent = Callable[..., EventRequest]
MakeRegistration = Callable[..., Registration]

VIEWER = 21
OTHER_ATTENDEE = 22

WEDNESDAY = date(2026, 10, 14)
THURSDAY = date(2026, 10, 15)
SATURDAY = date(2026, 10, 17)
SUNDAY = date(2026, 10, 18)
NEXT_MONDAY = date(2026, 10, 19)

#: 10:00 on Saturday 17 October in Singapore, and 10:00 on Sunday 18 October.
SATURDAY_MORNING = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)
SUNDAY_MORNING = datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc)


@pytest.fixture()
def catalogue(db_session: Session, now: datetime) -> Catalogue:
    """The catalogue page for ``params`` as ``viewer`` sees it, at ``at`` or ``now``."""

    def _catalogue(
        params: dict[str, str] | None = None,
        viewer: int | str | None = None,
        *,
        at: datetime | None = None,
    ) -> CataloguePage:
        moment = at if at is not None else now
        return list_catalogue(params or {}, viewer, session=db_session, now=moment)

    return _catalogue


def _names(page: CataloguePage) -> list[str]:
    return [item.name for item in page.items]


def test_the_real_clock_decides_what_has_ended_when_no_time_is_given(
    db_session: Session, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Long over", day=date(2000, 1, 1))
    make_open_event(name="Far off", day=date(2099, 1, 1))

    page = list_catalogue({}, None, session=db_session)

    assert _names(page) == ["Far off"]


# --------------------------------------------------------------------------
# AC1 — only confirmed events with registration enabled, with what the attendee sees
# --------------------------------------------------------------------------


def test_an_open_event_is_listed_with_what_an_attendee_needs_to_see(
    catalogue: Catalogue, open_event: EventRequest
) -> None:
    page = catalogue()

    assert len(page.items) == 1
    item = page.items[0]
    assert item.id == open_event.id
    assert item.reference == "EVR-OPEN0001"
    assert item.name == "Jazz by the Bay"
    assert item.description == "An evening of music."
    assert item.starts_at == datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
    assert item.ends_at == datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
    assert item.capacity == 100
    assert item.places_left == 100
    assert item.is_full is False
    assert item.is_registered is False


@pytest.mark.parametrize("status", UNCONFIRMED_STATUSES, ids=lambda status: status.value)
def test_an_event_that_is_not_confirmed_is_not_listed(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, status: EventRequestStatus
) -> None:
    make_open_event(name="Open event")
    make_open_event(name="Not confirmed", status=status)

    assert _names(catalogue()) == ["Open event"]


def test_a_confirmed_event_without_registration_enabled_is_not_listed(
    catalogue: Catalogue, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Open event")
    make_open_event(name="Registration off", enabled=False)

    assert _names(catalogue()) == ["Open event"]


def test_an_event_with_no_description_is_listed_with_an_empty_one(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, db_session: Session
) -> None:
    event = make_open_event()
    event.description = None
    db_session.commit()

    assert catalogue().items[0].description == ""


def test_the_catalogue_lists_the_soonest_event_first(
    catalogue: Catalogue, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Later that day", day=date(2026, 10, 20), start=time(21, 0))
    make_open_event(name="The next day", day=date(2026, 10, 21), start=time(9, 0))
    make_open_event(name="That morning", day=date(2026, 10, 20), start=time(8, 0), end=time(9, 0))

    assert _names(catalogue()) == ["That morning", "Later that day", "The next day"]


def test_an_event_that_has_ended_is_not_listed(
    catalogue: Catalogue, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Ended this morning", day=WEDNESDAY, start=time(7, 0), end=time(9, 0))
    make_open_event(
        name="Ends at this very moment", day=WEDNESDAY, start=time(10, 0), end=time(12, 0)
    )
    make_open_event(
        name="Ends a minute from now", day=WEDNESDAY, start=time(10, 0), end=time(12, 1)
    )
    make_open_event(name="Yesterday", day=date(2026, 10, 13))

    assert _names(catalogue()) == ["Ends a minute from now"]


# --------------------------------------------------------------------------
# SCRUM-54 AC1, AC2 — places left, full, and who is registered
# --------------------------------------------------------------------------


def test_places_left_counts_the_registrations(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, make_registration: MakeRegistration
) -> None:
    event = make_open_event(capacity=3)
    make_registration(event, 31)
    make_registration(event, 32)

    item = catalogue().items[0]

    assert (item.capacity, item.places_left, item.is_full) == (3, 1, False)


def test_a_full_event_stays_listed_and_is_shown_as_full(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, make_registration: MakeRegistration
) -> None:
    event = make_open_event(capacity=2)
    make_registration(event, 31)
    make_registration(event, 32)

    item = catalogue().items[0]

    assert (item.capacity, item.places_left, item.is_full) == (2, 0, True)


def test_places_left_is_never_below_zero_if_more_are_registered_than_the_capacity(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, make_registration: MakeRegistration
) -> None:
    """A capacity edited straight in the database can end up under the registrations."""
    event = make_open_event(capacity=1)
    make_registration(event, 31)
    make_registration(event, 32)

    item = catalogue().items[0]

    assert (item.places_left, item.is_full) == (0, True)


def test_registrations_of_another_event_do_not_use_up_places(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, make_registration: MakeRegistration
) -> None:
    busy = make_open_event(name="Busy", capacity=5, start=time(10, 0))
    quiet = make_open_event(name="Quiet", capacity=5, start=time(20, 0))
    make_registration(busy, 31)
    make_registration(busy, 32)
    make_registration(quiet, 33)

    items = {item.name: item.places_left for item in catalogue().items}

    assert items == {"Busy": 3, "Quiet": 4}


@pytest.mark.parametrize("viewer", [VIEWER, str(VIEWER)], ids=["number", "token-subject"])
def test_is_registered_is_true_only_for_the_events_the_viewer_holds_a_place_at(
    catalogue: Catalogue,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
    viewer: int | str,
) -> None:
    mine = make_open_event(name="Mine", start=time(10, 0))
    make_open_event(name="Not mine", start=time(20, 0))
    make_registration(mine, VIEWER)

    page = catalogue(viewer=viewer)

    assert {item.name: item.is_registered for item in page.items} == {
        "Mine": True,
        "Not mine": False,
    }


@pytest.mark.parametrize("viewer", [None, OTHER_ATTENDEE], ids=["visitor", "another attendee"])
def test_is_registered_is_false_for_a_visitor_and_for_someone_else(
    catalogue: Catalogue,
    open_event: EventRequest,
    make_registration: MakeRegistration,
    viewer: int | None,
) -> None:
    make_registration(open_event, VIEWER)

    assert catalogue(viewer=viewer).items[0].is_registered is False


# --------------------------------------------------------------------------
# Paging
# --------------------------------------------------------------------------


@pytest.fixture()
def five_events(make_open_event: MakeOpenEvent) -> None:
    """Five open events, ``Event 1`` soonest."""
    for number in range(1, 6):
        make_open_event(name=f"Event {number}", day=date(2026, 10, 20 + number))


def test_the_first_page_has_twelve_to_a_page_by_default(
    catalogue: Catalogue, five_events: None
) -> None:
    page = catalogue()

    assert (page.page, page.page_size, page.total, page.total_pages) == (1, 12, 5, 1)
    assert len(page.items) == 5


def test_a_page_holds_page_size_events_and_the_next_page_the_ones_after(
    catalogue: Catalogue, five_events: None
) -> None:
    first = catalogue({"page_size": "2"})
    last = catalogue({"page_size": "2", "page": "3"})

    assert _names(first) == ["Event 1", "Event 2"]
    assert (first.page, first.page_size, first.total, first.total_pages) == (1, 2, 5, 3)
    assert _names(last) == ["Event 5"]
    assert (last.page, last.total, last.total_pages) == (3, 5, 3)


def test_a_page_past_the_last_is_empty_with_the_real_totals(
    catalogue: Catalogue, five_events: None
) -> None:
    page = catalogue({"page_size": "2", "page": "4"})

    assert page.items == []
    assert (page.page, page.total, page.total_pages) == (4, 5, 3)


def test_an_empty_catalogue_has_no_events_and_no_pages(catalogue: Catalogue) -> None:
    page = catalogue()

    assert page.items == []
    assert (page.total, page.total_pages) == (0, 0)


def test_only_the_events_on_the_page_are_counted_for_places(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, make_registration: MakeRegistration
) -> None:
    make_open_event(name="First", day=date(2026, 10, 20))
    second = make_open_event(name="Second", day=date(2026, 10, 21), capacity=4)
    make_registration(second, VIEWER)

    page = catalogue({"page_size": "1", "page": "2"}, viewer=VIEWER)

    assert [(item.name, item.places_left, item.is_registered) for item in page.items] == [
        ("Second", 3, True)
    ]


# --------------------------------------------------------------------------
# Search — q
# --------------------------------------------------------------------------


@pytest.fixture()
def searchable_events(make_open_event: MakeOpenEvent) -> None:
    """Events named and described so each search term picks one of them out."""
    make_open_event(name="Jazz by the Bay", description="Standards and new work.")
    make_open_event(name="Orchid Masterclass", description="Repotting with the JAZZ club growers.")
    make_open_event(name="Poetry Night", description="Verse at the gallery.")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("jazz", ["Jazz by the Bay", "Orchid Masterclass"]),
        ("ORCHID", ["Orchid Masterclass"]),
        ("verse at", ["Poetry Night"]),
        ("  poetry  ", ["Poetry Night"]),
        ("", ["Jazz by the Bay", "Orchid Masterclass", "Poetry Night"]),
        ("sculpture", []),
    ],
    ids=["name and description", "ignores case", "description", "trimmed", "blank", "no match"],
)
def test_q_matches_the_name_and_description_ignoring_case(
    catalogue: Catalogue, searchable_events: None, text: str, expected: list[str]
) -> None:
    page = catalogue({"q": text})

    assert sorted(_names(page)) == sorted(expected)
    assert page.total == len(expected)


# --------------------------------------------------------------------------
# when — presets resolved in business time
# --------------------------------------------------------------------------


@pytest.fixture()
def events_across_the_week(make_open_event: MakeOpenEvent) -> None:
    """One event on each of Wed 14 (evening), Thu 15, Sat 17, Sun 18, Mon 19 October."""
    make_open_event(name="Wednesday", day=WEDNESDAY, start=time(18, 0), end=time(20, 0))
    make_open_event(name="Thursday", day=THURSDAY)
    make_open_event(name="Saturday", day=SATURDAY)
    make_open_event(name="Sunday", day=SUNDAY)
    make_open_event(name="Monday", day=NEXT_MONDAY)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (None, ["Wednesday", "Thursday", "Saturday", "Sunday", "Monday"]),
        ("upcoming", ["Wednesday", "Thursday", "Saturday", "Sunday", "Monday"]),
        ("today", ["Wednesday"]),
        ("this_week", ["Wednesday", "Thursday", "Saturday", "Sunday"]),
        ("this_weekend", ["Saturday", "Sunday"]),
    ],
)
def test_when_picks_a_window_counted_from_today_in_business_time(
    catalogue: Catalogue,
    events_across_the_week: None,
    when: str | None,
    expected: list[str],
) -> None:
    params = {} if when is None else {"when": when}

    assert _names(catalogue(params)) == expected


def test_today_follows_the_business_day_not_the_utc_day(
    catalogue: Catalogue, make_open_event: MakeOpenEvent
) -> None:
    # 23:30 on Wednesday in Singapore is 15:30 UTC; 00:30 on Thursday is 16:30 UTC,
    # still Wednesday there.
    make_open_event(name="Late Wednesday", day=WEDNESDAY, start=time(23, 30), end=time(23, 45))
    make_open_event(name="Early Thursday", day=THURSDAY, start=time(0, 30), end=time(1, 0))

    assert _names(catalogue({"when": "today"})) == ["Late Wednesday"]


def test_this_weekend_is_what_is_left_of_it_when_it_has_started(
    catalogue: Catalogue, events_across_the_week: None
) -> None:
    on_saturday = catalogue({"when": "this_weekend"}, at=SATURDAY_MORNING)
    on_sunday = catalogue({"when": "this_weekend"}, at=SUNDAY_MORNING)

    assert _names(on_saturday) == ["Saturday", "Sunday"]
    assert _names(on_sunday) == ["Sunday"]


def test_this_weekend_on_a_sunday_leaves_out_an_overnight_event_that_started_on_saturday(
    catalogue: Catalogue, make_open_event: MakeOpenEvent, db_session: Session
) -> None:
    """It is still running, but it did not start in what is left of the weekend."""
    overnight = make_open_event(name="Overnight", day=SATURDAY, start=time(22, 0), end=time(2, 0))
    overnight.end_date = SUNDAY
    db_session.commit()
    sunday_one_am = datetime(2026, 10, 17, 17, 0, tzinfo=timezone.utc)

    page = catalogue({"when": "this_weekend"}, at=sunday_one_am)

    assert _names(page) == []


def test_this_week_ends_on_sunday(catalogue: Catalogue, events_across_the_week: None) -> None:
    on_saturday = catalogue({"when": "this_week"}, at=SATURDAY_MORNING)
    on_sunday = catalogue({"when": "this_week"}, at=SUNDAY_MORNING)

    assert _names(on_saturday) == ["Saturday", "Sunday"]
    assert _names(on_sunday) == ["Sunday"]


def test_today_still_leaves_out_an_event_that_has_ended(
    catalogue: Catalogue, make_open_event: MakeOpenEvent
) -> None:
    make_open_event(name="Ended this morning", day=WEDNESDAY, start=time(7, 0), end=time(9, 0))
    make_open_event(name="This evening", day=WEDNESDAY, start=time(18, 0), end=time(20, 0))

    assert _names(catalogue({"when": "today"})) == ["This evening"]


# --------------------------------------------------------------------------
# starts_from and starts_to — a custom range on the start
# --------------------------------------------------------------------------


@pytest.fixture()
def events_by_hour(make_open_event: MakeOpenEvent) -> None:
    """Events starting at 10:00, 14:00 and 18:00 on 20 October (business time)."""
    for name, hour in [("Ten", 10), ("Two", 14), ("Six", 18)]:
        make_open_event(name=name, start=time(hour, 0), end=time(hour, 30))


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"starts_from": "2026-10-20T14:00"}, ["Two", "Six"]),
        ({"starts_to": "2026-10-20T14:00"}, ["Ten", "Two"]),
        ({"starts_from": "2026-10-20T10:01", "starts_to": "2026-10-20T17:59"}, ["Two"]),
        ({"starts_from": "2026-10-20T14:00", "starts_to": "2026-10-20T14:00"}, ["Two"]),
        ({"starts_from": "2026-10-20T14:00:00"}, ["Two", "Six"]),
        ({"starts_from": "2026-10-20T06:00:00+00:00"}, ["Two", "Six"]),
        ({"starts_to": "2026-10-20T06:00:00+00:00"}, ["Ten", "Two"]),
        ({"starts_from": "2026-10-21T00:00"}, []),
    ],
    ids=[
        "from",
        "to",
        "both",
        "one minute",
        "with seconds",
        "from with an offset",
        "to with an offset",
        "nothing in range",
    ],
)
def test_starts_from_and_starts_to_bound_the_start_inclusively(
    catalogue: Catalogue, events_by_hour: None, params: dict[str, str], expected: list[str]
) -> None:
    assert _names(catalogue(params)) == expected


def test_a_time_without_an_offset_is_read_as_business_time(
    catalogue: Catalogue, events_by_hour: None
) -> None:
    # 14:00 in Singapore is 06:00 UTC. Read as UTC, 14:00 would leave out "Two".
    without_offset = catalogue({"starts_from": "2026-10-20T14:00"})
    as_utc = catalogue({"starts_from": "2026-10-20T14:00:00+00:00"})

    assert _names(without_offset) == ["Two", "Six"]
    assert _names(as_utc) == []


# --------------------------------------------------------------------------
# Bad input is a 400 naming the query parameter
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "details"),
    [
        (
            {"starts_from": "2026-10-20T12:00", "starts_to": "2026-10-20T11:59"},
            {"starts_to": ["Must be after starts_from."]},
        ),
        (
            {"starts_from": "2026-10-20T12:00+08:00", "starts_to": "2026-10-20T03:00:00+00:00"},
            {"starts_to": ["Must be after starts_from."]},
        ),
        (
            {"when": "today", "starts_from": "2026-10-20T12:00"},
            {"when": ["Send either a preset or a custom range, not both."]},
        ),
        (
            {"when": "upcoming", "starts_to": "2026-10-20T12:00"},
            {"when": ["Send either a preset or a custom range, not both."]},
        ),
        (
            {"when": "tomorrow"},
            {"when": ["Must be one of: upcoming, today, this_week, this_weekend."]},
        ),
        ({"starts_from": "next week"}, {"starts_from": ["Not a valid date-time."]}),
        ({"starts_to": "2026-13-45T10:00"}, {"starts_to": ["Not a valid date-time."]}),
        ({"page": "0"}, {"page": ["Must be at least 1."]}),
        ({"page": "two"}, {"page": ["Not a valid integer."]}),
        ({"page_size": "many"}, {"page_size": ["Not a valid integer."]}),
        ({"page_size": "0"}, {"page_size": ["Must be between 1 and 50."]}),
        ({"page_size": "51"}, {"page_size": ["Must be between 1 and 50."]}),
        ({"colour": "red"}, {"colour": ["Unknown field."]}),
    ],
    ids=[
        "range ends before it starts",
        "range ends before it starts across offsets",
        "preset with a start",
        "upcoming with an end",
        "unknown preset",
        "start is not a date-time",
        "end is not a date",
        "page zero",
        "page not a number",
        "page size not a number",
        "page size zero",
        "page size over the maximum",
        "unknown parameter",
    ],
)
def test_bad_query_parameters_are_a_validation_error_naming_the_parameter(
    catalogue: Catalogue, params: dict[str, str], details: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        catalogue(params)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == details


def test_the_largest_page_size_is_accepted(catalogue: Catalogue, five_events: None) -> None:
    page = catalogue({"page_size": "50"})

    assert (page.page_size, page.total) == (50, 5)
