"""Unit tests for SCRUM-49 AC9 and AC10, rejecting an event during planning.

AC9: when an essential arrangement can't be fulfilled, the assigned coordinator may
reject the event with a reason, and its status becomes Rejected. It is always a manual
decision, and the organiser is notified. AC10: its venue bookings and holds are
released, its reserved equipment returns to the available quantity and its open
equipment requests are closed, as for a cancelled event (SCRUM-61). Planning is
Approved or Safety Review (ADR-0047); the rejection is recorded as a decision, so it is
the event's current decision with its reason and coordinator (SCRUM-31, ADR-0093).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7, assigned to Event Coordinator 3), so the release is
real SQL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment import services as equipment_services
from app.modules.equipment.models import EquipmentReservation
from app.modules.events import services as events_services
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.schemas import PLANNING_REJECTION_REASON_REQUIRED_MESSAGE
from app.modules.events.services import (
    NOT_IN_PLANNING_FOR_REJECTION_MESSAGE,
    EventRejectionNotAllowedError,
    get_event_record_for_organiser,
    list_equipment_requests_awaiting_action,
    record_equipment_outcome,
    reject_event_during_planning,
)
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationSchema
from app.modules.notifications.services import NotificationKind, list_notifications_for_recipient
from app.modules.venue import services as venue_services
from app.modules.venue.models import BookingRequestStatus, VenueBookingRequest
from tests.events.cases import LOST_CONNECTION, AddLine, Arrange

pytestmark = pytest.mark.scrum_49

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
ORGANISER_ID = 7
TECHNICAL_SUPPORT_ID = 5
VENUE_STAFF_ID = 4
#: Everyone in ``saved_users`` but the organiser.
NON_ORGANISER_IDS = [9, 3, 4, 5, 2]
REASON = "No venue large enough is free that week."
PLANNING_STATUSES = [EventRequestStatus.APPROVED, EventRequestStatus.SAFETY_REVIEW]
#: The arrangements that hold their venue, so a rejection releases them and Venue Staff
#: are told (ADR-0093, ADR-0103). Written out; the other statuses come from the enum.
HOLDING_STATUSES = [BookingRequestStatus.APPROVED, BookingRequestStatus.ON_HOLD]
NOT_HOLDING_STATUSES = [status for status in BookingRequestStatus if status not in HOLDING_STATUSES]
#: Every status but planning, built from the enum so a status added later is refused
#: too. A draft is left out: staff get a 404 for it, not a 409 (ADR-0024).
NOT_IN_PLANNING = [
    status
    for status in EventRequestStatus
    if status not in PLANNING_STATUSES and status is not EventRequestStatus.DRAFT
]


@pytest.fixture(params=PLANNING_STATUSES, ids=lambda status: status.value)
def in_planning(
    request: pytest.FixtureRequest,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> EventRequest:
    """``saved_event_request`` in each planning status in turn, with the users saved."""
    saved_event_request.status = request.param
    save(saved_event_request)
    return saved_event_request


@pytest.fixture()
def approved(
    saved_users: list[User], saved_event_request: EventRequest, save: Callable[..., None]
) -> EventRequest:
    """``saved_event_request`` approved, with the users saved."""
    saved_event_request.status = EventRequestStatus.APPROVED
    save(saved_event_request)
    return saved_event_request


def _reject(
    session: Session,
    payload: Any = None,
    coordinator_id: int = COORDINATOR_ID,
) -> EventRequest:
    if payload is None:
        payload = {"reason": REASON}
    return reject_event_during_planning(coordinator_id, REFERENCE, payload, session=session)


def _reserve(
    event_request: EventRequest, equipment_type_id: int, save: Callable[..., None]
) -> None:
    """Hold three units of the type for the event's period, as Technical Support do."""
    save(
        EquipmentReservation(
            event_id=event_request.id,
            equipment_type_id=equipment_type_id,
            quantity=3,
            starts_at=datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc),
            reserved_by=TECHNICAL_SUPPORT_ID,
        )
    )


def _reservations_of(session: Session, event_request: EventRequest) -> list[EquipmentReservation]:
    session.expire_all()
    query = select(EquipmentReservation).where(EquipmentReservation.event_id == event_request.id)
    return list(session.scalars(query))


def _status_of(session: Session, arrangement: VenueBookingRequest) -> BookingRequestStatus:
    session.expire_all()
    reloaded = session.get(VenueBookingRequest, arrangement.id)
    assert reloaded is not None
    return reloaded.status


def _assert_nothing_changed(
    event_request: EventRequest,
    status: EventRequestStatus,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
) -> None:
    assert reload_event_request(event_request.id).status is status
    assert history_of(event_request.id) == []
    assert notifications_of(ORGANISER_ID) == []


# --------------------------------------------------------------------------
# AC9 — the coordinator rejects an event in planning, with a reason
# --------------------------------------------------------------------------


def test_an_event_in_planning_is_rejected(
    db_session: Session, in_planning: EventRequest, reload_event_request: ReloadEventRequest
) -> None:
    rejected = _reject(db_session)

    assert rejected.status is EventRequestStatus.REJECTED
    assert reload_event_request(in_planning.id).status is EventRequestStatus.REJECTED


def test_the_rejection_is_recorded_as_a_decision_with_who_and_why(
    db_session: Session, approved: EventRequest, history_of: HistoryOf
) -> None:
    """AC9, SCRUM-31 AC8: the history keeps the coordinator, the time and the reason."""
    _reject(db_session, {"reason": f"  {REASON}  "})

    assert history_of(approved.id) == [
        (
            EventHistoryKind.DECISION_RECORDED,
            COORDINATOR_ID,
            {"outcome": "rejected", "reason": REASON, "during_planning": True},
        )
    ]


def test_the_organiser_sees_the_rejection_as_the_current_decision(
    db_session: Session, approved: EventRequest
) -> None:
    """SCRUM-31 AC9: the current decision, its reason and who made it."""
    _reject(db_session)

    decision = get_event_record_for_organiser(ORGANISER_ID, REFERENCE, session=db_session).decision

    assert decision is not None
    assert (decision.outcome, decision.reason, decision.decided_by) == (
        "rejected",
        REASON,
        "Coordinator Three",
    )


def test_the_organiser_is_notified_once_with_the_reason_and_nobody_else(
    db_session: Session,
    approved: EventRequest,
    detailed_notifications_of: NotificationsOf,
) -> None:
    _reject(db_session)

    assert detailed_notifications_of(ORGANISER_ID) == [
        (REFERENCE, NotificationKind.EVENT_REQUEST_REJECTED, REASON)
    ]
    for user_id in NON_ORGANISER_IDS:
        assert detailed_notifications_of(user_id) == []


def test_a_lost_notification_does_not_lose_the_rejection(
    db_session: Session,
    approved: EventRequest,
    reload_event_request: ReloadEventRequest,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0015: the rejection is committed before the organiser is told."""

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(events_services, "notify_users", _fail)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _reject(db_session)

    assert reload_event_request(approved.id).status is EventRequestStatus.REJECTED
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference={REFERENCE} kind=event_request_rejected"
    ]


# --------------------------------------------------------------------------
# ADR-0103 — Venue Staff are told of each booking or hold the rejection released
# --------------------------------------------------------------------------


def _released_detail(arrangement: VenueBookingRequest) -> str:
    """What Venue Staff are told about the first arrangement ``arrange`` saves.

    It is at ``venue``'s Main Hall, from 17:00 to 17:30 on 1 November 2026 in business
    time; each later one starts an hour after the last.
    """
    return (
        f"Venue arrangement {arrangement.id} at Main Hall, 2026-11-01 17:00 to"
        " 2026-11-01 17:30, was released."
    )


def _released_notifications(user_id: int) -> list[Notification]:
    """The user's "booking released" notifications, newest first."""
    notices = []
    for notification in list_notifications_for_recipient(user_id):
        if notification.kind is NotificationKind.VENUE_BOOKING_RELEASED:
            notices.append(notification)
    return notices


def _released_notices(user_id: int) -> list[tuple[str, str | None]]:
    """The user's "booking released" notices as (reference, detail), newest first."""
    rows = []
    for notification in _released_notifications(user_id):
        rows.append((notification.event_reference, notification.detail))
    return rows


@pytest.fixture()
def second_venue_staff(make_user: Callable[..., User], save: Callable[..., None]) -> User:
    """Another Venue Staff user: every one of them is told (ADR-0103)."""
    user = make_user(email="venue8@example.com", role=Role.VENUE_STAFF, user_id=8)
    save(user)
    return user


@pytest.mark.parametrize("status", HOLDING_STATUSES, ids=lambda status: status.value)
def test_every_venue_staff_user_is_told_of_each_booking_or_hold_released(
    db_session: Session,
    in_planning: EventRequest,
    arrange: Arrange,
    second_venue_staff: User,
    status: BookingRequestStatus,
) -> None:
    held = arrange(status)

    _reject(db_session)

    told = [(REFERENCE, _released_detail(held))]
    assert _released_notices(VENUE_STAFF_ID) == told
    assert _released_notices(second_venue_staff.id) == told


def test_each_released_arrangement_is_its_own_notice(
    db_session: Session, approved: EventRequest, arrange: Arrange
) -> None:
    first = arrange(BookingRequestStatus.APPROVED)
    second = arrange(BookingRequestStatus.ON_HOLD)

    _reject(db_session)

    # Newest first: the second arrangement's notice was sent last.
    assert [detail for _, detail in _released_notices(VENUE_STAFF_ID)] == [
        f"Venue arrangement {second.id} at Main Hall, 2026-11-01 18:00 to"
        " 2026-11-01 18:30, was released.",
        _released_detail(first),
    ]


@pytest.mark.parametrize("status", NOT_HOLDING_STATUSES, ids=lambda status: status.value)
def test_an_arrangement_that_did_not_hold_its_venue_is_not_told_about(
    db_session: Session, approved: EventRequest, arrange: Arrange, status: BookingRequestStatus
) -> None:
    """A withdrawn one never had a booking; a retired one was released already."""
    arrange(status)

    _reject(db_session)

    assert _released_notices(VENUE_STAFF_ID) == []


def test_nobody_but_venue_staff_is_told_of_the_release(
    db_session: Session,
    approved: EventRequest,
    arrange: Arrange,
    make_user: Callable[..., User],
    save: Callable[..., None],
) -> None:
    """One user of every other role, from the enum, so a role added later is checked."""
    others = []
    for offset, role in enumerate(Role):
        if role is not Role.VENUE_STAFF:
            others.append(
                make_user(email=f"{role.value}@example.com", role=role, user_id=100 + offset)
            )
    save(*others)
    arrange(BookingRequestStatus.APPROVED)

    _reject(db_session)

    assert _released_notices(VENUE_STAFF_ID) != []
    for user in others:
        assert _released_notices(user.id) == [], user.role


def test_the_release_notice_says_why_and_links_to_the_event(
    db_session: Session, approved: EventRequest, arrange: Arrange
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    _reject(db_session)

    [notice] = _released_notifications(VENUE_STAFF_ID)
    shown = NotificationSchema().dump(notice)
    assert shown["message"] == (
        "A venue booking or hold was released because its event was rejected during planning."
    )
    assert shown["link"] == f"/events/{REFERENCE}"


def test_a_lost_venue_staff_notice_does_not_lose_the_rejection_or_the_release(
    db_session: Session,
    approved: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    detailed_notifications_of: NotificationsOf,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0015: the rejection commits first, then the organiser and Venue Staff."""
    booked = arrange(BookingRequestStatus.APPROVED)

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(venue_services, "notify_users", _fail)

    with caplog.at_level(logging.WARNING, logger="connectsphere.venue"):
        _reject(db_session)

    assert reload_event_request(approved.id).status is EventRequestStatus.REJECTED
    assert _status_of(db_session, booked) is BookingRequestStatus.RELEASED
    assert detailed_notifications_of(ORGANISER_ID) == [
        (REFERENCE, NotificationKind.EVENT_REQUEST_REJECTED, REASON)
    ]
    assert f"venue_booking_notification_failed reference={REFERENCE}" in caplog.text


# --------------------------------------------------------------------------
# AC10 — venues, holds and equipment are released
# --------------------------------------------------------------------------


def test_its_venue_arrangements_are_released(
    db_session: Session, in_planning: EventRequest, arrange: Arrange, history_of: HistoryOf
) -> None:
    pending = arrange(BookingRequestStatus.PENDING)
    booked = arrange(BookingRequestStatus.APPROVED)

    _reject(db_session)

    assert _status_of(db_session, pending) is BookingRequestStatus.WITHDRAWN
    assert _status_of(db_session, booked) is BookingRequestStatus.RELEASED
    kinds = [kind for kind, _actor, _details in history_of(in_planning.id)]
    assert kinds == [
        EventHistoryKind.DECISION_RECORDED,
        EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN,
    ]


def test_its_reserved_equipment_returns_to_stock(
    db_session: Session,
    in_planning: EventRequest,
    add_line: AddLine,
    save: Callable[..., None],
) -> None:
    line = add_line(2)
    _reserve(in_planning, line.equipment_type_id, save)
    starts_at = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
    ends_at = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    before = equipment_services.available_quantity(
        line.equipment_type_id, starts_at, ends_at, session=db_session
    )

    _reject(db_session)

    assert _reservations_of(db_session, in_planning) == []
    after = equipment_services.available_quantity(
        line.equipment_type_id, starts_at, ends_at, session=db_session
    )
    assert after == before + 3


def test_its_open_equipment_requests_are_closed(
    db_session: Session, approved: EventRequest, add_line: AddLine
) -> None:
    """SCRUM-61 AC9: off Technical Support's list, and no outcome can be recorded."""
    waiting = add_line(None)
    today = approved.proposed_date
    assert len(list_equipment_requests_awaiting_action(session=db_session, today=today)) == 1

    _reject(db_session)

    assert list_equipment_requests_awaiting_action(session=db_session, today=today) == []
    with pytest.raises(ConflictError) as exc_info:
        record_equipment_outcome(
            TECHNICAL_SUPPORT_ID,
            REFERENCE,
            waiting.id,
            {"provided_quantity": 2},
            session=db_session,
        )
    # SCRUM-48 AC8's refusal, naming the status the rejection set.
    assert exc_info.value.message.endswith("; this one is rejected.")


def test_the_rejection_and_the_release_are_saved_together_or_not_at_all(
    db_session: Session,
    approved: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One commit: if returning the equipment fails, the venues and status stay."""
    pending = arrange(BookingRequestStatus.PENDING)

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(equipment_services, "release_event_reservations", _fail)

    with pytest.raises(type(LOST_CONNECTION)):
        _reject(db_session)
    db_session.rollback()

    assert _status_of(db_session, pending) is BookingRequestStatus.PENDING
    _assert_nothing_changed(
        approved, EventRequestStatus.APPROVED, reload_event_request, history_of, notifications_of
    )


# --------------------------------------------------------------------------
# Refusals: no reason, not in planning, not the coordinator's
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, PLANNING_REJECTION_REASON_REQUIRED_MESSAGE),
        ({"reason": None}, PLANNING_REJECTION_REASON_REQUIRED_MESSAGE),
        ({"reason": ""}, "Must not be blank."),
        ({"reason": "   "}, "Must not be blank."),
        ({"reason": 5}, "Not a valid string."),
        ({"reason": True}, "Not a valid string."),
        ({"reason": [REASON]}, "Not a valid string."),
    ],
    ids=["missing", "null", "empty", "whitespace", "number", "boolean", "list"],
)
def test_a_rejection_without_a_reason_is_refused(
    db_session: Session,
    approved: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    payload: dict[str, Any],
    message: str,
) -> None:
    pending = arrange(BookingRequestStatus.PENDING)

    with pytest.raises(ValidationError) as exc_info:
        _reject(db_session, payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"reason": [message]}
    assert _status_of(db_session, pending) is BookingRequestStatus.PENDING
    _assert_nothing_changed(
        approved, EventRequestStatus.APPROVED, reload_event_request, history_of, notifications_of
    )


def test_a_field_it_does_not_know_is_refused(db_session: Session, approved: EventRequest) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _reject(db_session, {"reason": REASON, "status": "rejected"})

    assert exc_info.value.details == {"status": ["Unknown field."]}


@pytest.mark.parametrize("status", NOT_IN_PLANNING, ids=lambda status: status.value)
def test_only_an_event_in_planning_can_be_rejected_this_way(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    status: EventRequestStatus,
) -> None:
    """A request awaiting its first decision is rejected through SCRUM-31's decision."""
    saved_event_request.status = status
    save(saved_event_request)

    with pytest.raises(EventRejectionNotAllowedError) as exc_info:
        _reject(db_session)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "rejection_not_allowed")
    assert refused.message == NOT_IN_PLANNING_FOR_REJECTION_MESSAGE
    _assert_nothing_changed(
        saved_event_request, status, reload_event_request, history_of, notifications_of
    )


def test_the_status_is_checked_before_the_reason(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> None:
    """As SCRUM-31's decision does: the event, then its status, then the body."""
    saved_event_request.status = EventRequestStatus.CONFIRMED
    save(saved_event_request)

    with pytest.raises(EventRejectionNotAllowedError):
        _reject(db_session, {})


def test_another_coordinator_gets_not_found_and_the_event_is_unchanged(
    db_session: Session,
    approved: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
) -> None:
    with pytest.raises(NotFoundError):
        _reject(db_session, coordinator_id=OTHER_COORDINATOR_ID)

    _assert_nothing_changed(
        approved, EventRequestStatus.APPROVED, reload_event_request, history_of, notifications_of
    )
