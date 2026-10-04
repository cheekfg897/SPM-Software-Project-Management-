"""Unit tests for SCRUM-67 — Record setup and turnaround time for a venue.

A booking holds its venue from ``start - setup`` to ``end + turnaround`` (AC3), and so
does the period a search asks about, so two events need setup + turnaround between
them. Blocked periods aren't padded. The worked examples come from the review of PR #10.
Runs against ``db_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from flask import Flask
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.permissions import Role
from app.modules.venue import services
from app.modules.venue.models import Booking, BookingStatus, Venue, VenueBlock
from app.modules.venue.schemas import VenueSchema

pytestmark = pytest.mark.scrum_67

MakeVenue = Callable[..., Venue]
MakeBooking = Callable[..., Booking]
MakeBlock = Callable[..., VenueBlock]
Save = Callable[..., None]
ReloadVenue = Callable[[int], Venue]

VALID_VENUE: dict[str, Any] = {"name": "Hall", "location": "A", "capacity": 10}


def _at(hour: int, minute: int = 0) -> datetime:
    """A moment on 1 October 2026, in UTC."""
    return datetime(2026, 10, 1, hour, minute, tzinfo=timezone.utc)


def _search(start: datetime, end: datetime) -> list[str]:
    """Names of the venues free for ``start``-``end``."""
    payload = {"start_time": start.isoformat(), "end_time": end.isoformat(), "min_capacity": 1}
    return [match.venue.name for match in services.search_venues(payload)]


@pytest.fixture()
def customers_example(make_venue: MakeVenue, make_booking: MakeBooking, save: Save) -> Venue:
    """The customer's example (Week 7 change #1): 30/45 and an event at 10:00-12:00."""
    venue = make_venue(setup_minutes=30, turnaround_minutes=45)
    save(venue)
    save(make_booking(venue, _at(10), _at(12)))
    return venue


# --------------------------------------------------------------------------
# AC1 — a venue records its setup and turnaround time
# --------------------------------------------------------------------------


def test_a_venue_records_its_setup_and_turnaround_time(
    db_session: Session, reload_venue: ReloadVenue
) -> None:
    payload = {**VALID_VENUE, "setup_minutes": 45, "turnaround_minutes": 20}

    created = services.create_venue(payload)

    shown = VenueSchema().dump(reload_venue(created.id))
    assert (shown["setup_minutes"], shown["turnaround_minutes"]) == (45, 20)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("setup_minutes", "Setup time cannot be negative."),
        ("turnaround_minutes", "Turnaround time cannot be negative."),
    ],
)
def test_buffer_minutes_cannot_be_negative(db_session: Session, field: str, message: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.create_venue({**VALID_VENUE, field: -1})

    assert exc_info.value.details == {field: [message]}


@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
def test_buffer_minutes_cannot_be_cleared(db_session: Session, venue: Venue, field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        services.update_venue(venue.id, {field: None})

    assert field in exc_info.value.details


# --------------------------------------------------------------------------
# AC2 — both default to the configured value when not set
# --------------------------------------------------------------------------


def test_a_new_venue_takes_the_configured_defaults(
    app: Flask, db_session: Session, reload_venue: ReloadVenue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "DEFAULT_VENUE_SETUP_MINUTES", 7)
    monkeypatch.setitem(app.config, "DEFAULT_VENUE_TURNAROUND_MINUTES", 11)

    created = services.create_venue(VALID_VENUE)

    stored = reload_venue(created.id)
    assert (stored.setup_minutes, stored.turnaround_minutes) == (7, 11)


def test_updating_other_fields_leaves_the_buffers_alone(
    db_session: Session, make_venue: MakeVenue, save: Save, reload_venue: ReloadVenue
) -> None:
    venue = make_venue(setup_minutes=45, turnaround_minutes=20)
    save(venue)

    services.update_venue(venue.id, {"capacity": 50})

    stored = reload_venue(venue.id)
    assert (stored.setup_minutes, stored.turnaround_minutes) == (45, 20)


# --------------------------------------------------------------------------
# AC3 — the calendar shows the padded period, and the event inside it
# --------------------------------------------------------------------------


def test_the_calendar_shows_a_booking_padded_by_setup_and_turnaround(
    db_session: Session, make_venue: MakeVenue, make_booking: MakeBooking, save: Save
) -> None:
    """A booking at 11:15-12:00 with 30/30 holds the venue 10:45-12:30.

    It overlaps a 10:00-11:00 range even though the event itself starts after it.
    """
    venue = make_venue(setup_minutes=30, turnaround_minutes=30)
    save(venue)
    save(make_booking(venue, _at(11, 15), _at(12)))

    [entry] = services.get_venue_calendar(venue.id, _at(10), _at(11), viewer_role=Role.VENUE_STAFF)

    assert (entry.start_time, entry.end_time) == (_at(10, 45), _at(12, 30))
    assert (entry.event_start, entry.event_end) == (_at(11, 15), _at(12))


def test_turnaround_after_an_earlier_event_reaches_into_the_range(
    db_session: Session, make_venue: MakeVenue, make_booking: MakeBooking, save: Save
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=30)
    save(venue)
    save(make_booking(venue, _at(8), _at(9, 45)))

    entries = services.get_venue_calendar(venue.id, _at(10), _at(11), viewer_role=Role.VENUE_STAFF)

    assert [(entry.start_time, entry.end_time) for entry in entries] == [(_at(8), _at(10, 15))]


@pytest.mark.parametrize("setup_minutes", [30, 60], ids=["clear-of-range", "touching-range"])
def test_a_padded_booking_that_stays_outside_the_range_is_left_out(
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    setup_minutes: int,
) -> None:
    venue = make_venue(setup_minutes=setup_minutes, turnaround_minutes=0)
    save(venue)
    save(make_booking(venue, _at(12), _at(13)))

    assert (
        services.get_venue_calendar(venue.id, _at(10), _at(11), viewer_role=Role.VENUE_STAFF) == []
    )


def test_the_calendar_does_not_pad_a_block(
    db_session: Session, make_venue: MakeVenue, make_block: MakeBlock, save: Save
) -> None:
    venue = make_venue(setup_minutes=30, turnaround_minutes=30)
    save(venue)
    save(make_block(venue, _at(9), _at(10)))

    [entry] = services.get_venue_calendar(venue.id, _at(8), _at(12), viewer_role=Role.VENUE_STAFF)

    assert (entry.start_time, entry.end_time) == (_at(9), _at(10))
    assert (entry.event_start, entry.event_end) == (None, None)


def test_a_block_just_before_the_range_is_not_pulled_in_by_padding(
    db_session: Session, make_venue: MakeVenue, make_block: MakeBlock, save: Save
) -> None:
    """Widening the range for bookings' padding must not catch unpadded blocks."""
    venue = make_venue(setup_minutes=30, turnaround_minutes=30)
    save(venue)
    save(make_block(venue, _at(10), _at(10, 45)))

    assert (
        services.get_venue_calendar(venue.id, _at(11), _at(12), viewer_role=Role.VENUE_STAFF) == []
    )


def test_the_calendar_route_shows_the_padded_period_and_the_event_in_business_time(
    app: Flask,
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    token_for: Callable[..., str],
) -> None:
    """01:00-02:00 UTC is 09:00-10:00 in Singapore; with 30/30 it holds 08:30-10:30."""
    venue = make_venue(setup_minutes=30, turnaround_minutes=30)
    save(venue)
    save(make_booking(venue, _at(1), _at(2), event_id=42))
    query = {"range_start": "2026-10-01T00:00:00Z", "range_end": "2026-10-02T00:00:00Z"}
    headers = {"Authorization": f"Bearer {token_for(role=Role.VENUE_STAFF)}"}

    with app.test_request_context(
        f"/api/venues/{venue.id}/calendar", query_string=query, headers=headers
    ):
        response, status = app.view_functions["venue.get_calendar"](venue_id=venue.id)

    assert status == 200
    assert response.get_json() == [
        {
            "start_time": "2026-10-01T08:30:00+08:00",
            "end_time": "2026-10-01T10:30:00+08:00",
            "event_start": "2026-10-01T09:00:00+08:00",
            "event_end": "2026-10-01T10:00:00+08:00",
            "kind": "confirmed_booking",
            "reason": "Event #42",
        }
    ]


# --------------------------------------------------------------------------
# AC3 — search pads both the existing booking and the period asked about
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("request_start", "found"),
    [(_at(10, 30), []), (_at(11), ["Main Hall"])],
    ids=["30-minutes-after", "60-minutes-after"],
)
def test_search_needs_setup_and_turnaround_after_an_earlier_event(
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    request_start: datetime,
    found: list[str],
) -> None:
    """08:00-10:00 with 30/30: the next event's setup can't start before 10:30."""
    venue = make_venue(setup_minutes=30, turnaround_minutes=30)
    save(venue)
    save(make_booking(venue, _at(8), _at(10)))

    assert _search(request_start, _at(12)) == found


@pytest.mark.parametrize(
    ("request_end", "found"),
    [(_at(13), ["Main Hall"]), (_at(13, 1), [])],
    ids=["60-minutes-before", "59-minutes-before"],
)
def test_search_needs_setup_and_turnaround_before_a_later_event(
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    request_end: datetime,
    found: list[str],
) -> None:
    venue = make_venue(setup_minutes=30, turnaround_minutes=30)
    save(venue)
    save(make_booking(venue, _at(14), _at(16)))

    assert _search(_at(12), request_end) == found


def test_each_venue_is_padded_by_its_own_buffers(
    db_session: Session, make_venue: MakeVenue, make_booking: MakeBooking, save: Save
) -> None:
    padded = make_venue(name="Padded", setup_minutes=30, turnaround_minutes=30)
    unpadded = make_venue(name="Unpadded", setup_minutes=0, turnaround_minutes=0)
    save(padded, unpadded)
    save(make_booking(padded, _at(8), _at(10)), make_booking(unpadded, _at(8), _at(10)))

    assert _search(_at(10, 30), _at(12)) == ["Unpadded"]


def test_search_does_not_pad_a_block(
    db_session: Session, make_venue: MakeVenue, make_block: MakeBlock, save: Save
) -> None:
    venue = make_venue(setup_minutes=30, turnaround_minutes=30)
    save(venue)
    save(make_block(venue, _at(8), _at(10)))

    assert _search(_at(10), _at(12)) == [venue.name]


# --------------------------------------------------------------------------
# AC3 — the customer's example: with 30 minutes' setup and 45 minutes' turnaround,
# an event at 10:00-12:00 holds the venue 09:30-12:45
# --------------------------------------------------------------------------


def test_the_calendar_shows_the_customers_example_as_09_30_to_12_45(
    customers_example: Venue,
) -> None:
    [entry] = services.get_venue_calendar(
        customers_example.id, _at(8), _at(16), viewer_role=Role.VENUE_STAFF
    )

    assert (entry.start_time, entry.end_time) == (_at(9, 30), _at(12, 45))


@pytest.mark.parametrize(
    ("request_start", "request_end", "found"),
    [(_at(12, 30), _at(14), []), (_at(14), _at(15), ["Main Hall"])],
    ids=["12:30-14:00", "14:00-15:00"],
)
def test_search_leaves_out_the_customers_example_until_its_turnaround_is_over(
    customers_example: Venue, request_start: datetime, request_end: datetime, found: list[str]
) -> None:
    assert _search(request_start, request_end) == found


# --------------------------------------------------------------------------
# AC4 — a buffer change reports confirmed bookings that now overlap
# --------------------------------------------------------------------------


def test_a_longer_turnaround_reports_confirmed_bookings_that_now_overlap(
    db_session: Session, make_venue: MakeVenue, make_booking: MakeBooking, save: Save
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=0)
    save(venue)
    first, second = make_booking(venue, _at(9), _at(10)), make_booking(venue, _at(10, 30), _at(11))
    save(first, second)

    _, warnings = services.update_venue(venue.id, {"turnaround_minutes": 45})

    assert warnings == [
        services.OverlapWarning(
            booking_ids=(first.id, second.id), overlap_start=_at(10, 30), overlap_end=_at(10, 45)
        )
    ]
    assert (first.status, second.status) == (BookingStatus.CONFIRMED, BookingStatus.CONFIRMED)


def test_bookings_still_far_enough_apart_after_a_change_are_not_reported(
    db_session: Session, make_venue: MakeVenue, make_booking: MakeBooking, save: Save
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=0)
    save(venue)
    save(make_booking(venue, _at(9), _at(10)), make_booking(venue, _at(12), _at(13)))

    _, warnings = services.update_venue(venue.id, {"turnaround_minutes": 45})

    assert warnings == []


@pytest.mark.parametrize("status", [BookingStatus.TENTATIVE, BookingStatus.CANCELLED])
def test_only_confirmed_bookings_are_checked_for_new_overlaps(
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    status: BookingStatus,
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=0)
    save(venue)
    save(
        make_booking(venue, _at(9), _at(10)),
        make_booking(venue, _at(10, 30), _at(11), status=status),
    )

    _, warnings = services.update_venue(venue.id, {"turnaround_minutes": 45})

    assert warnings == []


@pytest.mark.parametrize(
    "change", [{"capacity": 50}, {"turnaround_minutes": 45}], ids=["other-field", "same-value"]
)
def test_nothing_is_reported_unless_a_buffer_actually_changes(
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    change: dict[str, int],
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=45)
    save(venue)
    save(make_booking(venue, _at(9), _at(10)), make_booking(venue, _at(10, 30), _at(11)))

    _, warnings = services.update_venue(venue.id, change)

    assert warnings == []


def test_the_update_route_returns_the_venue_and_its_overlap_warnings(
    app: Flask,
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    token_for: Callable[..., str],
) -> None:
    venue = make_venue(setup_minutes=0, turnaround_minutes=0)
    save(venue)
    first, second = make_booking(venue, _at(9), _at(10)), make_booking(venue, _at(10, 30), _at(11))
    save(first, second)
    headers = {"Authorization": f"Bearer {token_for(role=Role.VENUE_STAFF)}"}

    with app.test_request_context(
        f"/api/venues/{venue.id}", method="PATCH", json={"turnaround_minutes": 45}, headers=headers
    ):
        response, status = app.view_functions["venue.update_venue"](venue_id=venue.id)

    body = response.get_json()
    assert status == 200
    assert body["turnaround_minutes"] == 45
    assert body["overlap_warnings"] == [
        {
            "booking_ids": [first.id, second.id],
            "overlap_start": "2026-10-01T18:30:00+08:00",
            "overlap_end": "2026-10-01T18:45:00+08:00",
        }
    ]
