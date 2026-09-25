"""Unit tests for SCRUM-34 — Block a venue for maintenance or internal use.

AC1: a block is saved with its reason and period, and the calendar shows it.
AC2: a block over a confirmed booking is still saved, and the response lists the
confirmed bookings it cuts into, padded by setup and turnaround (ADR-0016, ADR-0011).
AC3: search doesn't offer a blocked venue for the blocked period.

The services run against ``db_session`` with ``today`` pinned. Routes can't pin
``today``, so they're called through the registered view with the services mocked.
Times follow ADR-0009. The ``venue`` fixture has no opening periods, so every block
that is saved also shows that opening hours aren't checked (ADR-0016).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any, NamedTuple
from unittest.mock import MagicMock

import pytest
from flask import Flask, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from app.modules.auth.permissions import ALL_ROLES, Role
from app.modules.venue import services
from app.modules.venue.models import (
    Booking,
    BookingStatus,
    CalendarEntryKind,
    Venue,
    VenueBlock,
)

pytestmark = pytest.mark.scrum_34

MakeVenue = Callable[..., Venue]
MakeBooking = Callable[..., Booking]
MakeBlock = Callable[..., VenueBlock]
Save = Callable[..., None]
StoredBlock = tuple[int, datetime, datetime, str]

UTC = timezone.utc
TODAY = date(2026, 10, 1)
OTHER_ROLES = sorted(ALL_ROLES - {Role.VENUE_STAFF}, key=lambda role: role.value)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in October 2026, in UTC."""
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


#: The block most tests make: 3 October, 10:00-13:00 UTC (18:00-21:00 in Singapore).
BLOCK_START, BLOCK_END = _at(3, 10), _at(3, 13)
VALID_BLOCK = {
    "start_time": BLOCK_START.isoformat(),
    "end_time": BLOCK_END.isoformat(),
    "reason": "Repainting",
}
#: The day before TODAY, in UTC. 15:59 UTC is 23:59 that day in Singapore; 16:30 UTC is
#: already 00:30 on TODAY.
SEP_30_10AM = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
SEP_30_3_59PM = datetime(2026, 9, 30, 15, 59, tzinfo=UTC)
SEP_30_4_30PM = datetime(2026, 9, 30, 16, 30, tzinfo=UTC)


def _block(venue: Venue, **changes: str) -> tuple[VenueBlock, list[services.ConflictingBooking]]:
    """Block ``venue`` with :data:`VALID_BLOCK`, changed by ``changes``, as of TODAY."""
    return services.block_venue(venue.id, {**VALID_BLOCK, **changes}, today=TODAY)


def _stored_blocks(session: Session) -> list[StoredBlock]:
    """Every saved block as (venue id, start, end, reason), read back from the DB."""
    session.expire_all()
    blocks = session.scalars(select(VenueBlock).order_by(VenueBlock.id))
    return [(block.venue_id, block.start_time, block.end_time, block.reason) for block in blocks]


def _search(start: datetime, end: datetime) -> list[str]:
    """Names of the venues a coordinator's search finds free for ``start``-``end``."""
    payload = {"start_time": start.isoformat(), "end_time": end.isoformat(), "min_capacity": 1}
    return [match.venue.name for match in services.search_venues(payload)]


class BlockRoute(NamedTuple):
    """A block route, how to call its view, and the service it calls."""

    endpoint: str
    method: str
    path: str
    view_kwargs: dict[str, int]
    service: str


BLOCK_VENUE_ROUTE = BlockRoute(
    "venue.block_venue", "POST", "/api/venues/1/blocks", {"venue_id": 1}, "block_venue"
)
BLOCK_ROUTES = [BLOCK_VENUE_ROUTE]


def _call_route(app: Flask, route: BlockRoute, token: str | None) -> tuple[Response, int]:
    """Call the registered view the way a request would reach it, with VALID_BLOCK."""
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    with app.test_request_context(
        route.path, method=route.method, headers=headers, json=VALID_BLOCK
    ):
        return app.view_functions[route.endpoint](**route.view_kwargs)


@pytest.fixture()
def mock_block_services(
    monkeypatch: pytest.MonkeyPatch, make_venue: MakeVenue, make_block: MakeBlock
) -> dict[str, MagicMock]:
    """Replace the services the block routes call with mocks of the right shape."""
    block = make_block(make_venue(venue_id=1), BLOCK_START, BLOCK_END, reason="Repainting")
    block.id = 7
    conflict = services.ConflictingBooking(
        booking_id=12, event_id=42, start_time=_at(3, 10, 30), end_time=_at(3, 12, 30)
    )
    returns: dict[str, Any] = {"block_venue": (block, [conflict])}
    mocks = {}
    for name, value in returns.items():
        mock = MagicMock(return_value=value)
        monkeypatch.setattr(services, name, mock)
        mocks[name] = mock
    return mocks


# --------------------------------------------------------------------------
# AC1 — a block with a reason and a period makes the venue unavailable
# --------------------------------------------------------------------------


def test_venue_staff_can_block_a_venue_with_a_reason_and_a_period(
    db_session: Session, venue: Venue
) -> None:
    _, conflicts = _block(venue)

    assert _stored_blocks(db_session) == [(venue.id, BLOCK_START, BLOCK_END, "Repainting")]
    assert conflicts == []


def test_a_new_block_shows_as_unavailable_on_the_calendar(
    db_session: Session, venue: Venue
) -> None:
    _block(venue)

    entries = services.get_venue_calendar(
        venue.id, _at(3, 0), _at(4, 0), viewer_role=Role.VENUE_STAFF
    )

    assert [(entry.kind, entry.start_time, entry.end_time, entry.reason) for entry in entries] == [
        (CalendarEntryKind.BLOCK, BLOCK_START, BLOCK_END, "Repainting")
    ]


def test_a_time_without_an_offset_is_read_as_business_time(
    db_session: Session, venue: Venue
) -> None:
    _block(venue, start_time="2026-10-03T18:00:00", end_time="2026-10-03T21:00:00")

    assert _stored_blocks(db_session) == [(venue.id, BLOCK_START, BLOCK_END, "Repainting")]


def test_the_block_route_returns_the_block_and_what_it_cuts_into_in_business_time(
    app: Flask, token_for: Callable[..., str], mock_block_services: dict[str, MagicMock]
) -> None:
    response, status = _call_route(app, BLOCK_VENUE_ROUTE, token_for(role=Role.VENUE_STAFF))

    assert status == 201
    mock_block_services["block_venue"].assert_called_once_with(1, VALID_BLOCK)
    assert response.get_json() == {
        "id": 7,
        "venue_id": 1,
        "start_time": "2026-10-03T18:00:00+08:00",
        "end_time": "2026-10-03T21:00:00+08:00",
        "reason": "Repainting",
        "conflicting_bookings": [
            {
                "booking_id": 12,
                "event_id": 42,
                "start_time": "2026-10-03T18:30:00+08:00",
                "end_time": "2026-10-03T20:30:00+08:00",
            }
        ],
    }


# --------------------------------------------------------------------------
# What a block must carry (ADR-0016) — a rejected block is never saved
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["start_time", "end_time", "reason"])
def test_reason_start_and_end_are_required(db_session: Session, venue: Venue, missing: str) -> None:
    payload = dict(VALID_BLOCK)
    del payload[missing]

    with pytest.raises(ValidationError) as exc_info:
        services.block_venue(venue.id, payload, today=TODAY)

    assert exc_info.value.details == {missing: ["Missing data for required field."]}
    assert _stored_blocks(db_session) == []


@pytest.mark.parametrize(
    ("changes", "details"),
    [
        ({"reason": ""}, {"reason": ["Must not be blank."]}),
        ({"reason": "   "}, {"reason": ["Must not be blank."]}),
        ({"reason": "x" * 501}, {"reason": ["Reason must be at most 500 characters."]}),
        (
            {"end_time": BLOCK_START.isoformat()},
            {"end_time": ["end_time must be after start_time."]},
        ),
        (
            {"end_time": _at(3, 9).isoformat()},
            {"end_time": ["end_time must be after start_time."]},
        ),
        (
            {"start_time": SEP_30_10AM.isoformat(), "end_time": SEP_30_3_59PM.isoformat()},
            {"end_time": ["Block cannot end before today."]},
        ),
    ],
    ids=[
        "empty-reason",
        "blank-reason",
        "reason-too-long",
        "ends-as-it-starts",
        "ends-before-it-starts",
        "ended-before-today",
    ],
)
def test_an_invalid_block_is_rejected(
    db_session: Session, venue: Venue, changes: dict[str, str], details: dict[str, list[str]]
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _block(venue, **changes)

    assert exc_info.value.details == details
    assert _stored_blocks(db_session) == []


@pytest.mark.parametrize(
    ("reason", "stored"),
    [("  Repainting  ", "Repainting"), ("  " + "x" * 500 + "  ", "x" * 500)],
    ids=["trimmed", "at-the-length-limit-once-trimmed"],
)
def test_the_reason_is_stored_trimmed(
    db_session: Session, venue: Venue, reason: str, stored: str
) -> None:
    _block(venue, reason=reason)

    assert _stored_blocks(db_session) == [(venue.id, BLOCK_START, BLOCK_END, stored)]


@pytest.mark.parametrize(
    ("start", "end"),
    [(SEP_30_10AM, SEP_30_4_30PM), (SEP_30_10AM, _at(2, 10))],
    ids=["ends-today", "started-before-today"],
)
def test_a_block_may_end_today_or_have_started_before_today(
    db_session: Session, venue: Venue, start: datetime, end: datetime
) -> None:
    _block(venue, start_time=start.isoformat(), end_time=end.isoformat())

    assert _stored_blocks(db_session) == [(venue.id, start, end, "Repainting")]


def test_blocking_an_unknown_venue_is_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        services.block_venue(999, VALID_BLOCK, today=TODAY)

    assert _stored_blocks(db_session) == []


# --------------------------------------------------------------------------
# AC2 — blocking over a confirmed booking is saved, and reports the booking
# --------------------------------------------------------------------------


def test_blocking_over_a_confirmed_booking_saves_the_block_and_reports_it(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save
) -> None:
    booking = make_booking(venue, _at(3, 11), _at(3, 12), event_id=42)
    save(booking)

    _, conflicts = _block(venue)

    assert conflicts == [
        services.ConflictingBooking(
            booking_id=booking.id, event_id=42, start_time=_at(3, 11), end_time=_at(3, 12)
        )
    ]
    assert _stored_blocks(db_session) == [(venue.id, BLOCK_START, BLOCK_END, "Repainting")]
    assert booking.status is BookingStatus.CONFIRMED


@pytest.mark.parametrize(
    ("booking_start", "booking_end", "held"),
    [
        (_at(3, 13, 20), _at(3, 14), [(_at(3, 12, 50), _at(3, 14, 15))]),
        (_at(3, 9), _at(3, 9, 50), [(_at(3, 8, 30), _at(3, 10, 5))]),
        (_at(3, 13, 30), _at(3, 14), []),
        (_at(3, 9), _at(3, 9, 45), []),
    ],
    ids=[
        "setup-reaches-in",
        "turnaround-reaches-in",
        "setup-only-touches",
        "turnaround-only-touches",
    ],
)
def test_a_booking_is_reported_when_its_setup_or_turnaround_reaches_into_the_block(
    db_session: Session,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
    booking_start: datetime,
    booking_end: datetime,
    held: list[tuple[datetime, datetime]],
) -> None:
    """With 30 minutes' setup and 15 minutes' turnaround, around a 10:00-13:00 block."""
    venue = make_venue(setup_minutes=30, turnaround_minutes=15)
    save(venue)
    save(make_booking(venue, booking_start, booking_end))

    _, conflicts = _block(venue)

    assert [(conflict.start_time, conflict.end_time) for conflict in conflicts] == held


@pytest.mark.parametrize("status", [BookingStatus.TENTATIVE, BookingStatus.CANCELLED])
def test_tentative_holds_and_cancelled_bookings_are_not_reported(
    db_session: Session,
    venue: Venue,
    make_booking: MakeBooking,
    save: Save,
    status: BookingStatus,
) -> None:
    save(make_booking(venue, _at(3, 11), _at(3, 12), status=status))

    _, conflicts = _block(venue)

    assert conflicts == []


def test_bookings_outside_the_period_or_on_another_venue_are_not_reported(
    db_session: Session,
    venue: Venue,
    make_venue: MakeVenue,
    make_booking: MakeBooking,
    save: Save,
) -> None:
    other = make_venue(name="Other Hall")
    save(other)
    save(
        make_booking(venue, _at(4, 11), _at(4, 12)),
        make_booking(other, _at(3, 11), _at(3, 12)),
    )

    _, conflicts = _block(venue)

    assert conflicts == []


def test_conflicts_are_listed_in_start_order(
    db_session: Session, venue: Venue, make_booking: MakeBooking, save: Save
) -> None:
    later = make_booking(venue, _at(3, 12), _at(3, 12, 30))
    earlier = make_booking(venue, _at(3, 10, 30), _at(3, 11))
    save(later, earlier)

    _, conflicts = _block(venue)

    assert [conflict.booking_id for conflict in conflicts] == [earlier.id, later.id]


# --------------------------------------------------------------------------
# AC3 — a coordinator's search doesn't offer a blocked venue for that period
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "found"),
    [(_at(3, 11), _at(3, 12), []), (_at(3, 13), _at(3, 14), ["Main Hall"])],
    ids=["inside-the-block", "after-the-block"],
)
def test_a_blocked_venue_cannot_be_found_for_that_period(
    db_session: Session, venue: Venue, start: datetime, end: datetime, found: list[str]
) -> None:
    _block(venue)

    assert _search(start, end) == found


# --------------------------------------------------------------------------
# Only Venue Staff manage blocks (through the registered routes)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", OTHER_ROLES, ids=lambda role: role.value)
@pytest.mark.parametrize("route", BLOCK_ROUTES, ids=lambda route: route.endpoint)
def test_managing_blocks_by_non_venue_staff_is_403(
    app: Flask,
    token_for: Callable[..., str],
    mock_block_services: dict[str, MagicMock],
    role: Role,
    route: BlockRoute,
) -> None:
    with pytest.raises(AuthorizationError) as exc_info:
        _call_route(app, route, token_for(role=role))

    assert exc_info.value.status_code == 403
    mock_block_services[route.service].assert_not_called()


@pytest.mark.parametrize("route", BLOCK_ROUTES, ids=lambda route: route.endpoint)
def test_managing_blocks_without_a_token_is_401(
    app: Flask, mock_block_services: dict[str, MagicMock], route: BlockRoute
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        _call_route(app, route, token=None)

    assert exc_info.value.status_code == 401
    mock_block_services[route.service].assert_not_called()


@pytest.mark.parametrize("route", BLOCK_ROUTES, ids=lambda route: route.endpoint)
def test_block_routes_allow_only_venue_staff(app: Flask, route: BlockRoute) -> None:
    """Guards against a future edit widening the allow-list by accident."""
    assert app.view_functions[route.endpoint].allowed_roles == frozenset({Role.VENUE_STAFF.value})
