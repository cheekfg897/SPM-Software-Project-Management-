"""Unit tests for SCRUM-49 "Confirm an event once its arrangements are in place".

AC1: the assigned coordinator confirms an event in Safety Review once the Safety
Officer has approved it, every active venue arrangement is Approved and every equipment
request has an outcome. AC2: an event with no equipment requests passes the equipment
check. AC3: confirmation is a manual action; nothing confirms an event on its own. AC4,
AC5, AC8: a refusal names each gap (no venue, a Pending or Rejected arrangement, the
outstanding safety check); a Withdrawn arrangement is ignored. AC7: a tentative hold on
a venue is not a booking. AC12: the organiser is
notified. The confirmation is written to the event history, and a confirmed event with
registration on is open for registration (ADR-0051).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7, assigned to Event Coordinator 3), so the venue and
equipment checks are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    CONFIRMATION_NOT_READY_MESSAGE,
    NOT_IN_SAFETY_REVIEW_FOR_CONFIRMATION_MESSAGE,
    EventConfirmationNotAllowedError,
    confirm_event_request,
    list_registrable_events,
    record_event_history,
)
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import Booking, BookingRequestStatus, BookingStatus, Venue
from tests.events.cases import AddLine, Arrange

pytestmark = pytest.mark.scrum_49

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
CheckSafety = Callable[[str], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
ORGANISER_ID = 7
SAFETY_OFFICER_ID = 20
#: Everyone in ``saved_users`` but the organiser.
NON_ORGANISER_IDS = [9, 3, 4, 5, 2]
SENT_TO_SAFETY_REVIEW_AT = datetime(2026, 10, 12, 2, 0, tzinfo=timezone.utc)
NO_SAFETY_APPROVAL = {"safety_check": ["The Safety Officer has not approved the event."]}
NO_VENUE_ARRANGED = {"venue_arrangements": ["The event has no venue arranged."]}
#: Every status but Safety Review, built from the enum so a status added later is
#: refused too. A draft is left out: staff get a 404 for it, not a 409 (ADR-0024).
NOT_IN_SAFETY_REVIEW = [
    status
    for status in EventRequestStatus
    if status not in {EventRequestStatus.SAFETY_REVIEW, EventRequestStatus.DRAFT}
]


@pytest.fixture()
def in_review(
    saved_users: list[User], saved_event_request: EventRequest, save: Callable[..., None]
) -> EventRequest:
    """``saved_event_request`` in Safety Review, with the users saved."""
    saved_event_request.status = EventRequestStatus.SAFETY_REVIEW
    save(saved_event_request)
    return saved_event_request


@pytest.fixture()
def check_safety(db_session: Session, in_review: EventRequest) -> CheckSafety:
    """Send ``in_review`` to the Safety Officer, who rules with the outcome given.

    Written as the safety stories write it, so ``has_safety_approval`` reads it
    (ADR-0047).
    """

    def _check(outcome: str) -> None:
        record_event_history(
            in_review,
            EventHistoryKind.SAFETY_REVIEW_REQUESTED,
            actor_id=COORDINATOR_ID,
            session=db_session,
            now=SENT_TO_SAFETY_REVIEW_AT,
        )
        record_event_history(
            in_review,
            EventHistoryKind.SAFETY_OUTCOME_RECORDED,
            actor_id=SAFETY_OFFICER_ID,
            details={"outcome": outcome, "checklist": {}, "reason": None},
            session=db_session,
            now=SENT_TO_SAFETY_REVIEW_AT + timedelta(hours=1),
        )
        db_session.commit()

    return _check


@pytest.fixture()
def ready_event(
    in_review: EventRequest, check_safety: CheckSafety, arrange: Arrange
) -> EventRequest:
    """``in_review`` with the Safety Officer's approval and one Approved venue."""
    check_safety("approved")
    arrange(BookingRequestStatus.APPROVED)
    return in_review


def _confirm(session: Session, coordinator_id: int = COORDINATOR_ID) -> EventRequest:
    return confirm_event_request(coordinator_id, REFERENCE, session=session)


def _refusal(session: Session) -> EventConfirmationNotAllowedError:
    with pytest.raises(EventConfirmationNotAllowedError) as exc_info:
        _confirm(session)
    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "confirmation_not_allowed")
    return refused


def _assert_nothing_changed(
    event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
) -> None:
    assert reload_event_request(event_request.id).status is EventRequestStatus.SAFETY_REVIEW
    kinds = [kind for kind, _actor, _details in history_of(event_request.id)]
    assert EventHistoryKind.EVENT_CONFIRMED not in kinds
    assert notifications_of(ORGANISER_ID) == []


# --------------------------------------------------------------------------
# AC1, AC2, AC3 — everything in place, and the coordinator confirms
# --------------------------------------------------------------------------


def test_an_event_with_every_approval_in_place_is_confirmed(
    db_session: Session,
    ready_event: EventRequest,
    add_line: AddLine,
    reload_event_request: ReloadEventRequest,
) -> None:
    add_line(2)

    confirmed = _confirm(db_session)

    assert confirmed.status is EventRequestStatus.CONFIRMED
    assert reload_event_request(ready_event.id).status is EventRequestStatus.CONFIRMED


def test_an_event_with_no_equipment_requests_is_confirmed(
    db_session: Session, ready_event: EventRequest
) -> None:
    assert _confirm(db_session).status is EventRequestStatus.CONFIRMED


def test_a_withdrawn_arrangement_does_not_hold_the_event_back(
    db_session: Session, ready_event: EventRequest, arrange: Arrange
) -> None:
    arrange(BookingRequestStatus.WITHDRAWN)

    assert _confirm(db_session).status is EventRequestStatus.CONFIRMED


def test_the_confirmation_is_written_to_the_event_history(
    db_session: Session, ready_event: EventRequest, history_of: HistoryOf
) -> None:
    _confirm(db_session)

    assert history_of(ready_event.id)[-1] == (
        EventHistoryKind.EVENT_CONFIRMED,
        COORDINATOR_ID,
        None,
    )


# --------------------------------------------------------------------------
# AC12 — the organiser is told, and nobody else
# --------------------------------------------------------------------------


def test_the_organiser_is_notified_once_and_nobody_else(
    db_session: Session, ready_event: EventRequest, notifications_of: NotificationsOf
) -> None:
    _confirm(db_session)

    assert notifications_of(ORGANISER_ID) == [
        (ready_event.id, REFERENCE, "Partner Summit", NotificationKind.EVENT_CONFIRMED, None)
    ]
    for user_id in NON_ORGANISER_IDS:
        assert notifications_of(user_id) == []


# --------------------------------------------------------------------------
# SCRUM-52 — a confirmed event with registration on reaches the attendee catalogue
# --------------------------------------------------------------------------


def test_a_confirmed_event_with_registration_enabled_is_open_for_registration(
    db_session: Session, ready_event: EventRequest, save: Callable[..., None]
) -> None:
    ready_event.registration_enabled = True
    ready_event.registration_capacity = 100
    save(ready_event)
    before_the_event = datetime(2026, 10, 10, tzinfo=timezone.utc)
    assert list_registrable_events(session=db_session, now=before_the_event) == []

    _confirm(db_session)

    events = list_registrable_events(session=db_session, now=before_the_event)
    assert [event.reference for event in events] == [REFERENCE]


# --------------------------------------------------------------------------
# AC1, AC8 — the Safety Officer's approval is needed
# --------------------------------------------------------------------------


def test_an_event_still_waiting_for_the_safety_officer_is_refused(
    db_session: Session,
    in_review: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    refused = _refusal(db_session)

    assert refused.message == CONFIRMATION_NOT_READY_MESSAGE
    assert refused.details == NO_SAFETY_APPROVAL
    _assert_nothing_changed(in_review, reload_event_request, history_of, notifications_of)


def test_a_safety_outcome_that_is_not_an_approval_is_refused(
    db_session: Session, in_review: EventRequest, check_safety: CheckSafety, arrange: Arrange
) -> None:
    check_safety("changes_requested")
    arrange(BookingRequestStatus.APPROVED)

    assert _refusal(db_session).details == NO_SAFETY_APPROVAL


def test_an_approval_is_void_once_the_event_is_sent_to_safety_review_again(
    db_session: Session, ready_event: EventRequest
) -> None:
    record_event_history(
        ready_event,
        EventHistoryKind.SAFETY_REVIEW_REQUESTED,
        actor_id=COORDINATOR_ID,
        session=db_session,
        now=SENT_TO_SAFETY_REVIEW_AT + timedelta(days=1),
    )
    db_session.commit()

    assert _refusal(db_session).details == NO_SAFETY_APPROVAL


# --------------------------------------------------------------------------
# AC4, AC5 — every active venue arrangement must be Approved
# --------------------------------------------------------------------------


def test_an_event_with_no_venue_arranged_is_refused(
    db_session: Session, in_review: EventRequest, check_safety: CheckSafety
) -> None:
    check_safety("approved")

    assert _refusal(db_session).details == NO_VENUE_ARRANGED


def test_a_tentative_hold_on_a_venue_is_not_an_approved_booking(
    db_session: Session,
    in_review: EventRequest,
    check_safety: CheckSafety,
    venue: Venue,
    save: Callable[..., None],
) -> None:
    check_safety("approved")
    save(
        Booking(
            venue_id=venue.id,
            event_id=in_review.id,
            start_time=datetime(2026, 11, 1, 9, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 1, 12, tzinfo=timezone.utc),
            status=BookingStatus.TENTATIVE,
        )
    )

    assert _refusal(db_session).details == NO_VENUE_ARRANGED


@pytest.mark.parametrize("status", [BookingRequestStatus.PENDING, BookingRequestStatus.REJECTED])
def test_an_arrangement_that_is_not_approved_is_named_in_the_refusal(
    db_session: Session, ready_event: EventRequest, arrange: Arrange, status: BookingRequestStatus
) -> None:
    held_back = arrange(status)

    assert _refusal(db_session).details == {
        "venue_arrangements": [f"Venue arrangement {held_back.id} is {status.value}."]
    }


# --------------------------------------------------------------------------
# AC1 — every equipment request needs an outcome
# --------------------------------------------------------------------------


def test_an_equipment_request_without_an_outcome_is_named_in_the_refusal(
    db_session: Session, ready_event: EventRequest, add_line: AddLine
) -> None:
    add_line(2)
    waiting = add_line(None)

    assert _refusal(db_session).details == {
        "equipment": [f"Equipment request {waiting.id} has no outcome from Technical Support."]
    }


def test_every_gap_is_named_together(
    db_session: Session, in_review: EventRequest, add_line: AddLine
) -> None:
    waiting = add_line(None)

    assert _refusal(db_session).details == {
        **NO_SAFETY_APPROVAL,
        **NO_VENUE_ARRANGED,
        "equipment": [f"Equipment request {waiting.id} has no outcome from Technical Support."],
    }


# --------------------------------------------------------------------------
# The event must be in Safety Review, and the caller its coordinator
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NOT_IN_SAFETY_REVIEW, ids=lambda status: status.value)
def test_only_an_event_in_safety_review_can_be_confirmed(
    db_session: Session,
    ready_event: EventRequest,
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    status: EventRequestStatus,
) -> None:
    ready_event.status = status
    save(ready_event)

    refused = _refusal(db_session)

    assert refused.message == NOT_IN_SAFETY_REVIEW_FOR_CONFIRMATION_MESSAGE
    assert reload_event_request(ready_event.id).status is status


def test_another_coordinator_gets_not_found_and_the_event_is_unchanged(
    db_session: Session,
    ready_event: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
) -> None:
    with pytest.raises(NotFoundError):
        _confirm(db_session, coordinator_id=OTHER_COORDINATOR_ID)

    _assert_nothing_changed(ready_event, reload_event_request, history_of, notifications_of)
