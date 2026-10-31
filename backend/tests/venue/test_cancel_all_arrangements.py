"""Unit tests for SCRUM-93 AC6 and AC10 — cancel all of an event's arrangements.

Cancel-all retires every arrangement the event still has, in one transaction: one not
yet approved is withdrawn, as before, and an approved booking is cancelled, as SCRUM-111
cancels one (ADR-0118): the booking is released, the arrangement becomes Cancelled and
its history entry carries the coordinator's reason, which cancel-all requires. SCRUM-111
AC2's Safety Review rules apply once for the whole action, and Venue Staff, and for an
event in Safety Review the Safety Officers, are told of each booking cancelled. Runs
against ``db_session``, so the queries really run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events import services as event_services
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import has_safety_approval
from app.modules.notifications.models import Notification
from app.modules.notifications.services import (
    NotificationKind,
    list_notifications_for_recipient,
)
from app.modules.venue import services
from app.modules.venue.models import BookingRequestStatus, BookingStatus, Venue
from app.modules.venue.schemas import BookingRequestAsShown
from tests.venue.conftest import (
    COORDINATOR_ID,
    SECOND_PERIOD,
    VENUE_STAFF_ID,
    SavedEvent,
    approve_safety,
    approved_arrangement,
    bookings,
    history_entries,
    raise_booking,
    reload_event,
    reload_request,
)

pytestmark = pytest.mark.scrum_93

REASON = "The conference moved online."
SAFETY_OFFICER_ID = 21
#: What the notices say about each booking, in business time (ADR-0117).
MAIN_HALL_CANCELLED = (
    "Venue arrangement {id} at Main Hall, 2026-11-01 09:00 to 2026-11-01 12:00, was cancelled."
)
BREAKOUT_CANCELLED = (
    "Venue arrangement {id} at Breakout room, 2026-11-01 13:00 to 2026-11-01 16:00, was cancelled."
)
BACK_IN_PLANNING = " It is back in planning until it can be sent to Safety Review again."


def _cancel_all(
    event: EventRequest, session: Session, payload: dict[str, Any] | None = None
) -> list[BookingRequestAsShown]:
    body = {"reason": REASON} if payload is None else payload
    return services.cancel_all_arrangements(
        event.reference, body, coordinator_id=COORDINATOR_ID, session=session
    )


def _statuses(session: Session, *arrangement_ids: int) -> list[BookingRequestStatus]:
    return [reload_request(session, each).status for each in arrangement_ids]


def _notices(user_id: int) -> list[tuple[NotificationKind, str | None]]:
    """The user's notices as (kind, detail), sorted: ones sent together share a time."""
    rows = []
    for notice in list_notifications_for_recipient(user_id):
        rows.append((notice.kind, notice.detail))
    return sorted(rows)


def _forget_earlier_notices(session: Session) -> None:
    """Delete the notices raising and approving the bookings sent, before the act."""
    session.execute(delete(Notification))
    session.commit()


def _into(event: EventRequest, status: EventRequestStatus, session: Session) -> None:
    event.status = status
    session.commit()


@pytest.fixture()
def event(saved_event: SavedEvent) -> EventRequest:
    """An approved event of coordinator 3's."""
    return saved_event()


@pytest.fixture()
def second_venue(make_venue: Callable[..., Venue], save: Callable[..., None]) -> Venue:
    saved = make_venue(name="Breakout room")
    save(saved)
    return saved


@pytest.fixture()
def booked(db_session: Session, event: EventRequest, venue: Venue) -> int:
    """The event's approved arrangement at ``venue`` (Main Hall), 09:00-12:00."""
    return approved_arrangement(venue, event, db_session)


@pytest.fixture()
def pending(db_session: Session, event: EventRequest, second_venue: Venue) -> int:
    """A Pending arrangement of the event's at the second venue, 13:00-16:00."""
    return raise_booking(second_venue, event, db_session, **SECOND_PERIOD).id


@pytest.fixture()
def also_booked(db_session: Session, event: EventRequest, second_venue: Venue) -> int:
    """A second approved arrangement of the event's, 13:00-16:00."""
    return approved_arrangement(second_venue, event, db_session, **SECOND_PERIOD)


@pytest.fixture()
def safety_officer(db_session: Session, make_user: Callable[..., User]) -> User:
    officer = make_user(email="safety21@example.com", role=Role.SAFETY_OFFICER, user_id=21)
    db_session.add(officer)
    db_session.commit()
    return officer


# --------------------------------------------------------------------------
# An approved booking is cancelled; the rest are withdrawn, all in one go
# --------------------------------------------------------------------------


def test_an_approved_booking_is_cancelled_and_the_pending_one_withdrawn(
    db_session: Session, event: EventRequest, booked: int, pending: int
) -> None:
    retired = _cancel_all(event, db_session)

    assert [(shown.request.id, shown.request.status) for shown in retired] == [
        (booked, BookingRequestStatus.CANCELLED),
        (pending, BookingRequestStatus.WITHDRAWN),
    ]
    assert _statuses(db_session, booked, pending) == [
        BookingRequestStatus.CANCELLED,
        BookingRequestStatus.WITHDRAWN,
    ]
    assert [status for _, status in bookings(db_session)] == [BookingStatus.CANCELLED]
    assert services.count_active_arrangements(event.id, session=db_session) == 0


def test_the_cancelled_booking_has_its_reason_in_the_history_and_the_withdrawal_its_entry(
    db_session: Session, event: EventRequest, booked: int, pending: int
) -> None:
    _cancel_all(event, db_session, {"reason": f"  {REASON}  "})

    entries = history_entries(db_session, event.id)[-2:]
    assert [(entry.kind, entry.actor_id) for entry in entries] == [
        (EventHistoryKind.VENUE_BOOKING_CANCELLED, COORDINATOR_ID),
        (EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN, COORDINATOR_ID),
    ]
    assert entries[0].details["venue_booking_request_id"] == booked
    assert entries[0].details["reason"] == REASON
    assert entries[1].details == {
        "venue_booking_request_id": pending,
        "venue_id": reload_request(db_session, pending).venue_id,
    }


def test_nothing_is_saved_when_a_step_fails_part_way(
    db_session: Session,
    event: EventRequest,
    booked: int,
    pending: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One transaction: a withdrawal beside a failed cancellation is not kept."""

    def _fail(*_: object, **__: object) -> None:
        raise SQLAlchemyError("history table is gone")

    monkeypatch.setattr(event_services, "record_venue_booking_cancelled", _fail)

    with pytest.raises(SQLAlchemyError):
        _cancel_all(event, db_session)

    db_session.rollback()
    assert _statuses(db_session, booked, pending) == [
        BookingRequestStatus.APPROVED,
        BookingRequestStatus.PENDING,
    ]
    assert [status for _, status in bookings(db_session)] == [BookingStatus.CONFIRMED]


# --------------------------------------------------------------------------
# The reason is required, and is checked after the event's status
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "errors"),
    [
        pytest.param({}, {"reason": ["A reason is required to cancel a booking."]}, id="none"),
        pytest.param(
            {"reason": None}, {"reason": ["A reason is required to cancel a booking."]}, id="null"
        ),
        pytest.param({"reason": "   "}, {"reason": ["Must not be blank."]}, id="blank"),
        pytest.param({"reason": 7}, {"reason": ["Not a valid string."]}, id="number"),
        pytest.param(
            {"reason": REASON, "notify": True}, {"notify": ["Unknown field."]}, id="unknown"
        ),
    ],
)
def test_a_cancel_all_without_a_proper_reason_is_refused_and_changes_nothing(
    db_session: Session,
    event: EventRequest,
    booked: int,
    pending: int,
    payload: dict[str, Any],
    errors: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError) as refused:
        _cancel_all(event, db_session, payload)

    assert refused.value.details == errors
    assert _statuses(db_session, booked, pending) == [
        BookingRequestStatus.APPROVED,
        BookingRequestStatus.PENDING,
    ]


def test_the_events_status_is_checked_before_the_reason(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _into(event, EventRequestStatus.CONFIRMED, db_session)

    with pytest.raises(ConflictError) as refused:
        _cancel_all(event, db_session, {})

    assert refused.value.message.endswith("this one is confirmed.")


# --------------------------------------------------------------------------
# SCRUM-111 AC2 — Safety Review, once for the whole action
# --------------------------------------------------------------------------


def test_an_approved_event_stays_approved(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _cancel_all(event, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED


def test_in_safety_review_cancelling_every_venue_sends_the_event_back_to_approved(
    db_session: Session, event: EventRequest, booked: int, also_booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    _cancel_all(event, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    kinds = [entry.kind for entry in history_entries(db_session, event.id)]
    assert EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN not in kinds


def test_in_safety_review_a_pass_is_withdrawn_once_naming_the_first_booking(
    db_session: Session, event: EventRequest, booked: int, also_booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)
    approve_safety(event, db_session)

    _cancel_all(event, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED
    assert has_safety_approval(event.id, session=db_session) is False
    withdrawals = [
        entry
        for entry in history_entries(db_session, event.id)
        if entry.kind is EventHistoryKind.SAFETY_APPROVAL_WITHDRAWN
    ]
    assert [(entry.actor_id, entry.details) for entry in withdrawals] == [
        (COORDINATOR_ID, {"venue_booking_request_id": booked})
    ]


def test_in_safety_review_withdrawing_its_only_venue_request_sends_it_back_too(
    db_session: Session, event: EventRequest, pending: int
) -> None:
    """Cancel-all leaves no venue, and Safety Review needs one (SCRUM-97 AC3)."""
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)

    _cancel_all(event, db_session)

    assert reload_event(db_session, event.id).status is EventRequestStatus.APPROVED


# --------------------------------------------------------------------------
# SCRUM-111 AC2, AC3 — who is told, once per booking cancelled
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("saved_users")
def test_venue_staff_are_told_of_each_cancelled_booking_and_not_of_a_withdrawal(
    db_session: Session, event: EventRequest, booked: int, also_booked: int, pending: int
) -> None:
    _forget_earlier_notices(db_session)

    _cancel_all(event, db_session)

    assert _notices(VENUE_STAFF_ID) == sorted(
        [
            (NotificationKind.VENUE_BOOKING_CANCELLED, MAIN_HALL_CANCELLED.format(id=booked)),
            (NotificationKind.VENUE_BOOKING_CANCELLED, BREAKOUT_CANCELLED.format(id=also_booked)),
        ]
    )


@pytest.mark.usefixtures("saved_users", "safety_officer")
def test_in_safety_review_the_safety_officers_are_told_of_each_and_that_it_is_back(
    db_session: Session, event: EventRequest, booked: int, also_booked: int
) -> None:
    _into(event, EventRequestStatus.SAFETY_REVIEW, db_session)
    _forget_earlier_notices(db_session)

    _cancel_all(event, db_session)

    assert _notices(SAFETY_OFFICER_ID) == sorted(
        [
            (
                NotificationKind.SAFETY_REVIEW_VENUE_CANCELLED,
                MAIN_HALL_CANCELLED.format(id=booked) + BACK_IN_PLANNING,
            ),
            (
                NotificationKind.SAFETY_REVIEW_VENUE_CANCELLED,
                BREAKOUT_CANCELLED.format(id=also_booked) + BACK_IN_PLANNING,
            ),
        ]
    )


@pytest.mark.usefixtures("saved_users", "safety_officer")
def test_an_approved_events_cancel_all_tells_no_safety_officer(
    db_session: Session, event: EventRequest, booked: int
) -> None:
    _forget_earlier_notices(db_session)

    _cancel_all(event, db_session)

    assert _notices(SAFETY_OFFICER_ID) == []
