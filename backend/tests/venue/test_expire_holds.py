"""Unit tests for SCRUM-94 — tentative holds expire automatically, with a warning first.

``expire_holds`` marks each hold whose expiry has passed, and its request, Expired, and
tells the event's coordinator. ``send_hold_expiry_warnings`` tells them 24 hours before.
Both take the instant to compare with, so the boundaries are tested exactly, and both
can be run again without repeating anything (ADR-0052). The command that runs them is in
``test_expire_holds_command.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.modules.auth.permissions import Role
from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.events.services import list_event_history
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from tests.venue.conftest import (
    COORDINATOR_ID,
    SINGAPORE,
    at,
    change_expiry,
    decide,
    hours_from_now,
    place_hold,
    raise_booking,
)

pytestmark = pytest.mark.scrum_94

#: The other Event Coordinator ``saved_users`` saves, for an event reassigned to them.
OTHER_COORDINATOR_ID = 9
WARNING_LEAD = timedelta(hours=24)
JUST = timedelta(microseconds=1)


def _status(request: VenueBookingRequest, session: Session) -> BookingRequestStatus:
    """The request's status as saved, not as the session last saw it."""
    session.expire_all()
    return session.get(VenueBookingRequest, request.id).status


def _notices(kind: NotificationKind, session: Session) -> list[tuple[int, str | None]]:
    """Who got a notification of ``kind``, and its detail, oldest first."""
    query = select(Notification).where(Notification.kind == kind).order_by(Notification.id)
    return [(notice.recipient_id, notice.detail) for notice in session.scalars(query)]


def _in_business_time(moment: datetime) -> str:
    """How a notice's detail gives an expiry: ISO 8601 in Singapore time."""
    return moment.astimezone(SINGAPORE).isoformat()


def _expire(now: datetime, session: Session) -> list[int]:
    """Run the expiry at ``now``; the ids of the requests it expired."""
    return [request.id for request in services.expire_holds(now=now, session=session)]


def _warn(now: datetime, session: Session) -> list[int]:
    """Send the warnings due at ``now``; the ids of the requests warned about."""
    return [request.id for request in services.send_hold_expiry_warnings(now=now, session=session)]


def _second_request(event: EventRequest, session: Session) -> VenueBookingRequest:
    """The multi-venue event's other request: 13:00-16:00 at a second venue."""
    return services.list_active_arrangements(event.id, session=session)[1]


@pytest.fixture()
def expires_at() -> datetime:
    """The expiry the tests hold the first request until: two days from now."""
    return hours_from_now(48)


@pytest.fixture()
def held_request(
    db_session: Session, multi_venue_request: VenueBookingRequest, expires_at: datetime
) -> VenueBookingRequest:
    """The multi-venue event's first request, On Hold until ``expires_at``."""
    return place_hold(multi_venue_request.id, expires_at, db_session)


# --------------------------------------------------------------------------
# AC1 — a hold whose expiry passes becomes Expired, with nobody acting
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "after_expiry",
    [pytest.param(timedelta(0), id="at the expiry"), pytest.param(JUST, id="just after")],
)
def test_a_hold_is_expired_from_the_instant_its_expiry_passes(
    db_session: Session,
    held_request: VenueBookingRequest,
    expires_at: datetime,
    after_expiry: timedelta,
) -> None:
    """The expiry instant itself counts as expired, as it does when read (ADR-0045)."""
    expired = _expire(expires_at + after_expiry, db_session)

    assert expired == [held_request.id]
    assert _status(held_request, db_session) is BookingRequestStatus.EXPIRED


def test_a_hold_just_before_its_expiry_stays_on_hold(
    db_session: Session, held_request: VenueBookingRequest, expires_at: datetime
) -> None:
    expired = _expire(expires_at - JUST, db_session)

    assert expired == []
    assert _status(held_request, db_session) is BookingRequestStatus.ON_HOLD


def test_only_the_hold_that_has_run_out_is_expired(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    """A hold at another venue expiring later, and a Pending request, are left alone.

    The Pending one is at the held venue on the next day: the same slot would be refused
    while the hold stands (SCRUM-42 AC7).
    """
    second = _second_request(multi_venue_event, db_session)
    place_hold(second.id, expires_at + timedelta(days=2), db_session)
    pending = raise_booking(
        db_session.get(Venue, held_request.venue_id),
        multi_venue_event,
        db_session,
        starts_at="2026-11-02T09:00:00+08:00",
        ends_at="2026-11-02T12:00:00+08:00",
    )

    expired = _expire(expires_at + timedelta(days=1), db_session)

    assert expired == [held_request.id]
    assert _status(second, db_session) is BookingRequestStatus.ON_HOLD
    assert _status(pending, db_session) is BookingRequestStatus.PENDING


@pytest.mark.parametrize("outcome", ["approved", "rejected"])
def test_a_hold_already_approved_or_rejected_is_not_expired(
    db_session: Session, held_request: VenueBookingRequest, expires_at: datetime, outcome: str
) -> None:
    """A rejected hold's booking keeps its expiry; its status is what rules it out."""
    decide(held_request.id, outcome, db_session, reason="Decided")

    expired = _expire(expires_at + timedelta(days=1), db_session)

    assert expired == []
    assert _status(held_request, db_session) is BookingRequestStatus(outcome)
    assert _notices(NotificationKind.VENUE_HOLD_EXPIRED, db_session) == []


def test_running_the_expiry_again_changes_and_sends_nothing_more(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    after_expiry = expires_at + timedelta(hours=1)
    _expire(after_expiry, db_session)

    expired_again = _expire(after_expiry + timedelta(hours=1), db_session)

    assert expired_again == []
    assert len(_notices(NotificationKind.VENUE_HOLD_EXPIRED, db_session)) == 1
    history = list_event_history(
        COORDINATOR_ID,
        multi_venue_event.reference,
        viewer_role=Role.EVENT_COORDINATOR,
        session=db_session,
    )
    hold_entries = [entry for entry in history if entry.kind is EventHistoryKind.VENUE_HOLD_EXPIRED]
    assert len(hold_entries) == 1


# --------------------------------------------------------------------------
# AC2 — the venue is free again and the coordinator can raise a new request
# --------------------------------------------------------------------------


def test_after_expiry_a_new_request_for_the_same_slot_can_be_raised_and_approved(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
    pin_now: Callable[[datetime], None],
) -> None:
    pin_now(expires_at)
    _expire(expires_at, db_session)
    venue = db_session.get(Venue, held_request.venue_id)

    replacement = raise_booking(venue, multi_venue_event, db_session)
    approved = decide(replacement.id, "approved", db_session)

    assert approved.status is BookingRequestStatus.APPROVED
    assert (approved.starts_at, approved.ends_at) == (at(9), at(12))


def test_an_expired_arrangement_still_counts_until_the_coordinator_withdraws_it(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    """Like a rejected one, it keeps the event waiting until withdrawn (ADR-0052)."""
    _expire(expires_at, db_session)
    counted = services.count_active_arrangements(multi_venue_event.id, session=db_session)

    services.withdraw_arrangement(
        multi_venue_event.reference,
        held_request.id,
        coordinator_id=COORDINATOR_ID,
        session=db_session,
    )

    assert counted == 2
    assert _status(held_request, db_session) is BookingRequestStatus.WITHDRAWN
    assert services.count_active_arrangements(multi_venue_event.id, session=db_session) == 1


# --------------------------------------------------------------------------
# AC5 — an expired hold is never treated as a confirmed booking
# --------------------------------------------------------------------------


def test_an_expired_request_leaves_the_queue_and_cannot_be_approved(
    db_session: Session, held_request: VenueBookingRequest, expires_at: datetime
) -> None:
    _expire(expires_at, db_session)

    queue = services.list_pending_booking_requests(session=db_session)
    with pytest.raises(ConflictError) as refusal:
        decide(held_request.id, "approved", db_session)

    assert held_request.id not in [entry.request.id for entry in queue]
    assert refusal.value.message == "Only a pending request can be decided; this one is expired."


# --------------------------------------------------------------------------
# AC3 — the coordinator is warned 24 hours before, and told when it expires
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before_expiry", "warned"),
    [
        pytest.param(WARNING_LEAD + JUST, False, id="just outside 24 hours"),
        pytest.param(WARNING_LEAD, True, id="exactly 24 hours"),
        pytest.param(JUST, True, id="just before the expiry"),
        pytest.param(timedelta(0), False, id="at the expiry: expired, not warned"),
    ],
)
def test_the_warning_is_sent_once_the_hold_is_within_24_hours_of_its_expiry(
    db_session: Session,
    held_request: VenueBookingRequest,
    expires_at: datetime,
    before_expiry: timedelta,
    warned: bool,
) -> None:
    warned_about = _warn(expires_at - before_expiry, db_session)

    assert warned_about == ([held_request.id] if warned else [])
    assert len(_notices(NotificationKind.VENUE_HOLD_EXPIRING, db_session)) == int(warned)


def test_the_warning_and_the_expiry_notice_go_to_the_assigned_coordinator(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    """Not to whoever raised the request: the event has moved to another coordinator."""
    multi_venue_event.coordinator_id = OTHER_COORDINATOR_ID
    db_session.commit()

    _warn(expires_at - timedelta(hours=1), db_session)
    _expire(expires_at, db_session)

    expiry = _in_business_time(expires_at)
    assert _notices(NotificationKind.VENUE_HOLD_EXPIRING, db_session) == [
        (OTHER_COORDINATOR_ID, expiry)
    ]
    assert _notices(NotificationKind.VENUE_HOLD_EXPIRED, db_session) == [
        (OTHER_COORDINATOR_ID, expiry)
    ]


def test_sending_the_warnings_again_sends_nothing_more(
    db_session: Session, held_request: VenueBookingRequest, expires_at: datetime
) -> None:
    _warn(expires_at - timedelta(hours=2), db_session)

    warned_again = _warn(expires_at - timedelta(hours=1), db_session)

    assert warned_again == []
    assert len(_notices(NotificationKind.VENUE_HOLD_EXPIRING, db_session)) == 1


def test_only_holds_due_a_warning_are_warned_about(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    """A hold at another venue still days away, and a rejected hold, get no warning."""
    second = _second_request(multi_venue_event, db_session)
    place_hold(second.id, expires_at + timedelta(days=3), db_session)
    decide(held_request.id, "rejected", db_session, reason="Not needed")

    warned_about = _warn(expires_at - timedelta(hours=1), db_session)

    assert warned_about == []
    assert _notices(NotificationKind.VENUE_HOLD_EXPIRING, db_session) == []


# --------------------------------------------------------------------------
# AC4 — a changed expiry moves the expiry and the warning, and is announced
# --------------------------------------------------------------------------


def test_a_hold_whose_expiry_was_moved_later_is_not_expired_at_the_old_time(
    db_session: Session, held_request: VenueBookingRequest, expires_at: datetime
) -> None:
    change_expiry(held_request.id, expires_at + timedelta(days=2), db_session)

    expired = _expire(expires_at + timedelta(hours=1), db_session)

    assert expired == []
    assert _status(held_request, db_session) is BookingRequestStatus.ON_HOLD


def test_the_warning_follows_a_changed_expiry(
    db_session: Session, held_request: VenueBookingRequest, expires_at: datetime
) -> None:
    """Warned about the first expiry, then moved: warned again only near the new one."""
    _warn(expires_at - timedelta(hours=1), db_session)
    new_expiry = expires_at + timedelta(days=2)
    change_expiry(held_request.id, new_expiry, db_session)

    at_the_old_window = _warn(expires_at - timedelta(minutes=30), db_session)
    at_the_new_window = _warn(new_expiry - timedelta(hours=1), db_session)

    assert at_the_old_window == []
    assert at_the_new_window == [held_request.id]
    assert _notices(NotificationKind.VENUE_HOLD_EXPIRING, db_session) == [
        (COORDINATOR_ID, _in_business_time(expires_at)),
        (COORDINATOR_ID, _in_business_time(new_expiry)),
    ]


def test_the_assigned_coordinator_is_told_when_the_expiry_changes(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    multi_venue_event.coordinator_id = OTHER_COORDINATOR_ID
    db_session.commit()
    new_expiry = expires_at + timedelta(days=1)

    change_expiry(held_request.id, new_expiry, db_session)

    assert _notices(NotificationKind.VENUE_HOLD_EXPIRY_CHANGED, db_session) == [
        (OTHER_COORDINATOR_ID, _in_business_time(new_expiry))
    ]


# --------------------------------------------------------------------------
# AC6 — an expired hold stays visible in the event's history, with its expiry
# --------------------------------------------------------------------------


def test_the_expiry_is_recorded_in_the_events_history_by_the_system(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    _expire(expires_at + timedelta(hours=1), db_session)

    history = list_event_history(
        COORDINATOR_ID,
        multi_venue_event.reference,
        viewer_role=Role.EVENT_COORDINATOR,
        session=db_session,
    )

    (entry,) = [entry for entry in history if entry.kind is EventHistoryKind.VENUE_HOLD_EXPIRED]
    assert entry.actor_name is None
    assert entry.details == {
        "venue_booking_request_id": held_request.id,
        "venue_id": held_request.venue_id,
        "booking_id": held_request.booking_id,
        "expires_at": expires_at.isoformat(),
    }


def test_the_expired_request_still_shows_its_expiry_on_the_event(
    db_session: Session,
    multi_venue_event: EventRequest,
    held_request: VenueBookingRequest,
    expires_at: datetime,
) -> None:
    _expire(expires_at, db_session)

    shown = services.list_booking_requests_for_event(
        multi_venue_event.reference, coordinator_id=COORDINATOR_ID, session=db_session
    )

    assert [(entry.request.status, entry.hold_expires_at) for entry in shown] == [
        (BookingRequestStatus.EXPIRED, expires_at),
        (BookingRequestStatus.PENDING, None),
    ]
