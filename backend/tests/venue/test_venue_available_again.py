"""Unit tests for SCRUM-92 AC8 — the coordinator is told the venue is available again.

When Venue Staff remove a block, or reactivate a venue, before a replacement is
approved, the flag clears, the original arrangement stands and the event's assigned
coordinator is notified that the venue is available again (Product Owner, 19 Oct). The
notice names the venue and the event, and adds that the event still needs Safety Review
and confirmation when the venue sent it back from Confirmed to Approved (Product Owner,
25 Oct). One notice per event with an arrangement left with no unavailability flag; one
another block still covers is not told (ADR-0100, ADR-0108). A notice that can't be
saved loses only itself (ADR-0015).

AC9, AC10 (Product Owner, 26 Oct): for an event a venue sent back from Confirmed, the
Organiser who submitted it is told too, once per event, naming the venue, the event and
the category.

The services run against ``db_session``; the event is the ``saved_event`` fixture's,
assigned to coordinator 3, with an arrangement from 09:00 to 12:00 on 1 November 2026
at Main Hall.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events import services as event_services
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue import services
from app.modules.venue.models import (
    BookingRequestStatus,
    Venue,
    VenueBlock,
    VenueBookingRequest,
)
from tests.venue.conftest import (
    COORDINATOR_ID,
    DEACTIVATED_AT,
    DEACTIVATION,
    SavedEvent,
    at,
    block,
    decide,
    raise_booking,
    record_confirmation,
    reload_event,
    reload_request,
    two_venues,
)

pytestmark = pytest.mark.scrum_92

#: A coordinator who did not raise the request; the event is reassigned to them.
REASSIGNED_COORDINATOR_ID = 9
MAIN_HALL_AGAIN = "Main Hall is available again for Partner Summit. Your original booking stands."
#: What the notice adds when the venue sent the event back from Confirmed to Approved.
STILL_NEEDS_SAFETY_REVIEW = " It still needs Safety Review and confirmation."
ORGANISER_ID = 7
#: What the organiser of an event sent back is told (AC9): the venue, the event and the
#: category, as their notice of the return named it (AC3).
ORGANISER_TOLD = (
    "Main Hall is available again for Partner Summit after being unavailable ({category})."
    " Your original booking stands. The event still needs Safety Review and confirmation."
)
#: The statuses in which an arrangement still holds or asks for its venue, so a block
#: flags it (AC1, ADR-0100). Typed out, so the code's own list is checked against it.
LIVE_STATUSES = {
    BookingRequestStatus.PENDING,
    BookingRequestStatus.CONFLICTING,
    BookingRequestStatus.ON_HOLD,
    BookingRequestStatus.APPROVED,
}
NOT_LIVE_STATUSES = [status for status in BookingRequestStatus if status not in LIVE_STATUSES]
LOST_CONNECTION = OperationalError("INSERT INTO notifications", {}, Exception("lost"))


def _lose_connection(*_: Any, **__: Any) -> None:
    raise LOST_CONNECTION


def _notifications_again(user_id: int) -> list[Notification]:
    """The user's "available again" notifications, newest first.

    Only this kind: the blocks and decisions set up here notify the coordinator too.
    """
    notices = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is NotificationKind.VENUE_AVAILABLE_AGAIN:
            notices.append(notification)
    return notices


def _told_again(user_id: int) -> list[tuple[int, str | None]]:
    """The user's "available again" notices as (event id, detail), newest first."""
    rows = []
    for notification in _notifications_again(user_id):
        rows.append((notification.event_request_id, notification.detail))
    return rows


def _set_status(session: Session, request_id: int, status: BookingRequestStatus) -> None:
    session.execute(
        update(VenueBookingRequest)
        .where(VenueBookingRequest.id == request_id)
        .values(status=status)
    )
    session.commit()


def _remove(venue: Venue, venue_block: VenueBlock, session: Session) -> None:
    services.remove_venue_block(venue.id, venue_block.id, session=session)


def _deactivate(venue: Venue, session: Session) -> None:
    services.deactivate_venue(venue.id, DEACTIVATION, session=session, now=DEACTIVATED_AT)


def _approved(
    venue: Venue, saved_event: SavedEvent, session: Session
) -> tuple[EventRequest, VenueBookingRequest]:
    """An approved event whose arrangement at ``venue`` is Approved: a booking."""
    event = saved_event()
    approved = decide(raise_booking(venue, event, session).id, "approved", session)
    return event, approved


def _confirmed(venue: Venue, saved_event: SavedEvent, session: Session) -> EventRequest:
    """A Confirmed event booked at ``venue``, which a block will send back (AC3)."""
    event, _ = _approved(venue, saved_event, session)
    event.status = EventRequestStatus.CONFIRMED
    session.commit()
    return event


def _recipients_told_again(session: Session) -> set[int]:
    """Everyone who got an "available again" notice, whatever the event."""
    stmt = select(Notification.recipient_id).where(
        Notification.kind == NotificationKind.VENUE_AVAILABLE_AGAIN
    )
    return set(session.scalars(stmt))


# --------------------------------------------------------------------------
# AC8 — removing a block or reactivating the venue tells the coordinator
# --------------------------------------------------------------------------


def test_removing_the_block_tells_the_coordinator_the_venue_is_available_again(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, approved = _approved(venue, saved_event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN)]
    standing = reload_request(db_session, approved.id)
    assert standing.status is BookingRequestStatus.APPROVED
    assert standing.needs_alternative_venue is False


def test_reactivating_the_venue_tells_the_coordinator_the_venue_is_available_again(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, _ = _approved(venue, saved_event, db_session)
    _deactivate(venue, db_session)

    services.reactivate_venue(venue.id, session=db_session)

    assert _told_again(COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN)]


def test_the_notice_names_what_happened_and_links_to_the_event(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, _ = _approved(venue, saved_event, db_session)
    _remove(venue, block(venue, at(10), at(11), db_session), db_session)

    [notice] = _notifications_again(COORDINATOR_ID)
    shown = NotificationSchema().dump(notice)

    assert shown["message"] == "A venue that was unavailable for your event is available again."
    assert shown["event_name"] == "Partner Summit"
    assert shown["link"] == f"/events/{event.reference}"


@pytest.mark.parametrize("status", sorted(LIVE_STATUSES, key=lambda status: status.value))
def test_every_live_arrangement_is_told_about(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: BookingRequestStatus
) -> None:
    event = saved_event()
    request = raise_booking(venue, event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)
    _set_status(db_session, request.id, status)

    _remove(venue, venue_block, db_session)

    assert _told_again(COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN)]


@pytest.mark.parametrize("status", NOT_LIVE_STATUSES)
def test_an_arrangement_that_no_longer_holds_or_asks_for_the_venue_is_not_told_about(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: BookingRequestStatus
) -> None:
    """Released by its replacement, say: it no longer needs anything (AC7)."""
    request = raise_booking(venue, saved_event(), db_session)
    venue_block = block(venue, at(10), at(11), db_session)
    _set_status(db_session, request.id, status)

    _remove(venue, venue_block, db_session)

    assert _told_again(COORDINATOR_ID) == []


def test_an_arrangement_another_block_still_covers_is_told_only_once_the_last_one_goes(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """ADR-0100 default: its venue is not available again while one block is left."""
    event, _ = _approved(venue, saved_event, db_session)
    first = block(venue, at(10), at(11), db_session)
    second = block(venue, at(11), at(12), db_session, category="other", reason="Filming.")

    _remove(venue, first, db_session)
    told_after_first = _told_again(COORDINATOR_ID)
    _remove(venue, second, db_session)

    assert told_after_first == []
    assert _told_again(COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN)]


def test_an_arrangement_two_overlapping_blocks_cover_is_told_only_once_both_are_gone(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The Product Owner, 25 Oct: "available again" only once nothing else covers it."""
    event, _ = _approved(venue, saved_event, db_session)
    first = block(venue, at(9), at(11), db_session)
    second = block(venue, at(10), at(12), db_session, category="other", reason="Filming.")

    _remove(venue, first, db_session)
    told_after_first = _told_again(COORDINATOR_ID)
    _remove(venue, second, db_session)

    assert told_after_first == []
    assert _told_again(COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN)]


def test_removing_a_block_from_a_venue_still_deactivated_tells_nobody(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The deactivation still covers the arrangement, so its venue is not available."""
    _approved(venue, saved_event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)
    _deactivate(venue, db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(COORDINATOR_ID) == []


def test_reactivating_a_venue_a_block_still_covers_tells_nobody(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    _approved(venue, saved_event, db_session)
    block(venue, at(10), at(11), db_session)
    _deactivate(venue, db_session)

    services.reactivate_venue(venue.id, session=db_session)

    assert _told_again(COORDINATOR_ID) == []


def test_only_the_arrangements_the_block_flagged_are_told_about(
    db_session: Session,
    make_venue: Callable[..., Venue],
    save: Callable[..., None],
    saved_event: SavedEvent,
) -> None:
    """The afternoon arrangement and the one at another venue are decoys (ADR-0100)."""
    auditorium, breakout = two_venues(make_venue, save)
    morning_event = saved_event()
    raise_booking(auditorium, morning_event, db_session)
    raise_booking(
        auditorium,
        saved_event(),
        db_session,
        starts_at=at(13).isoformat(),
        ends_at=at(15).isoformat(),
    )
    raise_booking(breakout, saved_event(), db_session)
    morning_block = block(auditorium, at(10), at(11), db_session)
    block(breakout, at(10), at(11), db_session)

    _remove(auditorium, morning_block, db_session)

    assert _told_again(COORDINATOR_ID) == [
        (
            morning_event.id,
            "Auditorium is available again for Partner Summit. Your original booking stands.",
        )
    ]


def test_an_event_sent_back_from_confirmed_is_told_it_still_needs_safety_review(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The Product Owner, 25 Oct: nothing is confirmed again automatically (AC8)."""
    event = _confirmed(venue, saved_event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN + STILL_NEEDS_SAFETY_REVIEW)]
    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED


def test_an_event_confirmed_again_since_it_was_sent_back_is_not_told_it_needs_review(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """Only a return to Approved not yet followed by a confirmation counts (ADR-0108).

    The event went back once, was confirmed again, and is Approved now for another
    reason; a later block finds it Approved, so it didn't send it back.
    """
    event = _confirmed(venue, saved_event, db_session)
    _remove(venue, block(venue, at(10), at(11), db_session), db_session)
    record_confirmation(event, db_session)
    later_block = block(venue, at(10), at(11), db_session)

    _remove(venue, later_block, db_session)

    assert _told_again(COORDINATOR_ID)[0] == (event.id, MAIN_HALL_AGAIN)
    # The organiser heard of the first return's end, and nothing of the later block.
    assert len(_told_again(ORGANISER_ID)) == 1


def test_an_event_with_two_arrangements_freed_is_told_once(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """It names the venue and the event, so a second would say the same (ADR-0108)."""
    event, _ = _approved(venue, saved_event, db_session)
    raise_booking(
        venue, event, db_session, starts_at=at(13).isoformat(), ends_at=at(15).isoformat()
    )
    venue_block = block(venue, at(8), at(16), db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN)]


# --------------------------------------------------------------------------
# AC9, AC10 — the organiser of an event sent back hears the venue is available again
# --------------------------------------------------------------------------


def test_the_organiser_of_an_event_sent_back_is_told_the_venue_is_available_again(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """The Product Owner, 26 Oct: the Organiser is told how the return resolves."""
    event = _confirmed(venue, saved_event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(ORGANISER_ID) == [(event.id, ORGANISER_TOLD.format(category="maintenance"))]
    [notice] = _notifications_again(ORGANISER_ID)
    shown = NotificationSchema().dump(notice)
    assert shown["message"] == "A venue that was unavailable for your event is available again."
    assert shown["link"] == f"/events/{event.reference}"


def test_the_organiser_is_told_when_the_venue_is_reactivated(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event = _confirmed(venue, saved_event, db_session)
    _deactivate(venue, db_session)

    services.reactivate_venue(venue.id, session=db_session)

    assert _told_again(ORGANISER_ID) == [(event.id, ORGANISER_TOLD.format(category="renovation"))]


@pytest.mark.parametrize(
    "status",
    [status for status in EventRequestStatus if status is not EventRequestStatus.CONFIRMED],
)
def test_the_organiser_of_an_event_the_venue_did_not_send_back_is_not_told(
    db_session: Session, venue: Venue, saved_event: SavedEvent, status: EventRequestStatus
) -> None:
    """Not Confirmed when the block came, so its status stayed as it was (AC3, AC9)."""
    event, _ = _approved(venue, saved_event, db_session)
    event.status = status
    db_session.commit()
    venue_block = block(venue, at(10), at(11), db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(ORGANISER_ID) == []


def test_the_organiser_waits_for_the_last_overlapping_block_too(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC9 sends it under AC8's condition: nothing else still covers the booking."""
    event = _confirmed(venue, saved_event, db_session)
    first = block(venue, at(9), at(11), db_session)
    second = block(venue, at(10), at(12), db_session, category="other", reason="Filming.")

    _remove(venue, first, db_session)
    told_after_first = _told_again(ORGANISER_ID)
    _remove(venue, second, db_session)

    assert told_after_first == []
    # The block left standing was the "other" one, so that is the category named.
    assert _told_again(ORGANISER_ID) == [(event.id, ORGANISER_TOLD.format(category="other"))]


def test_the_organiser_is_told_once_however_many_arrangements_are_freed(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    """AC10: once per event."""
    event, _ = _approved(venue, saved_event, db_session)
    raise_booking(
        venue, event, db_session, starts_at=at(13).isoformat(), ends_at=at(15).isoformat()
    )
    event.status = EventRequestStatus.CONFIRMED
    db_session.commit()
    venue_block = block(venue, at(8), at(16), db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(ORGANISER_ID) == [(event.id, ORGANISER_TOLD.format(category="maintenance"))]


def test_only_the_coordinator_and_the_submitting_organiser_are_told(
    db_session: Session, venue: Venue, saved_event: SavedEvent, saved_users: list[User]
) -> None:
    """AC10: the Organiser who submitted the event, not every user who could see it."""
    event = _confirmed(venue, saved_event, db_session)
    event.organisation_id = 3
    db_session.commit()
    venue_block = block(venue, at(10), at(11), db_session)

    _remove(venue, venue_block, db_session)

    assert _recipients_told_again(db_session) == {COORDINATOR_ID, ORGANISER_ID}


def test_removing_a_block_that_flagged_nothing_tells_nobody(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    _approved(venue, saved_event, db_session)
    venue_block = block(venue, at(13), at(14), db_session)

    _remove(venue, venue_block, db_session)

    assert _told_again(COORDINATOR_ID) == []


def test_reactivating_a_venue_that_was_not_deactivated_tells_nobody(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    _approved(venue, saved_event, db_session)

    services.reactivate_venue(venue.id, session=db_session)

    assert _told_again(COORDINATOR_ID) == []


def test_the_coordinator_assigned_now_is_told(
    db_session: Session, venue: Venue, saved_event: SavedEvent
) -> None:
    event, _ = _approved(venue, saved_event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)
    event.coordinator_id = REASSIGNED_COORDINATOR_ID
    db_session.commit()

    _remove(venue, venue_block, db_session)

    assert _told_again(REASSIGNED_COORDINATOR_ID) == [(event.id, MAIN_HALL_AGAIN)]
    assert _told_again(COORDINATOR_ID) == []


def test_an_event_with_no_coordinator_stands_again_and_nobody_is_told(
    db_session: Session, venue: Venue, saved_event: SavedEvent, caplog: pytest.LogCaptureFixture
) -> None:
    event, approved = _approved(venue, saved_event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)
    event.coordinator_id = None
    db_session.commit()

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _remove(venue, venue_block, db_session)

    assert reload_request(db_session, approved.id).needs_alternative_venue is False
    assert _told_again(COORDINATOR_ID) == []
    assert f"event_request_unassigned reference={event.reference}" in caplog.text


def test_a_notice_that_cannot_be_saved_leaves_the_block_removed_and_the_flag_cleared(
    db_session: Session,
    venue: Venue,
    saved_event: SavedEvent,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The removal is committed before the notice is sent (ADR-0015)."""
    _, approved = _approved(venue, saved_event, db_session)
    venue_block = block(venue, at(10), at(11), db_session)
    monkeypatch.setattr(event_services, "notify_users", _lose_connection)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _remove(venue, venue_block, db_session)

    db_session.rollback()
    assert services.list_venue_blocks(venue.id, session=db_session) == []
    assert reload_request(db_session, approved.id).needs_alternative_venue is False
    assert "kind=venue_available_again" in caplog.text
