"""Unit tests for SCRUM-87 "Reassign an event to a different coordinator": the service.

AC1: an assigned event can be reassigned to a different Event Coordinator, named by
their email; only its current coordinator may do it, while the request is submitted,
under review or confirmed (ADR-0021). AC2: the event still has exactly one
coordinator. AC3 and AC7: the change is written to the event history in the same
commit as the change itself, naming the previous and the new coordinator by id and
by name, who did it and when.
AC4 and AC5: the event leaves the previous coordinator's list, and their access to
its equipment, for the new coordinator's. AC6: the organiser's event record shows
the new coordinator's name and email. A refused reassignment changes nothing.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3), so lookups and lists are real
SQL; the one-commit test uses ``mock_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    ALREADY_ASSIGNED_MESSAGE,
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_A_COORDINATOR_MESSAGE,
    NOT_ASSIGNED_MESSAGE,
    NOT_REASSIGNABLE_MESSAGE,
    CoordinatorContact,
    RequestNotReassignableError,
    add_equipment_line,
    get_event_record_for_organiser,
    list_event_requests_for_coordinator,
    reassign_coordinator,
)

pytestmark = pytest.mark.scrum_87

Reassign = Callable[[int, str], tuple[EventRequest, CoordinatorContact]]
CoordinatorOf = Callable[[int], int | None]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssertNothingChanged = Callable[[int | None], None]

REFERENCE = "EVR-AAAAAAAA"
NINE = "coordinator9@example.com"
COORDINATOR_NINE = CoordinatorContact(full_name="Coordinator Nine", email=NINE)
#: What the history says when coordinator 3's event goes to coordinator 9.
FROM_3_TO_9 = {
    "previous_coordinator_id": 3,
    "previous_coordinator_name": "Coordinator Three",
    "coordinator_id": 9,
    "coordinator_name": "Coordinator Nine",
}

REASSIGNABLE = [
    EventRequestStatus.SUBMITTED,
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.CONFIRMED,
]
NOT_REASSIGNABLE = [
    EventRequestStatus.DRAFT,
    EventRequestStatus.COMPLETED,
    EventRequestStatus.CANCELLED,
    EventRequestStatus.REJECTED,
]


@pytest.fixture()
def assert_nothing_changed(
    saved_event_request: EventRequest, coordinator_of: CoordinatorOf, history_of: HistoryOf
) -> AssertNothingChanged:
    """Check the request still has this coordinator and no history was written."""

    def _assert(coordinator_id: int | None) -> None:
        assert coordinator_of(saved_event_request.id) == coordinator_id
        assert history_of(saved_event_request.id) == []

    return _assert


@pytest.fixture()
def set_status(
    saved_event_request: EventRequest, save: Callable[..., None]
) -> Callable[[EventRequestStatus], None]:
    """Move ``saved_event_request`` to another status and save it."""

    def _set(status: EventRequestStatus) -> None:
        saved_event_request.status = status
        save(saved_event_request)

    return _set


# --------------------------------------------------------------------------
# AC1, AC2 — an assigned event moves to another Event Coordinator, and only one
# --------------------------------------------------------------------------


def test_an_assigned_event_is_reassigned_to_another_event_coordinator(
    reassign: Reassign, coordinator_of: CoordinatorOf, saved_event_request: EventRequest
) -> None:
    event_request, _ = reassign(3, NINE)

    assert event_request.reference == REFERENCE
    assert coordinator_of(saved_event_request.id) == 9


def test_the_new_coordinators_email_ignores_case(
    reassign: Reassign, coordinator_of: CoordinatorOf, saved_event_request: EventRequest
) -> None:
    reassign(3, "Coordinator9@Example.COM")

    assert coordinator_of(saved_event_request.id) == 9


def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_users: list[User],
    saved_event_request: EventRequest,
    coordinator_of: CoordinatorOf,
) -> None:
    reassign_coordinator(3, "  evr-aaaaaaaa ", {"coordinator_email": NINE})

    assert coordinator_of(saved_event_request.id) == 9


@pytest.mark.parametrize("status", REASSIGNABLE, ids=lambda status: status.value)
def test_a_submitted_under_review_or_confirmed_event_can_be_reassigned(
    reassign: Reassign,
    set_status: Callable[[EventRequestStatus], None],
    coordinator_of: CoordinatorOf,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    reassign(3, NINE)

    assert coordinator_of(saved_event_request.id) == 9


# --------------------------------------------------------------------------
# ADR-0021 — what can't be reassigned, and to whom; a refusal changes nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [EventRequestStatus.SUBMITTED, EventRequestStatus.COMPLETED],
    ids=lambda status: status.value,
)
def test_only_the_events_own_coordinator_may_reassign_it(
    reassign: Reassign,
    set_status: Callable[[EventRequestStatus], None],
    assert_nothing_changed: AssertNothingChanged,
    status: EventRequestStatus,
) -> None:
    """Another coordinator gets the equipment routes' "not yours" 404 (ADR-0019).

    It comes before the status check, so a finished event says no more than an open
    one to a coordinator it doesn't belong to.
    """
    set_status(status)

    with pytest.raises(NotFoundError) as exc_info:
        reassign(9, NINE)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(3)


@pytest.mark.parametrize("status", NOT_REASSIGNABLE, ids=lambda status: status.value)
def test_a_draft_or_finished_event_cannot_be_reassigned(
    reassign: Reassign,
    set_status: Callable[[EventRequestStatus], None],
    assert_nothing_changed: AssertNothingChanged,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    with pytest.raises(RequestNotReassignableError) as exc_info:
        reassign(3, NINE)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "request_not_reassignable")
    assert refused.message == NOT_REASSIGNABLE_MESSAGE
    assert_nothing_changed(3)


def test_an_unassigned_event_cannot_be_reassigned(
    reassign: Reassign,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    assert_nothing_changed: AssertNothingChanged,
) -> None:
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    with pytest.raises(RequestNotReassignableError) as exc_info:
        reassign(3, NINE)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "request_not_reassignable")
    assert refused.message == NOT_ASSIGNED_MESSAGE
    assert_nothing_changed(None)


def test_reassigning_to_the_current_coordinator_is_a_conflict(
    reassign: Reassign, assert_nothing_changed: AssertNothingChanged
) -> None:
    with pytest.raises(ConflictError) as exc_info:
        reassign(3, "coordinator3@example.com")

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "conflict")
    assert refused.message == ALREADY_ASSIGNED_MESSAGE
    assert_nothing_changed(3)


@pytest.mark.parametrize(
    "email",
    ["staff4@example.com", "organiser7@example.com", "nobody@example.com"],
    ids=["venue-staff", "event-organiser", "no-such-user"],
)
def test_only_an_event_coordinator_can_be_given_the_event(
    reassign: Reassign, assert_nothing_changed: AssertNothingChanged, email: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        reassign(3, email)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"coordinator_email": [NOT_A_COORDINATOR_MESSAGE]}
    assert_nothing_changed(3)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, "Missing data for required field."),
        ({"coordinator_email": "not-an-email"}, "Not a valid email address."),
    ],
    ids=["missing", "not-an-email"],
)
def test_the_new_coordinators_email_is_required_and_checked(
    saved_users: list[User],
    assert_nothing_changed: AssertNothingChanged,
    payload: dict[str, Any],
    expected: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        reassign_coordinator(3, REFERENCE, payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"coordinator_email": [expected]}
    assert_nothing_changed(3)


def test_an_unknown_reference_is_404(
    saved_users: list[User], assert_nothing_changed: AssertNothingChanged
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        reassign_coordinator(3, "EVR-ZZZZZZZZ", {"coordinator_email": NINE})

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(3)


# --------------------------------------------------------------------------
# AC3, AC7 — the history keeps the previous coordinator, who changed it and when
# --------------------------------------------------------------------------


def test_the_reassignment_is_recorded_in_the_history_with_who_did_it_and_when(
    reassign: Reassign,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    db_session: Session,
) -> None:
    before = datetime.now(timezone.utc)

    reassign(3, NINE)

    after = datetime.now(timezone.utc)
    assert history_of(saved_event_request.id) == [
        (EventHistoryKind.COORDINATOR_REASSIGNED, 3, FROM_3_TO_9)
    ]
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert before <= entry.occurred_at <= after


def test_the_change_and_its_history_entry_are_saved_in_one_commit(
    mock_session: MagicMock, reassignment_lookups: EventRequest
) -> None:
    """At the first commit, the new coordinator is set and the entry already added."""
    seen_at_commit: list[tuple[int | None, list[EventHistoryKind]]] = []

    def note_what_is_saved() -> None:
        added_kinds = [call.args[0].kind for call in mock_session.add.call_args_list]
        seen_at_commit.append((reassignment_lookups.coordinator_id, added_kinds))

    mock_session.commit.side_effect = note_what_is_saved

    reassign_coordinator(3, REFERENCE, {"coordinator_email": NINE}, session=mock_session)

    assert seen_at_commit[0] == (9, [EventHistoryKind.COORDINATOR_REASSIGNED])


# --------------------------------------------------------------------------
# AC4, AC5 — the event, and access to it, move to the new coordinator
# --------------------------------------------------------------------------


def test_the_event_moves_from_the_previous_coordinators_list_to_the_new_ones(
    reassign: Reassign,
) -> None:
    reassign(3, NINE)

    assigned_to_9 = list_event_requests_for_coordinator(9)
    assert [event_request.reference for event_request in assigned_to_9] == [REFERENCE]
    assert list_event_requests_for_coordinator(3) == []


def test_the_previous_coordinator_can_no_longer_change_the_events_equipment(
    reassign: Reassign, valid_equipment_line_payload: dict[str, Any]
) -> None:
    reassign(3, NINE)

    with pytest.raises(NotFoundError) as exc_info:
        add_equipment_line(3, REFERENCE, valid_equipment_line_payload)

    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


def test_the_new_coordinator_can_change_the_events_equipment(
    reassign: Reassign,
    valid_equipment_line_payload: dict[str, Any],
    saved_event_request: EventRequest,
) -> None:
    reassign(3, NINE)

    line = add_equipment_line(9, REFERENCE, valid_equipment_line_payload)

    assert (line.event_request_id, line.quantity) == (saved_event_request.id, 2)


# --------------------------------------------------------------------------
# AC6 — the organiser sees the new coordinator's name and contact details
# --------------------------------------------------------------------------


def test_the_new_coordinators_contact_is_returned_and_shown_to_the_organiser(
    reassign: Reassign,
) -> None:
    _, contact = reassign(3, NINE)

    assert contact == COORDINATOR_NINE
    assert get_event_record_for_organiser(7, REFERENCE)[1] == COORDINATOR_NINE
