"""Unit tests for SCRUM-24 AC11: an Attendee opens an event they registered for.

They see what SCRUM-52 shows of any event (its name, description, date and time, and
each venue's name and location), plus their own registration and whether they may
still withdraw, as SCRUM-53 allows it: until the cut-off, or the start when there is
none. A Completed or Cancelled event still opens, read-only. Nobody else's event opens,
and nothing internal is shown (ADR-0109).

Runs against ``db_session``, so who registered for what is real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.registration.services import (
    MyRegisteredEvent,
    get_my_registered_event,
)
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from app.modules.venue.services import BookedVenue

pytestmark = pytest.mark.scrum_24

MakeOpenEvent = Callable[..., EventRequest]
MakeRegistration = Callable[..., Registration]
OpenAt = Callable[[str, datetime], MyRegisteredEvent]

ATTENDEE = 21
OTHER_ATTENDEE = 22
REFERENCE = "EVR-OPEN0001"

#: When the default open event starts: Tuesday 20 October 2026, 19:30 in Singapore.
EVENT_STARTS = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
#: When it ends, 22:00 in Singapore.
EVENT_ENDS = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
#: A withdrawal cut-off the day before, 19:30 in Singapore on Monday 19 October.
CUT_OFF = EVENT_STARTS - timedelta(days=1)
ONE_SECOND = timedelta(seconds=1)

#: The statuses whose page offers Withdraw: the event is still going ahead, confirmed
#: or sent back to planning after a change, where places stay held (ADR-0087).
WITHDRAWABLE_STATUSES = [
    EventRequestStatus.CONFIRMED,
    EventRequestStatus.APPROVED,
    EventRequestStatus.SAFETY_REVIEW,
]
#: Every other status, Completed and Cancelled among them: read-only (AC11). A draft is
#: never found at all, which its own test checks.
READ_ONLY_STATUSES = [
    status
    for status in EventRequestStatus
    if status not in WITHDRAWABLE_STATUSES and status is not EventRequestStatus.DRAFT
]


@pytest.fixture()
def open_at(db_session: Session) -> OpenAt:
    """Open an event by reference as the attendee, at a given moment."""

    def _open(reference: str, moment: datetime) -> MyRegisteredEvent:
        return get_my_registered_event(ATTENDEE, reference, session=db_session, now=moment)

    return _open


def _book(event: EventRequest, venue: Venue, status: BookingRequestStatus) -> VenueBookingRequest:
    """A venue arrangement for the whole of ``event``, in ``status``."""
    return VenueBookingRequest(
        event_id=event.id,
        venue_id=venue.id,
        starts_at=EVENT_STARTS,
        ends_at=EVENT_ENDS,
        purpose="Concert",
        expected_occupancy=80,
        status=status,
        requested_by=3,
    )


# --------------------------------------------------------------------------
# What the page shows: the public facts, the venues and the registration
# --------------------------------------------------------------------------


def test_the_event_shows_its_public_facts_venues_and_the_attendees_registration(
    now: datetime,
    open_at: OpenAt,
    save: Callable[..., None],
    make_venue: Callable[..., Venue],
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    event = make_open_event(cut_off=CUT_OFF)
    hall = make_venue(name="Main Hall", location="Building A, Level 1")
    save(hall)
    save(_book(event, hall, BookingRequestStatus.APPROVED))
    make_registration(event, ATTENDEE)

    shown = open_at(REFERENCE, now)

    assert shown == MyRegisteredEvent(
        id=event.id,
        reference=REFERENCE,
        name="Jazz by the Bay",
        description="An evening of music.",
        starts_at=EVENT_STARTS,
        ends_at=EVENT_ENDS,
        event_status="confirmed",
        venues=[BookedVenue(name="Main Hall", location="Building A, Level 1")],
        status=RegistrationStatus.REGISTERED,
        registered_at=now,
        withdrawn_at=None,
        withdrawals_close_at=CUT_OFF,
        can_withdraw=True,
    )


def test_a_venue_not_yet_approved_is_not_shown(
    now: datetime,
    open_at: OpenAt,
    save: Callable[..., None],
    venue: Venue,
    open_event: EventRequest,
    make_registration: MakeRegistration,
) -> None:
    """Only a booked venue is where the event takes place (ADR-0109)."""
    save(_book(open_event, venue, BookingRequestStatus.PENDING))
    make_registration(open_event, ATTENDEE)

    assert open_at(REFERENCE, now).venues == []


def test_the_reference_may_be_typed_in_any_case(
    now: datetime,
    open_at: OpenAt,
    open_event: EventRequest,
    make_registration: MakeRegistration,
) -> None:
    make_registration(open_event, ATTENDEE)

    assert open_at("evr-open0001", now).id == open_event.id


# --------------------------------------------------------------------------
# Withdraw, while SCRUM-53 allows it: until the cut-off, or the start
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("moment", "can_withdraw"),
    [(CUT_OFF - ONE_SECOND, True), (CUT_OFF, False)],
    ids=["just-before-the-cut-off", "at-the-cut-off"],
)
def test_withdrawing_is_offered_until_the_cut_off(
    open_at: OpenAt,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
    moment: datetime,
    can_withdraw: bool,
) -> None:
    make_registration(make_open_event(cut_off=CUT_OFF), ATTENDEE)

    shown = open_at(REFERENCE, moment)

    assert (shown.withdrawals_close_at, shown.can_withdraw) == (CUT_OFF, can_withdraw)


@pytest.mark.parametrize(
    ("moment", "can_withdraw"),
    [(EVENT_STARTS - ONE_SECOND, True), (EVENT_STARTS, False)],
    ids=["just-before-the-start", "at-the-start"],
)
def test_with_no_cut_off_withdrawing_is_offered_until_the_event_starts(
    open_at: OpenAt,
    open_event: EventRequest,
    make_registration: MakeRegistration,
    moment: datetime,
    can_withdraw: bool,
) -> None:
    make_registration(open_event, ATTENDEE)

    shown = open_at(REFERENCE, moment)

    assert (shown.withdrawals_close_at, shown.can_withdraw) == (EVENT_STARTS, can_withdraw)


@pytest.mark.parametrize("status", WITHDRAWABLE_STATUSES, ids=lambda status: status.value)
def test_withdrawing_is_offered_while_the_event_is_going_ahead(
    now: datetime,
    open_at: OpenAt,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
    status: EventRequestStatus,
) -> None:
    make_registration(make_open_event(status=status), ATTENDEE)

    shown = open_at(REFERENCE, now)

    assert (shown.event_status, shown.can_withdraw) == (status.value, True)


@pytest.mark.parametrize("status", READ_ONLY_STATUSES, ids=lambda status: status.value)
def test_every_other_event_status_opens_read_only_with_its_status(
    now: datetime,
    open_at: OpenAt,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
    status: EventRequestStatus,
) -> None:
    """Completed and Cancelled events still open, with no Withdraw (AC11)."""
    make_registration(make_open_event(status=status), ATTENDEE)

    shown = open_at(REFERENCE, now)

    assert (shown.event_status, shown.can_withdraw) == (status.value, False)


def test_the_status_lists_cover_every_status_with_completed_and_cancelled_read_only() -> None:
    """AC11 names these two; the rest of the read-only list is built from the enum."""
    assert {EventRequestStatus.COMPLETED, EventRequestStatus.CANCELLED} <= set(READ_ONLY_STATUSES)
    every_listed = {*WITHDRAWABLE_STATUSES, *READ_ONLY_STATUSES, EventRequestStatus.DRAFT}
    assert every_listed == set(EventRequestStatus)


def test_an_attendee_who_withdrew_still_opens_the_event_read_only(
    now: datetime,
    open_at: OpenAt,
    save: Callable[..., None],
    open_event: EventRequest,
    make_registration: MakeRegistration,
) -> None:
    registration = make_registration(open_event, ATTENDEE, registered_at=now - timedelta(days=1))
    registration.status = RegistrationStatus.WITHDRAWN
    registration.withdrawn_at = now
    save(registration)

    shown = open_at(REFERENCE, now)

    assert (shown.status, shown.withdrawn_at, shown.can_withdraw) == (
        RegistrationStatus.WITHDRAWN,
        now,
        False,
    )


def test_the_real_clock_decides_when_no_moment_is_given(
    db_session: Session, make_open_event: MakeOpenEvent, make_registration: MakeRegistration
) -> None:
    """The event is far off, so withdrawals are open whenever this runs."""
    make_registration(make_open_event(day=date(2099, 1, 1)), ATTENDEE)

    shown = get_my_registered_event(ATTENDEE, REFERENCE, session=db_session)

    assert shown.can_withdraw is True


# --------------------------------------------------------------------------
# Only the attendee who registered opens it; anything else is not found
# --------------------------------------------------------------------------


def test_an_event_the_attendee_never_registered_for_is_not_found(
    now: datetime,
    open_at: OpenAt,
    open_event: EventRequest,
    make_registration: MakeRegistration,
) -> None:
    """Another attendee's registration doesn't open it for this one (ADR-0012)."""
    make_registration(open_event, OTHER_ATTENDEE)

    with pytest.raises(NotFoundError) as exc_info:
        open_at(REFERENCE, now)

    assert (exc_info.value.status_code, exc_info.value.message) == (404, "Event not found.")


def test_an_unknown_reference_is_not_found_in_the_same_words(
    now: datetime, open_at: OpenAt, open_event: EventRequest
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        open_at("EVR-NOTHERE1", now)

    assert (exc_info.value.status_code, exc_info.value.message) == (404, "Event not found.")


def test_a_draft_is_not_found_even_with_a_registration_row(
    now: datetime,
    open_at: OpenAt,
    make_open_event: MakeOpenEvent,
    make_registration: MakeRegistration,
) -> None:
    """No draft can be registered for; a row pointing at one still finds nothing."""
    make_registration(make_open_event(status=EventRequestStatus.DRAFT), ATTENDEE)

    with pytest.raises(NotFoundError) as exc_info:
        open_at(REFERENCE, now)

    assert exc_info.value.message == "Event not found."
