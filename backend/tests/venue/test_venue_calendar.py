"""Unit tests for SCRUM-26 — View a venue's availability calendar.

The service runs against ``db_session``, so its range, venue and status filters are
real SQL. AC4 is tested by opening the registered route with each role's token. The
query rules, including how a time without an offset is read (ADR-0009), are tested on
``CalendarQuerySchema``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from flask import Flask, Response
from sqlalchemy.orm import Session

from app.common.errors import AuthorizationError, NotFoundError, ValidationError
from app.common.validation import load_or_raise
from app.modules.auth.permissions import EXTERNAL_ROLES, INTERNAL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import Booking, BookingStatus, Venue, VenueBlock
from app.modules.venue.schemas import CalendarQuerySchema

pytestmark = pytest.mark.scrum_26

MakeVenue = Callable[..., Venue]
MakeBooking = Callable[..., Booking]
MakeBlock = Callable[..., VenueBlock]
Save = Callable[..., None]

UTC = timezone.utc
ROLES_WITHOUT_ACCESS = sorted(EXTERNAL_ROLES, key=lambda role: role.value)
ROLES_WITH_ACCESS = sorted(INTERNAL_ROLES, key=lambda role: role.value)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in October 2026, in UTC."""
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


#: The calendar range most tests ask for: all of 1 October, UTC.
RANGE_START, RANGE_END = _at(1, 0), _at(2, 0)
#: 30 September, before the range starts.
SEP_30_8PM = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
SEP_30_10PM = datetime(2026, 9, 30, 22, 0, tzinfo=UTC)


def _calendar(venue: Venue, role: Role = Role.VENUE_STAFF) -> list[services.CalendarEntry]:
    return services.get_venue_calendar(venue.id, RANGE_START, RANGE_END, viewer_role=role)


def _summary(entries: list[services.CalendarEntry]) -> list[tuple[str, datetime, datetime]]:
    return [(entry.kind.value, entry.start_time, entry.end_time) for entry in entries]


def _open_calendar(
    app: Flask, token: str, venue_id: int, query: dict[str, str]
) -> tuple[Response, int]:
    """Call the registered calendar view the way a request would reach it."""
    with app.test_request_context(
        f"/api/venues/{venue_id}/calendar",
        query_string=query,
        headers={"Authorization": f"Bearer {token}"},
    ):
        return app.view_functions["venue.get_calendar"](venue_id=venue_id)


FULL_DAY_QUERY = {"range_start": "2026-10-01T00:00:00Z", "range_end": "2026-10-02T00:00:00Z"}


# --------------------------------------------------------------------------
# AC1 / AC2 — bookings and blocked periods in the range, in time order
# --------------------------------------------------------------------------


def test_bookings_and_blocks_in_range_are_listed_in_start_order(
    db_session: Session,
    venue: Venue,
    make_booking: MakeBooking,
    make_block: MakeBlock,
    save: Save,
) -> None:
    save(
        make_booking(venue, _at(1, 14), _at(1, 15)),
        make_block(venue, _at(1, 9), _at(1, 10)),
    )

    assert _summary(_calendar(venue)) == [
        ("block", _at(1, 9), _at(1, 10)),
        ("confirmed_booking", _at(1, 14), _at(1, 15)),
    ]


def test_a_tentative_hold_is_shown_and_marked_as_tentative(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save
) -> None:
    save(make_booking(venue, _at(1, 9), _at(1, 11), status=BookingStatus.TENTATIVE))

    assert _summary(_calendar(venue)) == [("tentative_hold", _at(1, 9), _at(1, 11))]


def test_a_cancelled_booking_is_not_shown(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save
) -> None:
    save(make_booking(venue, _at(1, 9), _at(1, 11), status=BookingStatus.CANCELLED))

    assert _calendar(venue) == []


def test_entries_crossing_either_edge_of_the_range_are_shown(
    db_session: Session,
    venue: Venue,
    make_booking: MakeBooking,
    make_block: MakeBlock,
    save: Save,
) -> None:
    save(
        make_booking(venue, SEP_30_10PM, _at(1, 2)),
        make_block(venue, _at(1, 23), _at(2, 3)),
    )

    assert _summary(_calendar(venue)) == [
        ("confirmed_booking", SEP_30_10PM, _at(1, 2)),
        ("block", _at(1, 23), _at(2, 3)),
    ]


def test_entries_outside_the_range_or_only_touching_it_are_left_out(
    db_session: Session,
    venue: Venue,
    make_booking: MakeBooking,
    make_block: MakeBlock,
    save: Save,
) -> None:
    save(
        make_booking(venue, SEP_30_8PM, RANGE_START),
        make_block(venue, RANGE_END, _at(2, 2)),
        make_booking(venue, _at(3, 9), _at(3, 10)),
        make_block(venue, _at(3, 9), _at(3, 10)),
    )

    assert _calendar(venue) == []


def test_another_venues_entries_are_left_out(
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    make_block: MakeBlock,
    save: Save,
) -> None:
    venue, other = make_venue(), make_venue(name="Other Hall")
    save(venue, other)
    save(make_booking(other, _at(1, 9), _at(1, 10)), make_block(other, _at(1, 11), _at(1, 12)))

    assert _calendar(venue) == []


def test_times_are_returned_in_utc_whatever_offset_they_were_saved_with(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save
) -> None:
    singapore = ZoneInfo("Asia/Singapore")
    save(
        make_booking(
            venue,
            datetime(2026, 10, 1, 9, 0, tzinfo=singapore),
            datetime(2026, 10, 1, 11, 0, tzinfo=singapore),
        )
    )
    db_session.expire_all()

    [entry] = _calendar(venue)

    assert (entry.start_time, entry.end_time) == (_at(1, 1), _at(1, 3))
    assert entry.start_time.tzinfo is UTC


def test_calendar_of_an_unknown_venue_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        services.get_venue_calendar(999, RANGE_START, RANGE_END, viewer_role=Role.VENUE_STAFF)


# --------------------------------------------------------------------------
# AC3 — how much of the reason a viewer sees depends on their role
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("saved_reason", "shown_reason"),
    [("Fire alarm inspection", "Fire alarm inspection"), ("", "Maintenance")],
    ids=["given", "left-blank"],
)
def test_venue_staff_see_why_a_venue_is_blocked(
    db_session: Session,
    venue: Venue,
    make_block: MakeBlock,
    save: Save,
    saved_reason: str,
    shown_reason: str,
) -> None:
    save(make_block(venue, _at(1, 9), _at(1, 10), reason=saved_reason))

    assert [entry.reason for entry in _calendar(venue)] == [shown_reason]


@pytest.mark.parametrize("role", [Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF])
def test_other_internal_roles_see_only_that_a_block_is_maintenance(
    db_session: Session, venue: Venue, make_block: MakeBlock, save: Save, role: Role
) -> None:
    save(make_block(venue, _at(1, 9), _at(1, 10), reason="Fire alarm inspection"))

    assert [entry.reason for entry in _calendar(venue, role)] == ["maintenance"]


@pytest.mark.parametrize(
    ("event_id", "reason"), [(42, "Event #42"), (None, "Booking (no linked event)")]
)
def test_venue_staff_see_which_event_a_booking_is_for(
    db_session: Session,
    venue: Venue,
    make_booking: MakeBooking,
    save: Save,
    event_id: int | None,
    reason: str,
) -> None:
    save(make_booking(venue, _at(1, 9), _at(1, 10), event_id=event_id))

    assert [entry.reason for entry in _calendar(venue)] == [reason]


@pytest.mark.parametrize("role", [Role.EVENT_COORDINATOR, Role.TECHNICAL_SUPPORT_STAFF])
def test_other_internal_roles_see_only_that_a_period_is_booked(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save, role: Role
) -> None:
    save(make_booking(venue, _at(1, 9), _at(1, 10), event_id=42))

    assert [entry.reason for entry in _calendar(venue, role)] == ["booking"]


# --------------------------------------------------------------------------
# AC4 — only internal roles can open the calendar (through the real route)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES_WITHOUT_ACCESS)
def test_organisers_and_attendees_cannot_open_the_calendar(
    app: Flask,
    db_session: Session,
    venue: Venue,
    token_for: Callable[..., str],
    role: Role,
) -> None:
    with pytest.raises(AuthorizationError):
        _open_calendar(app, token_for(role=role), venue.id, FULL_DAY_QUERY)


@pytest.mark.parametrize("role", ROLES_WITH_ACCESS)
def test_internal_roles_can_open_the_calendar(
    app: Flask,
    db_session: Session,
    venue: Venue,
    make_block: MakeBlock,
    save: Save,
    token_for: Callable[..., str],
    role: Role,
) -> None:
    save(make_block(venue, _at(1, 9), _at(1, 10), reason="Fire alarm inspection"))

    response, status = _open_calendar(app, token_for(role=role), venue.id, FULL_DAY_QUERY)

    expected_reason = "Fire alarm inspection" if role is Role.VENUE_STAFF else "maintenance"
    assert status == 200
    assert response.get_json() == [
        {
            "start_time": "2026-10-01T17:00:00+08:00",
            "end_time": "2026-10-01T18:00:00+08:00",
            "kind": "block",
            "reason": expected_reason,
        }
    ]


# --------------------------------------------------------------------------
# The range asked for (ADR-0009)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "range_end", ["2026-10-01T09:00:00Z", "2026-10-01T08:00:00Z"], ids=["equal", "before"]
)
def test_a_range_that_does_not_end_after_it_starts_is_rejected(range_end: str) -> None:
    query = {"range_start": "2026-10-01T09:00:00Z", "range_end": range_end}

    with pytest.raises(ValidationError) as exc_info:
        load_or_raise(CalendarQuerySchema(), query)

    assert exc_info.value.details == {"range_end": ["range_end must be after range_start."]}


@pytest.mark.parametrize("missing", ["range_start", "range_end"])
def test_both_ends_of_the_range_are_required(missing: str) -> None:
    query = dict(FULL_DAY_QUERY)
    del query[missing]

    with pytest.raises(ValidationError) as exc_info:
        load_or_raise(CalendarQuerySchema(), query)

    assert missing in exc_info.value.details


def test_a_time_without_an_offset_is_read_as_business_time() -> None:
    """Mixing an offset-less time with an offset one is fine: both become UTC first."""
    query = {"range_start": "2026-10-01T08:00:00", "range_end": "2026-10-01T02:00:00Z"}

    loaded = load_or_raise(CalendarQuerySchema(), query)

    assert loaded == {"range_start": _at(1, 0), "range_end": _at(1, 2)}
