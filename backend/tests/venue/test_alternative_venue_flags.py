"""Unit tests for SCRUM-92 — flag bookings affected when a venue becomes unavailable.

AC1: a block over a confirmed booking or a Pending request marks it "Needs Alternative
Venue", with the reason and the period. AC2: the reason is a category with a note. AC8:
removing the block clears the flag and the booking stands. AC9: deactivating the venue
flags its future arrangements the same way, until it is reactivated (ADR-0053).

The services run against ``db_session``. The default arrangement is the ``saved_event``
fixture's, 09:00 to 12:00 on 1 November 2026 in Singapore, at a venue with no setup or
turnaround unless a test gives it some.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    BookingStatus,
    UnavailabilityCategory,
    Venue,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    DEACTIVATED_AT,
    DEACTIVATION,
    SECOND_PERIOD,
    SavedEvent,
    VenueWithBuffers,
    at,
    block,
    bookings,
    decide,
    raise_booking,
    reload_request,
    two_venues,
)

pytestmark = pytest.mark.scrum_92

Flag = tuple[UnavailabilityCategory, str, datetime, datetime | None, int | None]

#: AC1: a confirmed booking (an Approved arrangement) or a request Venue Staff can still
#: decide. Typed out here, from the AC, so the code's own list is checked against it.
FLAGGED_STATUSES = {
    BookingRequestStatus.PENDING,
    BookingRequestStatus.CONFLICTING,
    BookingRequestStatus.APPROVED,
}
NOT_FLAGGED_STATUSES = [status for status in BookingRequestStatus if status not in FLAGGED_STATUSES]
#: Tuesday 20 October 2026, 12:00 in Singapore: before the default arrangement.


def _flags(session: Session, request_id: int) -> list[Flag]:
    """The request's flags as (category, reason, starts, ends, block id), in order."""
    request = reload_request(session, request_id)
    rows = []
    for flag in request.flags:
        rows.append((flag.category, flag.reason, flag.starts_at, flag.ends_at, flag.venue_block_id))
    return rows


def _set_status(session: Session, request_id: int, status: BookingRequestStatus) -> None:
    session.execute(
        update(VenueBookingRequest)
        .where(VenueBookingRequest.id == request_id)
        .values(status=status)
    )
    session.commit()


def _approved(venue: Venue, saved_event: SavedEvent, session: Session) -> VenueBookingRequest:
    """An Approved arrangement at ``venue``: a confirmed booking (AC1)."""
    request = raise_booking(venue, saved_event(), session)
    return decide(request.id, "approved", session)


def _deactivate(venue: Venue, session: Session, **overrides: Any) -> Venue:
    return services.deactivate_venue(
        venue.id, {**DEACTIVATION, **overrides}, session=session, now=DEACTIVATED_AT
    )


# --------------------------------------------------------------------------
# AC1 — a block over a confirmed booking or a Pending request flags it
# --------------------------------------------------------------------------


def test_a_block_over_a_confirmed_booking_flags_it_with_the_reason_and_the_period(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    approved = _approved(venue, saved_event, db_session)

    blocked = block(
        venue, at(10), at(11), db_session, category="equipment_failure", reason="Lift broken."
    )

    flagged = reload_request(db_session, approved.id)
    assert flagged.needs_alternative_venue is True
    assert _flags(db_session, approved.id) == [
        (UnavailabilityCategory.EQUIPMENT_FAILURE, "Lift broken.", at(10), at(11), blocked.id)
    ]


def test_the_flagged_booking_keeps_its_status_and_still_holds_the_venue(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC4 and AC8: the flag is beside the booking; nothing is released until AC7."""
    approved = _approved(venue, saved_event, db_session)

    block(venue, at(10), at(11), db_session)

    assert reload_request(db_session, approved.id).status is BookingRequestStatus.APPROVED
    assert bookings(db_session) == [(venue.id, BookingStatus.CONFIRMED)]


@pytest.mark.parametrize("status", sorted(FLAGGED_STATUSES, key=lambda status: status.value))
def test_every_live_arrangement_is_flagged(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: BookingRequestStatus
) -> None:
    request = raise_booking(venue, saved_event(), db_session)
    _set_status(db_session, request.id, status)

    block(venue, at(10), at(11), db_session)

    assert reload_request(db_session, request.id).needs_alternative_venue is True


@pytest.mark.parametrize("status", NOT_FLAGGED_STATUSES)
def test_an_arrangement_that_no_longer_holds_or_asks_for_the_venue_is_not_flagged(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: BookingRequestStatus
) -> None:
    request = raise_booking(venue, saved_event(), db_session)
    _set_status(db_session, request.id, status)

    block(venue, at(10), at(11), db_session)

    assert _flags(db_session, request.id) == []
    assert reload_request(db_session, request.id).needs_alternative_venue is False


@pytest.mark.parametrize(
    ("block_start", "block_end", "flagged"),
    [
        pytest.param(at(7), at(9), False, id="ends as the booking starts"),
        pytest.param(at(7), at(9, 1), True, id="ends a minute into the booking"),
        pytest.param(at(12), at(14), False, id="starts as the booking ends"),
        pytest.param(at(11, 59), at(14), True, id="starts a minute before it ends"),
    ],
)
def test_a_block_flags_only_a_booking_it_overlaps(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    block_start: datetime,
    block_end: datetime,
    flagged: bool,
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    block(venue, block_start, block_end, db_session)

    assert reload_request(db_session, request.id).needs_alternative_venue is flagged


@pytest.mark.parametrize(
    ("block_start", "block_end", "flagged"),
    [
        pytest.param(at(7), at(8, 30), False, id="ends as the 30 minutes of setup start"),
        pytest.param(at(7), at(8, 31), True, id="ends a minute into the setup"),
        pytest.param(at(12, 15), at(14), False, id="starts as the 15 minutes of turnaround end"),
        pytest.param(at(12, 14), at(14), True, id="starts a minute before the turnaround ends"),
    ],
)
def test_a_block_over_the_setup_or_turnaround_flags_the_booking(
    db_session: Session,
    venue_with_buffers: VenueWithBuffers,
    saved_event: SavedEvent,
    block_start: datetime,
    block_end: datetime,
    flagged: bool,
) -> None:
    """The venue is held for setup and turnaround too, as ADR-0016 has it."""
    padded = venue_with_buffers(30, 15)
    request = raise_booking(padded, saved_event(), db_session)

    block(padded, block_start, block_end, db_session)

    assert reload_request(db_session, request.id).needs_alternative_venue is flagged


def test_a_block_flags_only_the_arrangements_at_its_own_venue(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    auditorium, breakout = two_venues(make_venue, save)
    at_auditorium = raise_booking(auditorium, saved_event(), db_session)
    at_breakout = raise_booking(breakout, saved_event(), db_session)

    block(auditorium, at(10), at(11), db_session)

    assert reload_request(db_session, at_auditorium.id).needs_alternative_venue is True
    assert reload_request(db_session, at_breakout.id).needs_alternative_venue is False


def test_a_block_leaves_another_events_arrangement_at_another_time_alone(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    morning = raise_booking(venue, saved_event(), db_session)
    afternoon = raise_booking(venue, saved_event(), db_session, **SECOND_PERIOD)

    block(venue, at(10), at(11), db_session)

    assert reload_request(db_session, morning.id).needs_alternative_venue is True
    assert reload_request(db_session, afternoon.id).needs_alternative_venue is False


def test_two_blocks_over_one_booking_each_leave_a_flag(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    first = block(venue, at(10), at(11), db_session)
    second = block(venue, at(9), at(10), db_session, category="safety_concern", reason="Leak.")

    assert _flags(db_session, request.id) == [
        (UnavailabilityCategory.SAFETY_CONCERN, "Leak.", at(9), at(10), second.id),
        (UnavailabilityCategory.MAINTENANCE, "Aircon repair.", at(10), at(11), first.id),
    ]


# --------------------------------------------------------------------------
# AC2 — the reason is one of five categories, with a note
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", list(UnavailabilityCategory))
def test_every_category_is_kept_on_the_block_and_the_flag(
    db_session: Session, venue: Venue, saved_event: SavedEvent, category: UnavailabilityCategory
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    blocked = block(venue, at(10), at(11), db_session, category=category.value)

    assert blocked.category is category
    assert _flags(db_session, request.id)[0][0] is category


def test_the_categories_are_the_five_the_story_names() -> None:
    assert [category.value for category in UnavailabilityCategory] == [
        "maintenance",
        "equipment_failure",
        "renovation",
        "safety_concern",
        "other",
    ]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        pytest.param(
            {"category": None}, {"category": ["Field may not be null."]}, id="no category"
        ),
        pytest.param(
            {"category": "flood"},
            {
                "category": [
                    "Category must be one of maintenance, equipment_failure, renovation,"
                    " safety_concern or other."
                ]
            },
            id="a category not on the list",
        ),
    ],
)
def test_a_block_without_a_listed_category_is_refused(
    db_session: Session, venue: Venue, changes: dict[str, Any], expected: dict[str, list[str]]
) -> None:
    with pytest.raises(ValidationError) as refusal:
        block(venue, at(10), at(11), db_session, **changes)

    assert refusal.value.details == expected
    assert services.list_venue_blocks(venue.id, session=db_session) == []


def test_a_block_that_leaves_out_the_category_is_refused(db_session: Session, venue: Venue) -> None:
    payload = {
        "start_time": at(10).isoformat(),
        "end_time": at(11).isoformat(),
        "reason": "Aircon repair.",
    }

    with pytest.raises(ValidationError) as refusal:
        services.block_venue(venue.id, payload, session=db_session)

    assert refusal.value.details == {"category": ["Missing data for required field."]}


# --------------------------------------------------------------------------
# AC8 — removing the block clears the flag and the booking stands
# --------------------------------------------------------------------------


def test_removing_the_block_clears_the_flag_and_the_booking_stands(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    approved = _approved(venue, saved_event, db_session)
    blocked = block(venue, at(10), at(11), db_session)

    services.remove_venue_block(venue.id, blocked.id, session=db_session)

    cleared = reload_request(db_session, approved.id)
    assert cleared.needs_alternative_venue is False
    assert _flags(db_session, approved.id) == []
    assert cleared.status is BookingRequestStatus.APPROVED
    assert bookings(db_session) == [(venue.id, BookingStatus.CONFIRMED)]


def test_removing_one_of_two_blocks_leaves_the_other_ones_flag(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(venue, saved_event(), db_session)
    removed = block(venue, at(10), at(11), db_session)
    kept = block(venue, at(11), at(12), db_session, category="other", reason="Filming.")

    services.remove_venue_block(venue.id, removed.id, session=db_session)

    assert _flags(db_session, request.id) == [
        (UnavailabilityCategory.OTHER, "Filming.", at(11), at(12), kept.id)
    ]
    assert reload_request(db_session, request.id).needs_alternative_venue is True


# --------------------------------------------------------------------------
# AC9 — deactivating the venue flags its future arrangements
# --------------------------------------------------------------------------


def test_deactivating_a_venue_flags_its_future_bookings_until_it_is_reactivated(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    approved = _approved(venue, saved_event, db_session)

    _deactivate(venue, db_session)

    assert _flags(db_session, approved.id) == [
        (UnavailabilityCategory.RENOVATION, "Closed for a refit.", DEACTIVATED_AT, None, None)
    ]
    assert reload_request(db_session, approved.id).needs_alternative_venue is True


@pytest.mark.parametrize(
    ("ends_after_deactivation", "flagged"),
    [
        pytest.param(timedelta(0), False, id="ended as the venue was deactivated"),
        pytest.param(timedelta(minutes=1), True, id="ends a minute after"),
    ],
)
def test_deactivating_flags_only_arrangements_that_have_not_ended(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    ends_after_deactivation: timedelta,
    flagged: bool,
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    services.deactivate_venue(
        venue.id,
        DEACTIVATION,
        session=db_session,
        now=request.ends_at - ends_after_deactivation,
    )

    assert reload_request(db_session, request.id).needs_alternative_venue is flagged


def test_deactivating_flags_only_the_arrangements_at_that_venue(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    auditorium, breakout = two_venues(make_venue, save)
    at_auditorium = raise_booking(auditorium, saved_event(), db_session)
    at_breakout = raise_booking(breakout, saved_event(), db_session)

    _deactivate(auditorium, db_session)

    assert reload_request(db_session, at_auditorium.id).needs_alternative_venue is True
    assert reload_request(db_session, at_breakout.id).needs_alternative_venue is False


@pytest.mark.parametrize("status", NOT_FLAGGED_STATUSES)
def test_deactivating_leaves_an_arrangement_that_no_longer_holds_the_venue_alone(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: BookingRequestStatus
) -> None:
    request = raise_booking(venue, saved_event(), db_session)
    _set_status(db_session, request.id, status)

    _deactivate(venue, db_session)

    assert _flags(db_session, request.id) == []


def test_deactivating_a_venue_that_is_already_inactive_flags_nothing_again(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(venue, saved_event(), db_session)
    _deactivate(venue, db_session)

    _deactivate(venue, db_session, category="other", reason="Still closed.")

    assert len(_flags(db_session, request.id)) == 1


def test_reactivating_clears_the_deactivations_flag_but_not_a_blocks(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(venue, saved_event(), db_session)
    blocked = block(venue, at(10), at(11), db_session)
    _deactivate(venue, db_session)

    services.reactivate_venue(venue.id, session=db_session)

    assert _flags(db_session, request.id) == [
        (UnavailabilityCategory.MAINTENANCE, "Aircon repair.", at(10), at(11), blocked.id)
    ]


def test_reactivating_clears_the_flag_and_the_booking_stands(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    approved = _approved(venue, saved_event, db_session)
    _deactivate(venue, db_session)

    services.reactivate_venue(venue.id, session=db_session)

    cleared = reload_request(db_session, approved.id)
    assert cleared.needs_alternative_venue is False
    assert cleared.status is BookingRequestStatus.APPROVED
    assert bookings(db_session) == [(venue.id, BookingStatus.CONFIRMED)]


def test_reactivating_one_venue_leaves_another_deactivated_venues_flags(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    auditorium, breakout = two_venues(make_venue, save)
    at_auditorium = raise_booking(auditorium, saved_event(), db_session)
    at_breakout = raise_booking(breakout, saved_event(), db_session)
    _deactivate(auditorium, db_session)
    _deactivate(breakout, db_session)

    services.reactivate_venue(auditorium.id, session=db_session)

    assert reload_request(db_session, at_auditorium.id).needs_alternative_venue is False
    assert reload_request(db_session, at_breakout.id).needs_alternative_venue is True


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(
            {},
            {
                "category": ["Missing data for required field."],
                "reason": ["Missing data for required field."],
            },
            id="nothing said",
        ),
        pytest.param(
            {"category": "renovation", "reason": "   "},
            {"reason": ["Must not be blank."]},
            id="a blank note",
        ),
        pytest.param(
            {"category": "renovation", "reason": "x" * 501},
            {"reason": ["Reason must be at most 500 characters."]},
            id="a note over 500 characters",
        ),
    ],
)
def test_a_deactivation_needs_a_category_and_a_note(
    db_session: Session, venue: Venue, payload: dict[str, Any], expected: dict[str, list[str]]
) -> None:
    with pytest.raises(ValidationError) as refusal:
        services.deactivate_venue(venue.id, payload, session=db_session)

    assert refusal.value.details == expected
    assert venue.is_active is True


def test_a_deactivations_note_is_kept_trimmed(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    request = raise_booking(venue, saved_event(), db_session)

    _deactivate(venue, db_session, reason="  Closed for a refit.  ")

    assert _flags(db_session, request.id)[0][1] == "Closed for a refit."
