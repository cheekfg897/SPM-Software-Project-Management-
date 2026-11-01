"""Unit tests for SCRUM-61, an Event Organiser cancelling their event.

AC1: an event from Submitted to Confirmed is cancelled by its Event Organiser with a
reason, straight away, and the assigned coordinator is notified. AC2 and AC6: every
venue booking and tentative hold is released. AC3: reserved equipment returns to the
available quantity. AC7: open equipment requests close and leave Technical Support's
list. AC8: Venue Staff are told of each booking or hold released, naming the event, the
venue and the period. Any organiser of the event's client organisation may cancel it, as
any of them may answer a clarification (ADR-0029, ADR-0122). Registered Attendees are
told too (AC4), in ``test_cancel_event_attendees.py``.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7 of client organisation 3, assigned to Event Coordinator
3), so the release is real SQL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment import services as equipment_services
from app.modules.equipment.models import EquipmentType
from app.modules.events import services as events_services
from app.modules.events.models import (
    EventEquipmentLine,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import CANCELLATION_REASON_REQUIRED_MESSAGE
from app.modules.events.services import (
    EventCancellationNotAllowedError,
    OrganiserWithoutOrganisationError,
    cancel_event_request,
    list_equipment_requests_awaiting_action,
    record_equipment_outcome,
)
from app.modules.notifications.services import NotificationKind
from app.modules.venue import services as venue_services
from app.modules.venue.models import (
    Booking,
    BookingRequestStatus,
    BookingStatus,
    VenueBookingRequest,
)
from tests.events.cases import (
    HOLDING_ARRANGEMENT_STATUSES,
    LOST_CONNECTION,
    NOT_HOLDING_ARRANGEMENT_STATUSES,
    AddLine,
    Arrange,
    released_detail,
)
from tests.venue.conftest import locked_request_reads, reload_request, set_status_underneath

pytestmark = pytest.mark.scrum_61

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
SetStatus = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
#: ``other_organisers``: a colleague in organisation 3, one in organisation 4, and one
#: linked to no organisation yet.
COLLEAGUE_ID = 8
OTHER_ORGANISATION_ORGANISER_ID = 6
UNLINKED_ORGANISER_ID = 10
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
VENUE_STAFF_ID = 4
TECHNICAL_SUPPORT_ID = 5
REASON = "Our keynote speaker has withdrawn."
#: Where the Organiser may cancel (AC1), written out; the others come from the enum.
CANCELLABLE_STATUSES = [
    EventRequestStatus.SUBMITTED,
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.AWAITING_CLARIFICATION,
    EventRequestStatus.APPROVED,
    EventRequestStatus.SAFETY_REVIEW,
    EventRequestStatus.CONFIRMED,
]
#: Built from the enum so a status added later is refused too. A draft is among them:
#: the organiser who wrote it can open it, so it is refused, not hidden (ADR-0024).
NOT_CANCELLABLE_STATUSES = [
    status for status in EventRequestStatus if status not in CANCELLABLE_STATUSES
]
#: Where an event can have venue arrangements and reserved equipment: once approved.
ARRANGED_STATUSES = [
    EventRequestStatus.APPROVED,
    EventRequestStatus.SAFETY_REVIEW,
    EventRequestStatus.CONFIRMED,
]
#: The event's period, 15 October 2026 09:00 to 17:00 in business time, in UTC.
EVENT_STARTS_AT = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
EVENT_ENDS_AT = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(params=CANCELLABLE_STATUSES, ids=lambda status: status.value)
def cancellable(
    request: pytest.FixtureRequest,
    saved_users: list[User],
    saved_event_request: EventRequest,
    set_status: SetStatus,
) -> EventRequest:
    """``saved_event_request`` in each status it may be cancelled from, users saved."""
    set_status(request.param)
    return saved_event_request


@pytest.fixture(params=ARRANGED_STATUSES, ids=lambda status: status.value)
def arranged(
    request: pytest.FixtureRequest,
    saved_users: list[User],
    saved_event_request: EventRequest,
    set_status: SetStatus,
) -> EventRequest:
    """``saved_event_request`` in each status that can have arrangements."""
    set_status(request.param)
    return saved_event_request


@pytest.fixture()
def confirmed(
    saved_users: list[User], saved_event_request: EventRequest, set_status: SetStatus
) -> EventRequest:
    """``saved_event_request`` confirmed, with the users saved."""
    set_status(EventRequestStatus.CONFIRMED)
    return saved_event_request


def _cancel(
    session: Session, payload: Any = None, organiser_id: int = ORGANISER_ID
) -> EventRequest:
    if payload is None:
        payload = {"reason": REASON}
    return cancel_event_request(organiser_id, REFERENCE, payload, session=session)


def _status_of(session: Session, arrangement: VenueBookingRequest) -> BookingRequestStatus:
    return reload_request(session, arrangement.id).status


def _booking_for(arrangement: VenueBookingRequest) -> Booking:
    """The confirmed booking that approving ``arrangement`` made."""
    return Booking(
        venue_id=arrangement.venue_id,
        event_id=arrangement.event_id,
        start_time=arrangement.starts_at,
        end_time=arrangement.ends_at,
        status=BookingStatus.CONFIRMED,
    )


def _free_units(equipment_type: EquipmentType, session: Session) -> int:
    """How many units of the type are free for the event's period."""
    return equipment_services.available_quantity(
        equipment_type.id, EVENT_STARTS_AT, EVENT_ENDS_AT, session=session
    )


def _notices_of_kind(
    detailed_notifications_of: NotificationsOf, user_id: int, kind: NotificationKind
) -> list[tuple[str, str | None]]:
    """The user's notices of one kind as (reference, detail), newest first."""
    rows = []
    for reference, notice_kind, detail in detailed_notifications_of(user_id):
        if notice_kind is kind:
            rows.append((reference, detail))
    return rows


def _assert_nothing_changed(
    event_request: EventRequest,
    status: EventRequestStatus,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
) -> None:
    assert reload_event_request(event_request.id).status is status
    assert history_of(event_request.id) == []
    assert notifications_of(COORDINATOR_ID) == []


# --------------------------------------------------------------------------
# AC1 — the Organiser cancels with a reason, straight away
# --------------------------------------------------------------------------


def test_an_event_from_submitted_to_confirmed_is_cancelled_straight_away(
    db_session: Session, cancellable: EventRequest, reload_event_request: ReloadEventRequest
) -> None:
    cancelled = _cancel(db_session)

    assert cancelled.status is EventRequestStatus.CANCELLED
    assert reload_event_request(cancellable.id).status is EventRequestStatus.CANCELLED


def test_the_cancellation_is_recorded_with_who_and_why(
    db_session: Session, confirmed: EventRequest, history_of: HistoryOf
) -> None:
    _cancel(db_session, {"reason": f"  {REASON}  "})

    assert history_of(confirmed.id) == [
        (EventHistoryKind.EVENT_CANCELLED, ORGANISER_ID, {"reason": REASON})
    ]


def test_a_colleague_in_the_same_organisation_may_cancel_it(
    db_session: Session,
    confirmed: EventRequest,
    other_organisers: list[User],
    history_of: HistoryOf,
) -> None:
    """Any organiser of the client organisation, as for a clarification (ADR-0029)."""
    cancelled = _cancel(db_session, organiser_id=COLLEAGUE_ID)

    assert cancelled.status is EventRequestStatus.CANCELLED
    [(_kind, actor_id, _details)] = history_of(confirmed.id)
    assert actor_id == COLLEAGUE_ID


def test_the_assigned_coordinator_is_told_with_the_reason(
    db_session: Session, cancellable: EventRequest, detailed_notifications_of: NotificationsOf
) -> None:
    _cancel(db_session)

    assert detailed_notifications_of(COORDINATOR_ID) == [
        (REFERENCE, NotificationKind.EVENT_CANCELLED, REASON)
    ]


def test_nobody_else_is_told_of_an_event_with_nothing_arranged(
    db_session: Session,
    confirmed: EventRequest,
    make_user: Callable[..., User],
    save: Callable[..., None],
    notifications_of: NotificationsOf,
) -> None:
    """One user of every role, from the enum, so a role added later is checked.

    The organiser did it themselves, and with nothing booked Venue Staff have nothing
    to hear about. Safety Officers and Technical Support are not told (ADR-0122).
    """
    others = []
    for offset, role in enumerate(Role):
        others.append(make_user(email=f"{role.value}@example.com", role=role, user_id=100 + offset))
    save(*others)

    _cancel(db_session)

    assert notifications_of(COORDINATOR_ID) != []
    assert notifications_of(ORGANISER_ID) == []
    for user in others:
        assert notifications_of(user.id) == [], user.role


def test_with_no_coordinator_assigned_nobody_is_told_and_that_is_logged(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A submitted request waits in the Lead's queue with no coordinator (SCRUM-95)."""
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _cancel(db_session)

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.CANCELLED
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_unassigned reference={REFERENCE}"
    ]


def test_a_lost_notification_does_not_lose_the_cancellation(
    db_session: Session,
    confirmed: EventRequest,
    reload_event_request: ReloadEventRequest,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0015: the cancellation is committed before anyone is told."""

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(events_services, "notify_users", _fail)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        _cancel(db_session)

    assert reload_event_request(confirmed.id).status is EventRequestStatus.CANCELLED
    assert (
        f"event_request_notification_failed reference={REFERENCE} kind=event_cancelled"
        in caplog.text
    )


# --------------------------------------------------------------------------
# AC2, AC6 — venue bookings and tentative holds are released
# --------------------------------------------------------------------------


def test_its_venue_arrangements_are_released_or_withdrawn_by_the_organiser(
    db_session: Session,
    arranged: EventRequest,
    arrange: Arrange,
    save: Callable[..., None],
    history_of: HistoryOf,
) -> None:
    pending = arrange(BookingRequestStatus.PENDING)
    booked = arrange(BookingRequestStatus.APPROVED)
    booking = _booking_for(booked)
    save(booking)
    held = arrange(BookingRequestStatus.ON_HOLD)

    _cancel(db_session)

    assert _status_of(db_session, pending) is BookingRequestStatus.WITHDRAWN
    assert _status_of(db_session, booked) is BookingRequestStatus.RELEASED
    # The venue is free for that period again.
    assert db_session.get(Booking, booking.id).status is BookingStatus.CANCELLED
    assert _status_of(db_session, held) is BookingRequestStatus.RELEASED
    entries = [(kind, actor_id) for kind, actor_id, _details in history_of(arranged.id)]
    assert entries == [
        (EventHistoryKind.EVENT_CANCELLED, ORGANISER_ID),
        (EventHistoryKind.VENUE_ARRANGEMENT_WITHDRAWN, ORGANISER_ID),
    ]


# --------------------------------------------------------------------------
# AC2 — an arrangement Venue Staff decide while the event is being cancelled (ADR-0118)
# --------------------------------------------------------------------------
# Venue Staff decide an arrangement under its row lock (ADR-0045), so the cancellation
# reads each one under the lock too, and sees a decision saved while it was in flight.
# SQLite ignores ``FOR UPDATE``: the lock is shown by the statements sent, and the race
# by a status written underneath the session's cached copy.


def test_each_arrangement_is_read_under_a_row_lock(
    db_session: Session, confirmed: EventRequest, arrange: Arrange
) -> None:
    arrange(BookingRequestStatus.PENDING)
    arrange(BookingRequestStatus.APPROVED)

    reads = locked_request_reads(db_session, lambda: _cancel(db_session))

    assert len(reads) == 2


def test_an_approval_saved_meanwhile_is_released_and_its_booking_cancelled(
    db_session: Session, confirmed: EventRequest, arrange: Arrange, save: Callable[..., None]
) -> None:
    """Without the locked read, the stale Pending copy is withdrawn instead.

    The booking the approval made would then stay, holding the hall for a cancelled
    event.
    """
    arrangement = arrange(BookingRequestStatus.PENDING)
    booking = _booking_for(arrangement)
    save(booking)
    set_status_underneath(arrangement, BookingRequestStatus.APPROVED, db_session)

    _cancel(db_session)

    assert _status_of(db_session, arrangement) is BookingRequestStatus.RELEASED
    assert db_session.get(Booking, booking.id).status is BookingStatus.CANCELLED


def test_an_arrangement_withdrawn_after_it_was_listed_is_left_as_it_is(
    db_session: Session,
    confirmed: EventRequest,
    arrange: Arrange,
    history_of: HistoryOf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The coordinator's withdrawal commits between the listing and the locked read.

    So there is nothing left to release, and withdrawing it again would be refused.
    """
    arrangement = arrange(BookingRequestStatus.PENDING)
    list_active = venue_services.list_active_arrangements

    def _withdrawn_once_listed(event_id: int, **kwargs: Any) -> list[VenueBookingRequest]:
        listed = list_active(event_id, **kwargs)
        set_status_underneath(arrangement, BookingRequestStatus.WITHDRAWN, db_session)
        return listed

    monkeypatch.setattr(venue_services, "list_active_arrangements", _withdrawn_once_listed)

    _cancel(db_session)

    assert _status_of(db_session, arrangement) is BookingRequestStatus.WITHDRAWN
    entries = [kind for kind, _actor_id, _details in history_of(confirmed.id)]
    assert entries == [EventHistoryKind.EVENT_CANCELLED]


# --------------------------------------------------------------------------
# AC3 — reserved equipment returns to the available quantity
# --------------------------------------------------------------------------


def test_its_reserved_equipment_returns_to_the_available_quantity(
    db_session: Session,
    equipment_type: EquipmentType,
    three_projectors: EventEquipmentLine,
    saved_event_request: EventRequest,
    set_status: SetStatus,
) -> None:
    """Three of the type's ten units were reserved for it (``three_projectors``)."""
    set_status(EventRequestStatus.CONFIRMED)
    assert _free_units(equipment_type, db_session) == 7

    _cancel(db_session)

    assert _free_units(equipment_type, db_session) == 10


# --------------------------------------------------------------------------
# AC7 — open equipment requests close and leave Technical Support's list
# --------------------------------------------------------------------------


def test_its_open_equipment_requests_are_closed(
    db_session: Session, arranged: EventRequest, add_line: AddLine
) -> None:
    """Off Technical Support's list (SCRUM-38), and no outcome can be recorded."""
    waiting = add_line(None)
    today = arranged.proposed_date
    assert len(list_equipment_requests_awaiting_action(session=db_session, today=today)) == 1

    _cancel(db_session)

    assert list_equipment_requests_awaiting_action(session=db_session, today=today) == []
    with pytest.raises(ConflictError) as exc_info:
        record_equipment_outcome(
            TECHNICAL_SUPPORT_ID,
            REFERENCE,
            waiting.id,
            {"provided_quantity": 2},
            session=db_session,
        )
    # SCRUM-48 AC8's refusal, naming the status the cancellation set.
    assert exc_info.value.message.endswith("; this one is cancelled.")


# --------------------------------------------------------------------------
# AC8 — Venue Staff are told of each booking or hold released
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", HOLDING_ARRANGEMENT_STATUSES, ids=lambda status: status.value)
def test_every_venue_staff_user_is_told_of_each_booking_or_hold_released(
    db_session: Session,
    arranged: EventRequest,
    arrange: Arrange,
    second_venue_staff: User,
    detailed_notifications_of: NotificationsOf,
    status: BookingRequestStatus,
) -> None:
    held = arrange(status)

    _cancel(db_session)

    told = [(REFERENCE, released_detail(held))]
    kind = NotificationKind.VENUE_BOOKING_RELEASED_BY_CANCELLATION
    assert _notices_of_kind(detailed_notifications_of, VENUE_STAFF_ID, kind) == told
    assert _notices_of_kind(detailed_notifications_of, second_venue_staff.id, kind) == told
    # The rejection's notice, which says the event was rejected, is not sent.
    rejection_kind = NotificationKind.VENUE_BOOKING_RELEASED
    assert _notices_of_kind(detailed_notifications_of, VENUE_STAFF_ID, rejection_kind) == []


def test_each_released_arrangement_is_its_own_notice_to_every_venue_staff_user(
    db_session: Session,
    confirmed: EventRequest,
    arrange: Arrange,
    second_venue_staff: User,
    detailed_notifications_of: NotificationsOf,
) -> None:
    first = arrange(BookingRequestStatus.APPROVED)
    second = arrange(BookingRequestStatus.ON_HOLD)

    _cancel(db_session)

    # Newest first: the second arrangement's notice was sent last.
    told = [
        (REFERENCE, released_detail(second, starting_hour=18)),
        (REFERENCE, released_detail(first)),
    ]
    kind = NotificationKind.VENUE_BOOKING_RELEASED_BY_CANCELLATION
    assert _notices_of_kind(detailed_notifications_of, VENUE_STAFF_ID, kind) == told
    assert _notices_of_kind(detailed_notifications_of, second_venue_staff.id, kind) == told


@pytest.mark.parametrize(
    "status", NOT_HOLDING_ARRANGEMENT_STATUSES, ids=lambda status: status.value
)
def test_an_arrangement_that_did_not_hold_its_venue_is_not_told_about(
    db_session: Session,
    confirmed: EventRequest,
    arrange: Arrange,
    notifications_of: NotificationsOf,
    status: BookingRequestStatus,
) -> None:
    """A withdrawn one never had a booking; a retired one was released already."""
    arrange(status)

    _cancel(db_session)

    assert notifications_of(VENUE_STAFF_ID) == []


def test_a_lost_venue_staff_notice_does_not_lose_the_cancellation_or_the_release(
    db_session: Session,
    confirmed: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    detailed_notifications_of: NotificationsOf,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0015: the cancellation commits, then the coordinator and Venue Staff hear."""
    booked = arrange(BookingRequestStatus.APPROVED)

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(venue_services, "notify_users", _fail)

    with caplog.at_level(logging.WARNING, logger="connectsphere.venue"):
        _cancel(db_session)

    assert reload_event_request(confirmed.id).status is EventRequestStatus.CANCELLED
    assert _status_of(db_session, booked) is BookingRequestStatus.RELEASED
    assert detailed_notifications_of(COORDINATOR_ID) == [
        (REFERENCE, NotificationKind.EVENT_CANCELLED, REASON)
    ]
    assert f"venue_booking_notification_failed reference={REFERENCE}" in caplog.text


# --------------------------------------------------------------------------
# One commit: the cancellation and the release, or neither
# --------------------------------------------------------------------------


def test_the_cancellation_and_the_release_are_saved_together_or_not_at_all(
    db_session: Session,
    confirmed: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If returning the equipment fails, the venues and the status stay."""
    pending = arrange(BookingRequestStatus.PENDING)

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(equipment_services, "release_event_reservations", _fail)

    with pytest.raises(type(LOST_CONNECTION)):
        _cancel(db_session)
    db_session.rollback()

    assert _status_of(db_session, pending) is BookingRequestStatus.PENDING
    _assert_nothing_changed(
        confirmed, EventRequestStatus.CONFIRMED, reload_event_request, history_of, notifications_of
    )


# --------------------------------------------------------------------------
# Refusals: no reason, not cancellable, not the organisation's
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, CANCELLATION_REASON_REQUIRED_MESSAGE),
        ({"reason": None}, CANCELLATION_REASON_REQUIRED_MESSAGE),
        ({"reason": ""}, "Must not be blank."),
        ({"reason": "   "}, "Must not be blank."),
        ({"reason": 5}, "Not a valid string."),
        ({"reason": [REASON]}, "Not a valid string."),
    ],
    ids=["missing", "null", "empty", "whitespace", "number", "list"],
)
def test_a_cancellation_without_a_reason_is_refused(
    db_session: Session,
    confirmed: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    payload: dict[str, Any],
    message: str,
) -> None:
    booked = arrange(BookingRequestStatus.APPROVED)

    with pytest.raises(ValidationError) as exc_info:
        _cancel(db_session, payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"reason": [message]}
    assert _status_of(db_session, booked) is BookingRequestStatus.APPROVED
    _assert_nothing_changed(
        confirmed, EventRequestStatus.CONFIRMED, reload_event_request, history_of, notifications_of
    )


def test_the_missing_reason_message_says_what_is_needed() -> None:
    assert CANCELLATION_REASON_REQUIRED_MESSAGE == "A reason is required to cancel the event."


def test_a_field_it_does_not_know_is_refused(db_session: Session, confirmed: EventRequest) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _cancel(db_session, {"reason": REASON, "status": "cancelled"})

    assert exc_info.value.details == {"status": ["Unknown field."]}


@pytest.mark.parametrize("status", NOT_CANCELLABLE_STATUSES, ids=lambda status: status.value)
def test_only_an_event_from_submitted_to_confirmed_can_be_cancelled(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    set_status: SetStatus,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    status: EventRequestStatus,
) -> None:
    """A Completed or Rejected event is over; a Cancelled one can't be cancelled twice.

    The refusal names the status.
    """
    set_status(status)

    with pytest.raises(EventCancellationNotAllowedError) as exc_info:
        _cancel(db_session)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "cancellation_not_allowed")
    assert refused.message == (
        "Only an event between Submitted and Confirmed can be cancelled;"
        f" this one is {status.value}."
    )
    _assert_nothing_changed(
        saved_event_request, status, reload_event_request, history_of, notifications_of
    )


def test_the_status_is_checked_before_the_reason(
    db_session: Session, saved_users: list[User], set_status: SetStatus
) -> None:
    """The event, then its status, then the body, as rejecting during planning does."""
    set_status(EventRequestStatus.COMPLETED)

    with pytest.raises(EventCancellationNotAllowedError):
        _cancel(db_session, {})


def test_an_organiser_of_another_organisation_gets_not_found(
    db_session: Session,
    confirmed: EventRequest,
    other_organisers: list[User],
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
) -> None:
    """The same 404 as a reference that doesn't exist (SCRUM-7 AC2, ADR-0012)."""
    with pytest.raises(NotFoundError):
        _cancel(db_session, organiser_id=OTHER_ORGANISATION_ORGANISER_ID)

    _assert_nothing_changed(
        confirmed, EventRequestStatus.CONFIRMED, reload_event_request, history_of, notifications_of
    )


def test_an_organiser_with_no_organisation_is_refused(
    db_session: Session, confirmed: EventRequest, other_organisers: list[User]
) -> None:
    with pytest.raises(OrganiserWithoutOrganisationError) as exc_info:
        _cancel(db_session, organiser_id=UNLINKED_ORGANISER_ID)

    assert exc_info.value.status_code == 403
