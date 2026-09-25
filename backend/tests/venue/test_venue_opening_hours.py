"""Unit tests for venue opening hours (SCRUM-25 AC1, ADR-0008).

Covers the weekly-timeline arithmetic in ``opening_hours.py`` directly, then
the same rules end to end through ``create_venue`` / ``update_venue`` against
the in-memory database (``db_session``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import time
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.venue import services
from app.modules.venue.models import Venue, VenueOpeningPeriod, Weekday
from app.modules.venue.opening_hours import Period, find_overlap, period_error
from app.modules.venue.schemas import VenueSchema

pytestmark = pytest.mark.scrum_25

MON, TUE, WED, FRI, SAT, SUN = (
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.WEDNESDAY,
    Weekday.FRIDAY,
    Weekday.SATURDAY,
    Weekday.SUNDAY,
)


def _t(hhmm: str) -> time:
    hours, minutes = hhmm.split(":")
    return time(int(hours), int(minutes))


def _period(open_day: Weekday, opens: str, close_day: Weekday, closes: str) -> Period:
    return Period(open_day, _t(opens), close_day, _t(closes))


def _json(open_day: str, opens: str, close_day: str, closes: str) -> dict[str, Any]:
    return {"open": {"day": open_day, "time": opens}, "close": {"day": close_day, "time": closes}}


def _payload(opening_hours: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": "Hall", "location": "A", "capacity": 10, "opening_hours": opening_hours}


def _hours_shown(venue: Venue) -> list[dict[str, Any]]:
    return VenueSchema().dump(venue)["opening_hours"]


# --------------------------------------------------------------------------
# period_error — the rule that replaces "end must be after start"
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period",
    [
        _period(MON, "09:00", MON, "18:00"),  # ordinary day
        _period(FRI, "18:00", SAT, "02:00"),  # past midnight
        _period(SUN, "22:00", MON, "03:00"),  # past midnight, across the week boundary
        _period(MON, "00:00", TUE, "00:00"),  # open all day, exactly 24 hours
        _period(MON, "00:00", MON, "23:59"),
    ],
    ids=["same-day", "overnight", "sunday-into-monday", "24-hours", "almost-24-hours"],
)
def test_valid_periods(period: Period) -> None:
    assert period_error(period) is None


@pytest.mark.parametrize(
    ("period", "message_fragment"),
    [
        (_period(MON, "18:00", MON, "09:00"), "set the close day to the next day"),
        (_period(MON, "09:00", MON, "09:00"), "Close time must be after open time"),
        (_period(MON, "09:00", TUE, "09:01"), "longer than 24 hours"),
        (_period(MON, "09:00", WED, "01:00"), "same day as the open day or the day after"),
        (_period(TUE, "09:00", MON, "10:00"), "same day as the open day or the day after"),
    ],
    ids=["close-before-open", "zero-length", "over-24-hours", "two-days-later", "day-before"],
)
def test_invalid_periods(period: Period, message_fragment: str) -> None:
    error = period_error(period)

    assert error is not None
    assert message_fragment in error


# --------------------------------------------------------------------------
# find_overlap — on a weekly timeline that wraps Sunday → Monday
# --------------------------------------------------------------------------


def test_split_hours_on_one_day_do_not_overlap() -> None:
    periods = [_period(MON, "09:00", MON, "12:00"), _period(MON, "13:00", MON, "18:00")]

    assert find_overlap(periods) is None


def test_touching_periods_do_not_overlap() -> None:
    """24/7 written as back-to-back full days is valid."""
    periods = [_period(day, "00:00", Weekday((day + 1) % 7), "00:00") for day in Weekday]

    assert find_overlap(periods) is None


def test_overnight_period_overlapping_next_morning_is_found() -> None:
    periods = [_period(FRI, "18:00", SAT, "02:00"), _period(SAT, "01:00", SAT, "05:00")]

    assert find_overlap(periods) == (0, 1)


def test_sunday_overnight_overlapping_monday_morning_is_found() -> None:
    periods = [_period(MON, "02:00", MON, "09:00"), _period(SUN, "22:00", MON, "03:00")]

    assert find_overlap(periods) == (0, 1)


def test_overlap_reports_the_right_pair_among_many() -> None:
    periods = [
        _period(MON, "09:00", MON, "12:00"),
        _period(TUE, "09:00", TUE, "12:00"),
        _period(WED, "09:00", WED, "12:00"),
        _period(TUE, "11:00", TUE, "14:00"),
    ]

    assert find_overlap(periods) == (1, 3)


# --------------------------------------------------------------------------
# Through the service layer
# --------------------------------------------------------------------------


def test_create_venue_saves_overnight_hours(
    db_session: Session, reload_venue: Callable[[int], Venue]
) -> None:
    hours = [
        _json("friday", "18:00", "saturday", "02:00"),
        _json("sunday", "22:00", "monday", "03:00"),
    ]

    created = services.create_venue(_payload(hours), session=db_session)

    assert _hours_shown(reload_venue(created.id)) == hours


def test_create_venue_without_hours_defaults_to_daily_nine_to_six(
    db_session: Session, reload_venue: Callable[[int], Venue]
) -> None:
    created = services.create_venue(
        {"name": "Hall", "location": "A", "capacity": 10}, session=db_session
    )

    assert _hours_shown(reload_venue(created.id)) == [
        _json(day, "09:00", day, "18:00") for day in Weekday.labels()
    ]


def test_create_venue_with_empty_hours_is_closed_every_day(
    db_session: Session, reload_venue: Callable[[int], Venue]
) -> None:
    created = services.create_venue(_payload([]), session=db_session)

    assert _hours_shown(reload_venue(created.id)) == []


def test_invalid_period_error_points_at_its_close_field(db_session: Session) -> None:
    hours = [
        _json("monday", "09:00", "monday", "18:00"),
        _json("monday", "22:00", "monday", "02:00"),
    ]

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(_payload(hours), session=db_session)

    assert "close" in exc_info.value.details["opening_hours"][1]
    assert db_session.scalars(select(Venue)).all() == []


def test_overlap_error_is_keyed_by_the_later_period(db_session: Session) -> None:
    hours = [
        _json("friday", "18:00", "saturday", "02:00"),
        _json("saturday", "01:00", "saturday", "05:00"),
    ]

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(_payload(hours), session=db_session)

    assert exc_info.value.details["opening_hours"] == {1: ["Overlaps opening period 0."]}


@pytest.mark.parametrize(
    "bad_point",
    [
        {"day": "funday", "time": "09:00"},
        {"day": "Monday", "time": "09:00"},
        {"day": "monday", "time": "9am"},
        {"day": "monday", "time": "24:00"},
        {"day": "monday", "time": "09:00:00"},
        {"day": "monday"},
    ],
    ids=["unknown-day", "capitalised-day", "not-hhmm", "24-00", "with-seconds", "missing-time"],
)
def test_malformed_open_point_is_rejected(db_session: Session, bad_point: dict[str, Any]) -> None:
    hours = [{"open": bad_point, "close": {"day": "monday", "time": "18:00"}}]

    with pytest.raises(ValidationError) as exc_info:
        services.create_venue(_payload(hours), session=db_session)

    assert "open" in exc_info.value.details["opening_hours"][0]


def test_update_rejects_an_incomplete_period(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    """Partial updates must not relax required fields inside a period."""
    venue = make_venue()
    save(venue)

    with pytest.raises(ValidationError) as exc_info:
        services.update_venue(
            venue.id,
            {"opening_hours": [{"open": {"day": "monday", "time": "09:00"}}]},
            session=db_session,
        )

    assert "close" in exc_info.value.details["opening_hours"][0]
    assert _hours_shown(reload_venue(venue.id)) == []


def test_update_replaces_the_whole_schedule(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    old = VenueOpeningPeriod(open_day=MON, open_time=time(9), close_day=MON, close_time=time(18))
    venue = make_venue(opening_periods=[old])
    save(venue)

    services.update_venue(
        venue.id,
        {"opening_hours": [_json("friday", "20:00", "saturday", "04:00")]},
        session=db_session,
    )

    assert _hours_shown(reload_venue(venue.id)) == [_json("friday", "20:00", "saturday", "04:00")]
    # The old period's row is deleted, not left behind without a venue.
    assert len(db_session.scalars(select(VenueOpeningPeriod)).all()) == 1


def test_update_without_hours_leaves_schedule_alone(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    reload_venue: Callable[[int], Venue],
) -> None:
    period = VenueOpeningPeriod(open_day=MON, open_time=time(9), close_day=MON, close_time=time(18))
    venue = make_venue(opening_periods=[period])
    save(venue)

    services.update_venue(venue.id, {"capacity": 50}, session=db_session)

    assert _hours_shown(reload_venue(venue.id)) == [_json("monday", "09:00", "monday", "18:00")]


def test_opening_hours_are_shown_in_week_order(make_venue: Callable[..., Venue]) -> None:
    venue = make_venue(
        opening_periods=[
            VenueOpeningPeriod(
                open_day=SUN, open_time=time(10), close_day=SUN, close_time=time(16)
            ),
            VenueOpeningPeriod(
                open_day=MON, open_time=time(13), close_day=MON, close_time=time(18)
            ),
            VenueOpeningPeriod(open_day=MON, open_time=time(9), close_day=MON, close_time=time(12)),
        ]
    )

    assert _hours_shown(venue) == [
        _json("monday", "09:00", "monday", "12:00"),
        _json("monday", "13:00", "monday", "18:00"),
        _json("sunday", "10:00", "sunday", "16:00"),
    ]
