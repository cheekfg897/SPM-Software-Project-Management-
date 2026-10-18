"""Unit tests for SCRUM-50 AC6 — Venue Staff hear when a buffer change hits a booking.

When a change to a venue's setup or turnaround time marks a confirmed booking
Conflicting (SCRUM-44, ADR-0045), every Venue Staff user is told, once for each booking
it newly marks, after the change is saved (ADR-0015, ADR-0035, ADR-0055). A booking that
was already Conflicting is not reported again, and a notice that can't be saved never
undoes the change.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventRequest
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.schemas import MESSAGE_BY_KIND
from app.modules.venue import services
from app.modules.venue.models import Booking, BookingStatus, Venue, VenueBlock
from tests.venue.conftest import VENUE_STAFF_ID, SaveBooking, SavedEvent, VenueWithBuffers, at

pytestmark = pytest.mark.scrum_50

CONFLICTING = NotificationKind.VENUE_BOOKING_CONFLICTING
#: A second Venue Staff user, saved beside ``saved_users``' user 4.
SECOND_STAFF_ID = 8
LONGER_TURNAROUND = {"turnaround_minutes": 45}


def _conflict_notices(session: Session) -> list[tuple[int, int, str, str | None]]:
    """(recipient, event id, reference, detail) of each Conflicting notice, in order."""
    notices = session.scalars(
        select(Notification).where(Notification.kind == CONFLICTING).order_by(Notification.id)
    )
    rows = []
    for notice in notices:
        rows.append(
            (notice.recipient_id, notice.event_request_id, notice.event_reference, notice.detail)
        )
    return rows


def _detail(venue: Venue) -> str:
    return (
        f"{venue.name}: a change to its setup or turnaround time makes this event's booking"
        " overlap another booking or a block."
    )


@pytest.fixture()
def two_staff(db_session: Session, saved_users: list[User], make_user: Callable[..., User]) -> None:
    """Venue Staff 4 (from ``saved_users``) and 8, beside users of every other role."""
    db_session.add(
        make_user(email="staff8@example.com", role=Role.VENUE_STAFF, user_id=SECOND_STAFF_ID)
    )
    db_session.commit()


@pytest.fixture()
def two_events(saved_event: SavedEvent) -> tuple[EventRequest, EventRequest]:
    """Two saved events, after a decoy, so no event's id matches a booking's."""
    saved_event()
    return saved_event(), saved_event()


def test_every_venue_staff_user_is_told_once_for_each_booking_the_change_marks(
    db_session: Session,
    two_staff: None,
    two_events: tuple[EventRequest, EventRequest],
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
) -> None:
    """The earlier booking is the later event's, so a mix-up of the two shows."""
    first_event, second_event = two_events
    venue = venue_with_buffers(0, 0)
    confirmed_booking(venue, at(9), at(10), event_id=second_event.id)
    confirmed_booking(venue, at(10, 30), at(11), event_id=first_event.id)

    services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    detail = _detail(venue)
    assert _conflict_notices(db_session) == [
        (VENUE_STAFF_ID, second_event.id, second_event.reference, detail),
        (SECOND_STAFF_ID, second_event.id, second_event.reference, detail),
        (VENUE_STAFF_ID, first_event.id, first_event.reference, detail),
        (SECOND_STAFF_ID, first_event.id, first_event.reference, detail),
    ]


def test_no_other_role_is_told(
    db_session: Session,
    saved_users: list[User],
    two_events: tuple[EventRequest, EventRequest],
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
) -> None:
    """``saved_users`` holds coordinators, an organiser and Technical Support too."""
    first_event, second_event = two_events
    venue = venue_with_buffers(0, 0)
    confirmed_booking(venue, at(9), at(10), event_id=first_event.id)
    confirmed_booking(venue, at(10, 30), at(11), event_id=second_event.id)

    services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    recipients = {notice.recipient_id for notice in db_session.scalars(select(Notification))}
    assert recipients == {VENUE_STAFF_ID}


def test_a_booking_that_now_runs_into_a_block_is_reported(
    db_session: Session,
    saved_users: list[User],
    saved_event: SavedEvent,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    make_block: Callable[..., VenueBlock],
    save: Callable[..., None],
) -> None:
    event = saved_event()
    venue = venue_with_buffers(0, 0)
    confirmed_booking(venue, at(9), at(10), event_id=event.id)
    save(make_block(venue, at(10, 15), at(10, 30)))

    services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    assert _conflict_notices(db_session) == [
        (VENUE_STAFF_ID, event.id, event.reference, _detail(venue))
    ]


def test_only_the_bookings_the_change_marks_are_reported(
    db_session: Session,
    saved_users: list[User],
    two_events: tuple[EventRequest, EventRequest],
    saved_event: SavedEvent,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
) -> None:
    """A far-off booking and another venue's overlapping pair are left out."""
    first_event, second_event = two_events
    decoy_event = saved_event()
    venue, other_venue = venue_with_buffers(0, 0), venue_with_buffers(0, 0)
    confirmed_booking(venue, at(9), at(10), event_id=first_event.id)
    confirmed_booking(venue, at(10, 30), at(11), event_id=second_event.id)
    confirmed_booking(venue, at(15), at(16), event_id=decoy_event.id)
    confirmed_booking(other_venue, at(9), at(10), event_id=decoy_event.id)
    confirmed_booking(other_venue, at(10, 30), at(11), event_id=decoy_event.id)

    services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    told_about = [event_id for _, event_id, _, _ in _conflict_notices(db_session)]
    assert told_about == [first_event.id, second_event.id]


@pytest.mark.parametrize(
    "change",
    [{"turnaround_minutes": 30}, {"capacity": 50}],
    ids=["turnaround-ends-as-next-starts", "another-field"],
)
def test_a_change_that_marks_nothing_tells_nobody(
    db_session: Session,
    saved_users: list[User],
    two_events: tuple[EventRequest, EventRequest],
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    change: dict[str, int],
) -> None:
    """The first booking's padding ends at 10:30, exactly as the second begins."""
    first_event, second_event = two_events
    venue = venue_with_buffers(0, 0)
    confirmed_booking(venue, at(9), at(10), event_id=first_event.id)
    confirmed_booking(venue, at(10, 30), at(11), event_id=second_event.id)

    services.update_venue(venue.id, change, session=db_session)

    assert _conflict_notices(db_session) == []


def test_a_booking_already_conflicting_is_not_reported_again(
    db_session: Session,
    saved_users: list[User],
    two_events: tuple[EventRequest, EventRequest],
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
) -> None:
    """A second, longer turnaround still overlaps the same pair: no duplicate notice."""
    first_event, second_event = two_events
    venue = venue_with_buffers(0, 0)
    first = confirmed_booking(venue, at(9), at(10), event_id=first_event.id)
    confirmed_booking(venue, at(10, 30), at(11), event_id=second_event.id)
    services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    services.update_venue(venue.id, {"turnaround_minutes": 50}, session=db_session)

    assert first.status is BookingStatus.CONFLICTING
    told_about = [event_id for _, event_id, _, _ in _conflict_notices(db_session)]
    assert told_about == [first_event.id, second_event.id]


def test_only_the_newly_marked_booking_is_reported_beside_one_already_conflicting(
    db_session: Session,
    saved_users: list[User],
    two_events: tuple[EventRequest, EventRequest],
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
) -> None:
    first_event, second_event = two_events
    venue = venue_with_buffers(0, 0)
    confirmed_booking(
        venue, at(9), at(10), event_id=first_event.id, status=BookingStatus.CONFLICTING
    )
    confirmed_booking(venue, at(10, 30), at(11), event_id=second_event.id)

    services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    told_about = [event_id for _, event_id, _, _ in _conflict_notices(db_session)]
    assert told_about == [second_event.id]


@pytest.mark.parametrize("event_id", [None, 999], ids=["no-event", "unknown-event"])
def test_a_booking_without_a_known_event_is_marked_but_nobody_is_told_about_it(
    db_session: Session,
    saved_users: list[User],
    saved_event: SavedEvent,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    event_id: int | None,
) -> None:
    """A notice needs an event to name, so only the booking with one is reported."""
    event = saved_event()
    venue = venue_with_buffers(0, 0)
    eventless = confirmed_booking(venue, at(9), at(10), event_id=event_id)
    confirmed_booking(venue, at(10, 30), at(11), event_id=event.id)

    services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    assert eventless.status is BookingStatus.CONFLICTING
    told_about = [told_event for _, told_event, _, _ in _conflict_notices(db_session)]
    assert told_about == [event.id]


def test_the_message_tells_venue_staff_a_booking_is_conflicting() -> None:
    assert MESSAGE_BY_KIND[CONFLICTING] == (
        "A confirmed booking is now Conflicting after a venue's setup or turnaround time changed."
    )


def test_a_failed_notification_keeps_the_saved_change_and_is_logged(
    db_session: Session,
    saved_users: list[User],
    saved_event: SavedEvent,
    venue_with_buffers: VenueWithBuffers,
    confirmed_booking: SaveBooking,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The change and the marks are saved first; failing would invite a retry."""
    event = saved_event()
    venue = venue_with_buffers(0, 0)
    booking = confirmed_booking(venue, at(9), at(10), event_id=event.id)
    confirmed_booking(venue, at(10, 30), at(11))
    real_commit = db_session.commit
    commits: list[str] = []

    def commit_unless_notifying() -> None:
        # The first commit saves the change and the marks; the second is the notice.
        commits.append("commit")
        if len(commits) == 2:
            raise OperationalError("INSERT", {}, Exception("database down"))
        real_commit()

    with (
        patch.object(db_session, "commit", side_effect=commit_unless_notifying),
        caplog.at_level(logging.WARNING, logger="connectsphere.venue"),
    ):
        services.update_venue(venue.id, LONGER_TURNAROUND, session=db_session)

    db_session.rollback()  # throws away anything that was not committed
    assert _conflict_notices(db_session) == []
    assert db_session.get(Booking, booking.id).status is BookingStatus.CONFLICTING
    assert db_session.get(Venue, venue.id).turnaround_minutes == 45
    assert [record.getMessage() for record in caplog.records] == [
        f"venue_booking_notification_failed reference={event.reference}"
    ]
