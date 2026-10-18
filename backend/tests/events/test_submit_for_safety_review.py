"""Unit tests for SCRUM-97 "Submit an event for operational safety check" (part A).

AC1: once every active venue arrangement is Approved and every equipment request has
an outcome from Technical Support, the assigned coordinator moves the approved event
to Safety Review. A Pending or Rejected arrangement holds it back; a Withdrawn one is
ignored. AC2: an event with no equipment requests passes the equipment check. An
event with no venue arranged at all is held back (ADR-0047). The move is written to
the event history; a refusal changes nothing. Once in Safety Review, the event can't
be edited nor its equipment changed (ADR-0047).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3), so the venue and equipment
checks are real SQL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import (
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EQUIPMENT_NOT_EDITABLE_MESSAGE,
    NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE,
    NOT_EDITABLE_MESSAGE,
    SAFETY_REVIEW_NOT_READY_MESSAGE,
    EquipmentNotEditableError,
    RequestNotEditableError,
    SafetyReviewNotAllowedError,
    add_equipment_line,
    submit_for_safety_review,
    update_event_request,
)
from app.modules.notifications.services import NotificationKind
from app.modules.venue.models import BookingRequestStatus
from tests.events.cases import AddLine, Arrange

pytestmark = pytest.mark.scrum_97

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
#: Saved out of order, so every Safety Officer has to be found (ADR-0047).
SAFETY_OFFICER_IDS = [21, 20]
#: Everyone in ``saved_users``: coordinators 9 and 3, Venue Staff 4, organiser 7 and
#: Technical Support 5 and 2.
OTHER_USER_IDS = [9, 3, 4, 7, 5, 2]

#: The retired statuses, which the gate ignores: Withdrawn (AC1) and Released, an
#: arrangement a replacement took over from (SCRUM-92 AC7).
RETIRED_ARRANGEMENT_STATUSES = [BookingRequestStatus.WITHDRAWN, BookingRequestStatus.RELEASED]
#: Every arrangement status but Approved and the retired ones, which let an event
#: through. Built from the enum, so a status added later is checked too.
HOLDING_ARRANGEMENT_STATUSES = [
    status
    for status in BookingRequestStatus
    if status is not BookingRequestStatus.APPROVED and status not in RETIRED_ARRANGEMENT_STATUSES
]
#: Every event status but approved, the one an event is sent from (ADR-0047). A draft
#: is left out: it has no coordinator, so it is a 404, not a 409 (ADR-0024).
NOT_APPROVED_STATUSES = [
    status
    for status in EventRequestStatus
    if status not in {EventRequestStatus.APPROVED, EventRequestStatus.DRAFT}
]


@pytest.fixture(autouse=True)
def approved_event(
    saved_users: list[User], saved_event_request: EventRequest, save: Callable[..., None]
) -> EventRequest:
    """``saved_event_request``, approved by its coordinator, with the users saved."""
    saved_event_request.status = EventRequestStatus.APPROVED
    save(saved_event_request)
    return saved_event_request


@pytest.fixture()
def safety_officers(make_user: Callable[..., User], save: Callable[..., None]) -> list[User]:
    """Save two Safety Officers, 21 before 20."""
    officers = [
        make_user(email=f"safety{user_id}@example.com", role=Role.SAFETY_OFFICER, user_id=user_id)
        for user_id in SAFETY_OFFICER_IDS
    ]
    save(*officers)
    return officers


def _submit(session: Session, coordinator_id: int = COORDINATOR_ID) -> EventRequest:
    return submit_for_safety_review(coordinator_id, REFERENCE, session=session)


def _refusal(session: Session) -> SafetyReviewNotAllowedError:
    with pytest.raises(SafetyReviewNotAllowedError) as exc_info:
        _submit(session)
    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "safety_review_not_allowed")
    return refused


def _assert_still_approved(
    approved_event: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    assert reload_event_request(approved_event.id).status is EventRequestStatus.APPROVED
    assert history_of(approved_event.id) == []


# --------------------------------------------------------------------------
# AC1 — every arrangement Approved and every outcome recorded moves it on
# --------------------------------------------------------------------------


def test_an_event_ready_on_both_counts_moves_to_safety_review(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    add_line: AddLine,
    reload_event_request: ReloadEventRequest,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    add_line(2)

    submitted = _submit(db_session)
    # Only what was committed survives a rollback; a flush alone would be undone.
    db_session.rollback()

    assert submitted.status is EventRequestStatus.SAFETY_REVIEW
    assert reload_event_request(approved_event.id).status is EventRequestStatus.SAFETY_REVIEW


def test_the_move_is_written_to_the_event_history(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    history_of: HistoryOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    _submit(db_session)
    db_session.rollback()

    assert history_of(approved_event.id) == [
        (EventHistoryKind.SAFETY_REVIEW_REQUESTED, COORDINATOR_ID, None)
    ]


@pytest.mark.parametrize("status", HOLDING_ARRANGEMENT_STATUSES, ids=lambda status: status.value)
def test_an_arrangement_that_is_not_approved_holds_the_event_back(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    status: BookingRequestStatus,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    held = arrange(status)

    refused = _refusal(db_session)

    assert refused.message == SAFETY_REVIEW_NOT_READY_MESSAGE
    assert refused.details == {
        "venue_arrangements": [f"Venue arrangement {held.id} is {status.value}."]
    }
    _assert_still_approved(approved_event, reload_event_request, history_of)


@pytest.mark.parametrize("retired", RETIRED_ARRANGEMENT_STATUSES, ids=lambda status: status.value)
def test_a_retired_arrangement_is_ignored(
    db_session: Session, arrange: Arrange, retired: BookingRequestStatus
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    arrange(retired)

    assert _submit(db_session).status is EventRequestStatus.SAFETY_REVIEW


def test_an_equipment_request_without_an_outcome_holds_the_event_back(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    add_line: AddLine,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    add_line(2)
    waiting = add_line(None)

    refused = _refusal(db_session)

    assert refused.details == {
        "equipment": [f"Equipment request {waiting.id} has no outcome from Technical Support."]
    }
    _assert_still_approved(approved_event, reload_event_request, history_of)


def test_one_refusal_names_every_venue_and_equipment_gap(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    add_line: AddLine,
    make_equipment_type: Callable[..., EquipmentType],
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    # A type no request uses, so no request's id equals its equipment type's id.
    save(make_equipment_type(name="Unused"))
    arrange(BookingRequestStatus.APPROVED)
    pending = arrange(BookingRequestStatus.PENDING)
    rejected = arrange(BookingRequestStatus.REJECTED)
    add_line(2)
    first_waiting = add_line(None)
    second_waiting = add_line(None)

    refused = _refusal(db_session)

    assert refused.details == {
        "venue_arrangements": [
            f"Venue arrangement {pending.id} is pending.",
            f"Venue arrangement {rejected.id} is rejected.",
        ],
        "equipment": [
            f"Equipment request {first_waiting.id} has no outcome from Technical Support.",
            f"Equipment request {second_waiting.id} has no outcome from Technical Support.",
        ],
    }
    _assert_still_approved(approved_event, reload_event_request, history_of)


# --------------------------------------------------------------------------
# AC2 — equipment is optional; ADR-0047 — a venue is not
# --------------------------------------------------------------------------


def test_an_event_with_no_equipment_requests_passes_the_equipment_check(
    db_session: Session, arrange: Arrange
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    assert _submit(db_session).status is EventRequestStatus.SAFETY_REVIEW


def test_an_event_with_no_venue_arranged_is_held_back(
    db_session: Session,
    approved_event: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    refused = _refusal(db_session)

    assert refused.details == {"venue_arrangements": ["The event has no venue arranged."]}
    _assert_still_approved(approved_event, reload_event_request, history_of)


# --------------------------------------------------------------------------
# Who may, and from which status (ADR-0047)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NOT_APPROVED_STATUSES, ids=lambda status: status.value)
def test_only_an_approved_event_can_be_submitted(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    save: Callable[..., None],
    status: EventRequestStatus,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    approved_event.status = status
    save(approved_event)

    refused = _refusal(db_session)

    assert refused.message == NOT_APPROVED_FOR_SAFETY_REVIEW_MESSAGE
    assert refused.details is None


def test_a_coordinator_not_assigned_to_the_event_gets_a_404(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    with pytest.raises(NotFoundError):
        _submit(db_session, OTHER_COORDINATOR_ID)

    _assert_still_approved(approved_event, reload_event_request, history_of)


# --------------------------------------------------------------------------
# ADR-0047 "Open" — an event in Safety Review can't be edited, nor its equipment
# changed, until SCRUM-98 sends it back to approved
# --------------------------------------------------------------------------


@pytest.fixture()
def event_in_review(approved_event: EventRequest, save: Callable[..., None]) -> EventRequest:
    """``approved_event``, now in Safety Review."""
    approved_event.status = EventRequestStatus.SAFETY_REVIEW
    save(approved_event)
    return approved_event


def test_an_event_in_safety_review_cannot_be_edited(
    db_session: Session, event_in_review: EventRequest, history_of: HistoryOf
) -> None:
    with pytest.raises(RequestNotEditableError) as exc_info:
        update_event_request(
            COORDINATOR_ID, REFERENCE, {"description": "Revised"}, session=db_session
        )

    assert exc_info.value.message == NOT_EDITABLE_MESSAGE
    assert history_of(event_in_review.id) == []


def test_the_equipment_of_an_event_in_safety_review_cannot_be_changed(
    db_session: Session,
    event_in_review: EventRequest,
    valid_equipment_line_payload: dict[str, Any],
    reload_event_request: ReloadEventRequest,
) -> None:
    with pytest.raises(EquipmentNotEditableError) as exc_info:
        add_equipment_line(
            COORDINATOR_ID, REFERENCE, valid_equipment_line_payload, session=db_session
        )

    assert exc_info.value.message == EQUIPMENT_NOT_EDITABLE_MESSAGE
    assert reload_event_request(event_in_review.id).equipment_lines == []


# --------------------------------------------------------------------------
# AC4 — every Safety Officer is told when an event enters Safety Review
# --------------------------------------------------------------------------


def test_every_safety_officer_is_notified_once_when_the_event_enters_safety_review(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    safety_officers: list[User],
    notifications_of: NotificationsOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    _submit(db_session)

    for officer_id in SAFETY_OFFICER_IDS:
        assert notifications_of(officer_id) == [
            (
                approved_event.id,
                REFERENCE,
                approved_event.name,
                NotificationKind.SAFETY_REVIEW_REQUESTED,
                None,
            )
        ]


def test_nobody_but_the_safety_officers_is_notified(
    db_session: Session,
    arrange: Arrange,
    safety_officers: list[User],
    notifications_of: NotificationsOf,
) -> None:
    arrange(BookingRequestStatus.APPROVED)

    _submit(db_session)

    for user_id in OTHER_USER_IDS:
        assert notifications_of(user_id) == []


def test_a_lost_notice_leaves_the_event_in_safety_review_and_is_logged(
    db_session: Session,
    approved_event: EventRequest,
    arrange: Arrange,
    safety_officers: list[User],
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    notifications_of: NotificationsOf,
    caplog: pytest.LogCaptureFixture,
) -> None:
    arrange(BookingRequestStatus.APPROVED)
    real_commit = db_session.commit
    commits: list[str] = []

    def commit_unless_notifying() -> None:
        # The first commit saves the move and its history; the second is the notices'.
        commits.append("commit")
        if len(commits) == 2:
            raise OperationalError("INSERT", {}, Exception("database down"))
        real_commit()

    with (
        patch.object(db_session, "commit", side_effect=commit_unless_notifying),
        caplog.at_level(logging.WARNING, logger="connectsphere.events"),
    ):
        _submit(db_session)

    assert reload_event_request(approved_event.id).status is EventRequestStatus.SAFETY_REVIEW
    assert history_of(approved_event.id) == [
        (EventHistoryKind.SAFETY_REVIEW_REQUESTED, COORDINATOR_ID, None)
    ]
    for officer_id in SAFETY_OFFICER_IDS:
        assert notifications_of(officer_id) == []
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference={REFERENCE} kind=safety_review_requested"
    ]


def test_a_refused_submission_notifies_no_safety_officer(
    db_session: Session,
    arrange: Arrange,
    safety_officers: list[User],
    notifications_of: NotificationsOf,
) -> None:
    arrange(BookingRequestStatus.PENDING)

    _refusal(db_session)

    for officer_id in SAFETY_OFFICER_IDS:
        assert notifications_of(officer_id) == []
