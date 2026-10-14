"""Unit tests for SCRUM-42 AC2 — a request must fall inside the venue's operating hours.

Covers the weekly-coverage arithmetic in ``opening_hours.py`` directly, then the refusal
it drives when a coordinator raises a booking request. Hours are agreed outside the
system, so a refused request has no in-system remedy and the message names the hours.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.venue.models import Venue, VenueOpeningPeriod, Weekday
from app.modules.venue.opening_hours import Period, covers_period
from tests.venue.conftest import SavedEvent, raise_booking, saved_requests

pytestmark = pytest.mark.scrum_42

MON, TUE, FRI, SAT, SUN = (
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.FRIDAY,
    Weekday.SATURDAY,
    Weekday.SUNDAY,
)

#: The week the arithmetic tests place their periods in, starting on a Monday.
WEEK_START = date(2026, 10, 26)

#: ``saved_event`` runs its event on Sunday 2026-11-01, which the default payload books.
SUNDAY = "2026-11-01"

OUTSIDE_HOURS = "The request falls outside the venue's operating hours."


def _t(hhmm: str) -> time:
    hours, minutes = hhmm.split(":")
    return time(int(hours), int(minutes))


def _period(open_day: Weekday, opens: str, close_day: Weekday, closes: str) -> Period:
    return Period(open_day, _t(opens), close_day, _t(closes))


def _row(open_day: Weekday, opens: str, close_day: Weekday, closes: str) -> VenueOpeningPeriod:
    """One of a venue's stored opening periods."""
    return VenueOpeningPeriod(
        open_day=open_day, open_time=_t(opens), close_day=close_day, close_time=_t(closes)
    )


def _at(day: Weekday, hhmm: str) -> datetime:
    """A business-time instant on ``day`` of the week beginning Monday 2026-10-26."""
    return datetime.combine(WEEK_START + timedelta(days=int(day)), _t(hhmm))


def _next_week_at(day: Weekday, hhmm: str) -> datetime:
    """A week later, for a request that runs on past Sunday midnight."""
    return _at(day, hhmm) + timedelta(days=7)


def _booked(sunday_from: str, sunday_to: str) -> dict[str, str]:
    """Payload overrides booking the event's own Sunday between two business times."""
    return {
        "starts_at": f"{SUNDAY}T{sunday_from}:00+08:00",
        "ends_at": f"{SUNDAY}T{sunday_to}:00+08:00",
    }


# --------------------------------------------------------------------------
# covers_period — placing a request on the weekly timeline
# --------------------------------------------------------------------------


def test_a_request_inside_one_days_hours_is_covered() -> None:
    assert covers_period(
        [_period(MON, "09:00", MON, "18:00")], _at(MON, "10:00"), _at(MON, "12:00")
    )


def test_a_request_filling_the_whole_opening_period_is_covered() -> None:
    """The ends touch the hours exactly, which is still inside them."""
    assert covers_period(
        [_period(MON, "09:00", MON, "18:00")], _at(MON, "09:00"), _at(MON, "18:00")
    )


def test_a_request_starting_before_the_venue_opens_is_not_covered() -> None:
    assert not covers_period(
        [_period(MON, "09:00", MON, "18:00")], _at(MON, "08:00"), _at(MON, "10:00")
    )


def test_a_request_ending_after_the_venue_closes_is_not_covered() -> None:
    assert not covers_period(
        [_period(MON, "09:00", MON, "18:00")], _at(MON, "17:00"), _at(MON, "20:00")
    )


def test_a_venue_with_no_opening_periods_covers_nothing() -> None:
    """A day with no period is a closed day, so a venue with none is closed all week."""
    assert not covers_period([], _at(MON, "10:00"), _at(MON, "12:00"))


def test_hours_on_another_day_do_not_cover_the_request() -> None:
    assert not covers_period(
        [_period(MON, "09:00", MON, "18:00")], _at(TUE, "10:00"), _at(TUE, "12:00")
    )


def test_two_periods_that_meet_are_one_continuous_opening() -> None:
    """Morning and afternoon periods that touch at 12:00 cover a request across both."""
    hours = [_period(MON, "09:00", MON, "12:00"), _period(MON, "12:00", MON, "18:00")]

    assert covers_period(hours, _at(MON, "11:00"), _at(MON, "13:00"))


def test_a_gap_between_two_periods_is_not_covered() -> None:
    hours = [_period(MON, "09:00", MON, "12:00"), _period(MON, "13:00", MON, "18:00")]

    assert not covers_period(hours, _at(MON, "11:00"), _at(MON, "14:00"))


def test_a_period_past_midnight_covers_a_request_across_midnight() -> None:
    hours = [_period(FRI, "20:00", SAT, "04:00")]

    assert covers_period(hours, _at(FRI, "23:00"), _at(SAT, "02:00"))


def test_a_period_from_sunday_into_monday_covers_a_request_across_the_weeks_end() -> None:
    """The timeline wraps, so Sunday's late hours still cover Monday's small ones."""
    hours = [_period(SUN, "20:00", MON, "04:00")]

    assert covers_period(hours, _at(SUN, "23:00"), _next_week_at(MON, "02:00"))


def test_sunday_hours_that_do_not_wrap_leave_monday_morning_uncovered() -> None:
    hours = [_period(SUN, "20:00", SUN, "23:30")]

    assert not covers_period(hours, _at(SUN, "23:00"), _next_week_at(MON, "02:00"))


# --------------------------------------------------------------------------
# raise_booking_request — AC2's refusal
# --------------------------------------------------------------------------


def test_a_request_before_the_venue_opens_is_refused_and_the_message_names_the_hours(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    with pytest.raises(ValidationError) as caught:
        raise_booking(venue, saved_event(), db_session, **_booked("08:00", "10:00"))

    assert caught.value.details == {
        "starts_at": [f"{OUTSIDE_HOURS} The venue is open 09:00-18:00 on Sunday."]
    }
    assert saved_requests(db_session) == []


def test_a_request_after_the_venue_closes_is_refused(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    with pytest.raises(ValidationError) as caught:
        raise_booking(venue, saved_event(), db_session, **_booked("17:00", "20:00"))

    assert caught.value.details == {
        "starts_at": [f"{OUTSIDE_HOURS} The venue is open 09:00-18:00 on Sunday."]
    }
    assert saved_requests(db_session) == []


@pytest.mark.parametrize(
    "hours",
    [(MON, "09:00", MON, "18:00"), (SAT, "18:00", SUN, "00:00")],
    ids=["open-only-on-monday", "saturday-closes-as-sunday-begins"],
)
def test_a_request_on_a_day_the_venue_is_closed_says_so(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
    hours: tuple[Weekday, str, Weekday, str],
) -> None:
    """The event's Sunday is closed.

    The venue opens only on another day, or its hours end at Sunday's midnight, which
    leaves none of Sunday open.
    """
    closed_on_sunday = make_venue(opening_periods=[_row(*hours)])
    save(closed_on_sunday)

    with pytest.raises(ValidationError) as caught:
        raise_booking(closed_on_sunday, saved_event(), db_session)

    assert caught.value.details == {
        "starts_at": [f"{OUTSIDE_HOURS} The venue is closed on Sunday."]
    }


def test_both_of_a_days_periods_are_named_when_a_request_falls_in_the_gap(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """A venue that shuts for lunch names both periods, so the refusal explains why."""
    split_day = make_venue(
        opening_periods=[_row(SUN, "09:00", SUN, "12:00"), _row(SUN, "13:00", SUN, "18:00")]
    )
    save(split_day)

    with pytest.raises(ValidationError) as caught:
        raise_booking(split_day, saved_event(), db_session, **_booked("11:00", "14:00"))

    assert caught.value.details == {
        "starts_at": [f"{OUTSIDE_HOURS} The venue is open 09:00-12:00, 13:00-18:00 on Sunday."]
    }


def test_an_overnight_opening_is_reported_as_the_part_that_falls_on_the_day(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """Open Saturday 20:00 to Sunday 04:00, the venue is open on Sunday, not closed."""
    overnight = make_venue(opening_periods=[_row(SAT, "20:00", SUN, "04:00")])
    save(overnight)

    with pytest.raises(ValidationError) as caught:
        raise_booking(overnight, saved_event(), db_session)

    assert caught.value.details == {
        "starts_at": [f"{OUTSIDE_HOURS} The venue is open 00:00-04:00 on Sunday."]
    }


def test_an_opening_that_runs_into_the_next_day_is_reported_up_to_midnight(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """Open Sunday 20:00 to Monday 04:00, Sunday's own part ends at midnight."""
    overnight = make_venue(opening_periods=[_row(SUN, "20:00", MON, "04:00")])
    save(overnight)

    with pytest.raises(ValidationError) as caught:
        raise_booking(overnight, saved_event(), db_session)

    assert caught.value.details == {
        "starts_at": [f"{OUTSIDE_HOURS} The venue is open 20:00-00:00 on Sunday."]
    }


def test_a_refused_overnight_request_names_the_hours_of_the_day_it_starts(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """Saturday 22:00 to Sunday 02:00 starts on Saturday, so Saturday's hours count."""
    two_days = make_venue(
        opening_periods=[_row(SAT, "09:00", SAT, "17:00"), _row(SUN, "10:00", SUN, "18:00")]
    )
    save(two_days)

    with pytest.raises(ValidationError) as caught:
        raise_booking(
            two_days,
            saved_event(),
            db_session,
            starts_at="2026-10-31T22:00:00+08:00",
            ends_at="2026-11-01T02:00:00+08:00",
        )

    assert caught.value.details == {
        "starts_at": [f"{OUTSIDE_HOURS} The venue is open 09:00-17:00 on Saturday."]
    }


def test_the_hours_are_refused_before_a_justification_is_asked_for(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """Hours can't be negotiated in the system, so there is no point writing one."""
    too_small = make_venue(capacity=10)
    save(too_small)

    with pytest.raises(ValidationError) as caught:
        raise_booking(too_small, saved_event(), db_session, **_booked("08:00", "10:00"))

    assert "justification" not in caught.value.details


def test_a_request_inside_the_hours_is_still_raised(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The check lets the default payload's 09:00-12:00 through unchanged."""
    request = raise_booking(venue, saved_event(), db_session)

    assert saved_requests(db_session) == [request]
