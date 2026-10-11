"""Unit tests for SCRUM-95 — the Event Coordinator Lead assigns each submitted request.

This file starts with AC7, the role itself: an account can be given the Event
Coordinator Lead role (ADR-0036). AC1 follows: submitting a request no longer
assigns anybody, so it arrives in the Lead's queue unassigned, superseding
SCRUM-30's least-loaded assignment (ADR-0018) and SCRUM-28 AC3's notice to the
coordinators. AC2 is the queue itself, and AC3 and AC5 the Lead's assignment: the
request gets one coordinator, leaves the queue, and the coordinator and the organiser
are each told once, with the assignment written to the event history.

AC5 also says the event appears in the coordinator's list. That needs no new code --
the list reads ``coordinator_id`` (ADR-0018) -- so it is proved where the list is
tested, in ``test_list_assigned_requests.py``, through the ``lead_assigns`` fixture
that now calls :func:`assign_coordinator_to_request`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import EXTERNAL_ROLES, INTERNAL_ROLES, Role, is_internal_role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.schemas import UnassignedRequestSchema
from app.modules.events.services import (
    ALREADY_HAS_COORDINATOR_MESSAGE,
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_A_COORDINATOR_MESSAGE,
    NOT_ASSIGNABLE_MESSAGE,
    CoordinatorContact,
    RequestNotAssignableError,
    assign_coordinator_to_request,
    list_unassigned_requests,
    submit_draft_event_request,
)
from app.modules.notifications.services import NotificationKind
from tests.events.cases import (
    COMPLETE_DRAFT_PAYLOAD,
    DRAFT_REFERENCE,
    LEAD_ID,
    LOST_NOTIFICATION_CASES,
    NON_DRAFT_STATUSES,
)

pytestmark = pytest.mark.scrum_95

ORGANISER_ID = 7

#: The coordinators ``saved_users`` saves, either of whom SCRUM-30 would have assigned.
COORDINATOR_IDS = [3, 9]

#: The request the Lead assigns in these tests, and what its notifications record.
REFERENCE = "EVR-AAAAAAAA"
REQUEST_NAME = "ConnectSphere Partner Summit"

#: The emails ``saved_users`` gives Event Coordinators 3 and 9 (ADR-0021).
THREE = "coordinator3@example.com"
NINE = "coordinator9@example.com"

AssertNothingWasAssigned = Callable[[EventRequest, int | None], None]
CoordinatorOf = Callable[[int], int | None]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssignmentNoticesOf = Callable[[int], list[NotificationKind]]
LeadAssigns = Callable[[EventRequest, int], None]
NotificationsOf = Callable[[int], list[tuple[Any, ...]]]
Save = Callable[..., None]
SaveDraft = Callable[[int, dict[str, Any]], EventRequest]
MakeEventRequest = Callable[..., EventRequest]


# --------------------------------------------------------------------------
# AC7 — a user account can be given the Event Coordinator Lead role
# --------------------------------------------------------------------------


def test_the_lead_role_is_internal_staff() -> None:
    assert Role.EVENT_COORDINATOR_LEAD.value == "event_coordinator_lead"
    assert Role.EVENT_COORDINATOR_LEAD in INTERNAL_ROLES
    assert Role.EVENT_COORDINATOR_LEAD not in EXTERNAL_ROLES
    assert is_internal_role("event_coordinator_lead")


def test_a_staff_account_can_be_created_with_the_lead_role(
    mock_session: MagicMock, valid_registration_payload: dict[str, Any]
) -> None:
    payload = {**valid_registration_payload, "role": Role.EVENT_COORDINATOR_LEAD.value}

    user = create_staff_user(payload, session=mock_session)

    assert user.role is Role.EVENT_COORDINATOR_LEAD
    mock_session.add.assert_called_once_with(user)


# --------------------------------------------------------------------------
# AC1 — a submitted request is assigned to nobody, however it was submitted
# --------------------------------------------------------------------------


@pytest.fixture(params=["a-new-request", "a-draft"])
def submitted_request(
    request: pytest.FixtureRequest,
    saved_users: list[User],
    submit_valid_request: Callable[..., EventRequest],
    save_draft: SaveDraft,
    db_session: Session,
    today: date,
) -> EventRequest:
    """One submitted request, through each of the two paths that submit one.

    ``saved_users`` saves Event Coordinators 3 and 9, so until SCRUM-95 one of them
    would have been assigned; nothing about the request itself says otherwise.
    """
    if request.param == "a-new-request":
        return submit_valid_request()
    save_draft(ORGANISER_ID, COMPLETE_DRAFT_PAYLOAD)
    return submit_draft_event_request(
        ORGANISER_ID, DRAFT_REFERENCE, session=db_session, today=today
    )


def test_a_submitted_request_has_no_coordinator(
    submitted_request: EventRequest, coordinator_of: CoordinatorOf
) -> None:
    assert coordinator_of(submitted_request.id) is None


def test_submitting_records_no_assignment_in_the_history(
    submitted_request: EventRequest, history_of: HistoryOf
) -> None:
    """Nothing has happened to the request yet, so its history is empty."""
    assert history_of(submitted_request.id) == []


@pytest.mark.parametrize("user_id", [*COORDINATOR_IDS, ORGANISER_ID])
def test_submitting_tells_nobody_a_coordinator_was_assigned(
    submitted_request: EventRequest,
    assignment_notices_of: AssignmentNoticesOf,
    user_id: int,
) -> None:
    """Only the assignment notices: the Lead's queue notice (AC4) is a separate one."""
    assert assignment_notices_of(user_id) == []


# --------------------------------------------------------------------------
# AC2 — the Lead's queue: submitted requests nobody has yet, oldest first
# --------------------------------------------------------------------------


@pytest.fixture()
def queued(save: Callable[..., None], make_event_request: MakeEventRequest) -> MakeEventRequest:
    """Save a request created at this UTC hour of 2026-10-01 (its submission time)."""

    def _queued(reference: str, created_hour: int = 9, **kwargs: Any) -> EventRequest:
        event_request = make_event_request(reference=reference, **kwargs)
        event_request.created_at = datetime(2026, 10, 1, created_hour, tzinfo=timezone.utc)
        save(event_request)
        return event_request

    return _queued


def references_in_queue() -> list[str]:
    return [event_request.reference for event_request in list_unassigned_requests()]


def test_the_queue_holds_only_submitted_requests_with_no_coordinator(
    queued: MakeEventRequest,
) -> None:
    queued("EVR-WAITING1")
    queued("EVR-ASSIGNED", coordinator_id=3)

    assert references_in_queue() == ["EVR-WAITING1"]


def test_a_request_assigned_before_the_lead_role_existed_is_not_in_the_queue(
    queued: MakeEventRequest,
) -> None:
    """Review Focus 3: SCRUM-30 gave it a coordinator; no migration takes it away."""
    queued("EVR-OLDASSIGN", coordinator_id=9)

    assert references_in_queue() == []


def test_an_empty_queue_is_an_empty_list(db_session: Session) -> None:
    """Review Focus 4: nothing waiting is an answer, not a 404."""
    assert list_unassigned_requests() == []


#: Every non-draft status but ``submitted``: none of them is waiting for the Lead.
#: ``cancelled`` and ``rejected`` are the ones reachable with no coordinator, so they
#: are what the status check exists for (ADR-0036).
NOT_WAITING_STATUSES = [
    status for status in NON_DRAFT_STATUSES if status is not EventRequestStatus.SUBMITTED
]


@pytest.mark.parametrize(
    "status", [*NOT_WAITING_STATUSES, EventRequestStatus.DRAFT], ids=lambda status: status.value
)
def test_only_a_submitted_request_is_queued(
    queued: MakeEventRequest, status: EventRequestStatus
) -> None:
    """A draft isn't waiting for the Lead yet; a cancelled or rejected one no longer is.

    Cancelled and rejected are the cases the narrow ``status == submitted`` filter
    exists for: both are reachable from ``submitted`` with no coordinator, so a filter
    that only excluded drafts would queue them (ADR-0036).
    """
    queued("EVR-OTHERSTAT", status=status)

    assert references_in_queue() == []


def test_the_oldest_submission_comes_first_and_an_equal_time_goes_by_id(
    queued: MakeEventRequest,
) -> None:
    queued("EVR-LATE0001", created_hour=12)
    queued("EVR-TIE00001", created_hour=9)
    queued("EVR-TIE00002", created_hour=9)
    queued("EVR-EARLY001", created_hour=8)

    assert references_in_queue() == [
        "EVR-EARLY001",
        "EVR-TIE00001",
        "EVR-TIE00002",
        "EVR-LATE0001",
    ]


def test_each_queue_entry_shows_its_reference_and_exactly_what_ac2_lists(
    make_event_request: MakeEventRequest,
) -> None:
    """The reference, then AC2: name, date, times, attendance, submission time."""
    event_request = make_event_request()
    event_request.created_at = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)

    shown = UnassignedRequestSchema().dump(event_request)

    assert shown == {
        "reference": "EVR-AAAAAAAA",
        "name": "Partner Summit",
        "proposed_date": "2026-10-15",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "expected_attendance": 250,
        "submitted_at": "2026-10-01T17:00:00+08:00",
    }


# --------------------------------------------------------------------------
# AC3, AC5 — the Lead gives one waiting request to one Event Coordinator
# --------------------------------------------------------------------------


@pytest.fixture()
def waiting_request(
    saved_users: list[User], submit_valid_request: Callable[..., EventRequest]
) -> EventRequest:
    """``EVR-AAAAAAAA``: organiser 7's submitted request, waiting in the queue."""
    return submit_valid_request()


@pytest.fixture()
def assignment_lookups(
    mock_session: MagicMock,
    make_event_request: MakeEventRequest,
    make_user: Callable[..., User],
) -> EventRequest:
    """Make ``mock_session`` find what assigning ``EVR-AAAAAAAA`` to 3 looks up.

    The unassigned request by its reference, then Event Coordinator 3 by email, then
    that coordinator by id for the name and email the organiser sees. Returns the
    request, so a test can read the coordinator the service set on it.
    """
    event_request = make_event_request()
    event_request.id = 1
    coordinator = make_user(
        email=THREE, full_name="Coordinator Three", role=Role.EVENT_COORDINATOR, user_id=3
    )
    mock_session.scalar.side_effect = [event_request, coordinator]
    mock_session.get.return_value = coordinator
    return event_request


def test_the_lead_gives_the_request_to_the_named_coordinator(
    waiting_request: EventRequest, lead_assigns: LeadAssigns, coordinator_of: CoordinatorOf
) -> None:
    """AC3: the column itself holds that one coordinator, and nothing else changes."""
    lead_assigns(waiting_request, 3)

    assert coordinator_of(waiting_request.id) == 3
    assert waiting_request.status is EventRequestStatus.SUBMITTED


def test_the_lead_is_given_back_the_coordinators_name_and_email(
    waiting_request: EventRequest, coordinator_three: CoordinatorContact
) -> None:
    """What the route shows the organiser afterwards: a name and email, never an id."""
    event_request, coordinator = assign_coordinator_to_request(
        REFERENCE, {"coordinator_email": THREE}, assigned_by=LEAD_ID
    )

    assert event_request.reference == REFERENCE
    assert coordinator == coordinator_three


def test_an_assigned_request_leaves_the_queue(
    waiting_request: EventRequest, lead_assigns: LeadAssigns
) -> None:
    assert references_in_queue() == [REFERENCE]

    lead_assigns(waiting_request, 3)

    assert references_in_queue() == []


def test_the_assigned_coordinator_gets_one_assignment_notification(
    waiting_request: EventRequest, lead_assigns: LeadAssigns, notifications_of: NotificationsOf
) -> None:
    """AC5, and SCRUM-30 AC4's notice, raised here now instead of on submission."""
    lead_assigns(waiting_request, 3)

    assert notifications_of(3) == [
        (
            waiting_request.id,
            REFERENCE,
            REQUEST_NAME,
            NotificationKind.COORDINATOR_ASSIGNED,
            None,
        )
    ]


def test_the_organiser_is_told_a_coordinator_was_assigned(
    waiting_request: EventRequest, lead_assigns: LeadAssigns, notifications_of: NotificationsOf
) -> None:
    """AC5, and SCRUM-39 AC1's notice (ADR-0030), raised here now."""
    lead_assigns(waiting_request, 3)

    assert notifications_of(ORGANISER_ID) == [
        (waiting_request.id, REFERENCE, REQUEST_NAME, NotificationKind.REQUEST_ASSIGNED, None)
    ]


@pytest.mark.parametrize(
    "user_id",
    [9, 4, 5, 2],
    ids=["the-other-coordinator", "venue-staff", "technical-support-5", "technical-support-2"],
)
def test_nobody_else_is_told_about_the_assignment(
    waiting_request: EventRequest,
    lead_assigns: LeadAssigns,
    notifications_of: NotificationsOf,
    user_id: int,
) -> None:
    lead_assigns(waiting_request, 3)

    assert notifications_of(user_id) == []


def test_the_assignment_is_recorded_once_in_the_history_with_who_did_it_and_when(
    waiting_request: EventRequest,
    lead_assigns: LeadAssigns,
    history_of: HistoryOf,
    db_session: Session,
) -> None:
    """AC3's audit trail: the actor is the Lead, where SCRUM-30's was NULL."""
    before = datetime.now(timezone.utc)

    lead_assigns(waiting_request, 3)

    after = datetime.now(timezone.utc)
    assert history_of(waiting_request.id) == [
        (EventHistoryKind.COORDINATOR_ASSIGNED, LEAD_ID, {"coordinator_id": 3})
    ]
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert before <= entry.occurred_at <= after


def test_the_assignment_and_its_history_entry_are_saved_in_one_commit(
    mock_session: MagicMock, assignment_lookups: EventRequest
) -> None:
    """At the first commit the coordinator is set and the entry is already added."""
    seen_at_commit: list[tuple[int | None, list[EventHistoryKind]]] = []

    def note_what_is_saved() -> None:
        added_kinds = [call.args[0].kind for call in mock_session.add.call_args_list]
        seen_at_commit.append((assignment_lookups.coordinator_id, added_kinds))

    mock_session.commit.side_effect = note_what_is_saved

    assign_coordinator_to_request(
        REFERENCE, {"coordinator_email": THREE}, assigned_by=LEAD_ID, session=mock_session
    )

    assert seen_at_commit[0] == (3, [EventHistoryKind.COORDINATOR_ASSIGNED])


@pytest.mark.parametrize(("commits", "lost_kind"), LOST_NOTIFICATION_CASES)
def test_a_failed_notification_write_still_returns_the_assigned_request(
    mock_session: MagicMock,
    assignment_lookups: EventRequest,
    caplog: pytest.LogCaptureFixture,
    commits: list[Exception | None],
    lost_kind: str,
) -> None:
    """The assignment is committed first; failing its reply would invite a retry.

    The two notices are separate writes, so losing one still sends the other
    (ADR-0015).
    """
    mock_session.commit.side_effect = commits

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        event_request, _ = assign_coordinator_to_request(
            REFERENCE, {"coordinator_email": THREE}, assigned_by=LEAD_ID, session=mock_session
        )

    assert event_request.coordinator_id == 3
    assert mock_session.commit.call_count == 3
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        f"event_request_notification_failed reference={REFERENCE} kind={lost_kind}"
    ]


# --------------------------------------------------------------------------
# ADR-0036 — what the Lead can't assign, and to whom; a refusal changes nothing
# --------------------------------------------------------------------------

#: Each refusal, on a request where every later check would also fail, so the answer
#: names the first failure (ADR-0036). The request is saved with this status and
#: coordinator, and the payload always names an email no Event Coordinator has.
FIRST_FAILURE_CASES = [
    pytest.param(EventRequestStatus.DRAFT, 3, NotFoundError, id="reference-before-assigned"),
    pytest.param(
        EventRequestStatus.CANCELLED, 3, ConflictError, id="already-assigned-before-status"
    ),
    pytest.param(
        EventRequestStatus.CANCELLED, None, RequestNotAssignableError, id="status-before-email"
    ),
]


@pytest.fixture()
def assert_nothing_was_assigned(
    coordinator_of: CoordinatorOf, history_of: HistoryOf, notifications_of: NotificationsOf
) -> AssertNothingWasAssigned:
    """Check the request still has this coordinator and nothing was written or sent."""

    def _assert(event_request: EventRequest, coordinator_id: int | None) -> None:
        assert coordinator_of(event_request.id) == coordinator_id
        assert history_of(event_request.id) == []
        assert notifications_of(3) == []
        assert notifications_of(9) == []
        assert notifications_of(ORGANISER_ID) == []

    return _assert


def test_a_request_that_already_has_a_coordinator_cannot_be_assigned(
    saved_users: list[User],
    saved_event_request: EventRequest,
    assert_nothing_was_assigned: AssertNothingWasAssigned,
) -> None:
    """Review Focus 1: a first assignment never moves an event off its coordinator.

    Moving one is a reassignment: the coordinator's own is SCRUM-87's ``/reassign``,
    and the Lead's is SCRUM-96's (ADR-0021 decision 6, ADR-0036).
    """
    with pytest.raises(ConflictError) as exc_info:
        assign_coordinator_to_request(REFERENCE, {"coordinator_email": NINE}, assigned_by=LEAD_ID)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "conflict")
    assert refused.message == ALREADY_HAS_COORDINATOR_MESSAGE
    assert_nothing_was_assigned(saved_event_request, 3)


@pytest.mark.parametrize("status", NOT_WAITING_STATUSES, ids=lambda status: status.value)
def test_only_a_request_waiting_in_the_queue_can_be_assigned(
    saved_users: list[User],
    save: Save,
    make_event_request: MakeEventRequest,
    assert_nothing_was_assigned: AssertNothingWasAssigned,
    status: EventRequestStatus,
) -> None:
    """A cancelled or rejected request can have no coordinator and still not be waiting.

    The other statuses are listed too: the guard looks at status alone, so pairing each
    with no coordinator costs nothing and keeps the test exhaustive.

    AC3 gives the Lead the requests *in the queue*, which is the one status
    :func:`list_unassigned_requests` lists, so both read the same definition.
    """
    event_request = make_event_request(status=status)
    save(event_request)

    with pytest.raises(RequestNotAssignableError) as exc_info:
        assign_coordinator_to_request(REFERENCE, {"coordinator_email": THREE}, assigned_by=LEAD_ID)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "request_not_assignable")
    assert refused.message == NOT_ASSIGNABLE_MESSAGE
    assert_nothing_was_assigned(event_request, None)


def test_a_draft_cannot_be_assigned(
    saved_users: list[User],
    save: Save,
    make_event_request: MakeEventRequest,
    assert_nothing_was_assigned: AssertNothingWasAssigned,
) -> None:
    """A draft is hidden from every internal role, so it is the 404, not a 409.

    SCRUM-20 AC4, ADR-0024: the Lead resolves a reference the way all internal staff
    do, so a draft can't be found at all rather than refused as "not waiting".
    """
    event_request = make_event_request(status=EventRequestStatus.DRAFT)
    save(event_request)

    with pytest.raises(NotFoundError) as exc_info:
        assign_coordinator_to_request(REFERENCE, {"coordinator_email": THREE}, assigned_by=LEAD_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_was_assigned(event_request, None)


@pytest.mark.parametrize(
    "email",
    ["staff4@example.com", "organiser7@example.com", "nobody@example.com"],
    ids=["venue-staff", "event-organiser", "no-such-user"],
)
def test_only_an_event_coordinator_can_be_given_the_request(
    waiting_request: EventRequest,
    assert_nothing_was_assigned: AssertNothingWasAssigned,
    email: str,
) -> None:
    """Review Focus 2: another role's email and an unknown one get the same 400.

    So the reply never says whether someone else holds that address (ADR-0021
    decision 4), and the Lead can't use it to enumerate the staff.
    """
    with pytest.raises(ValidationError) as exc_info:
        assign_coordinator_to_request(REFERENCE, {"coordinator_email": email}, assigned_by=LEAD_ID)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"coordinator_email": [NOT_A_COORDINATOR_MESSAGE]}
    assert_nothing_was_assigned(waiting_request, None)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, "Missing data for required field."),
        ({"coordinator_email": "not-an-email"}, "Not a valid email address."),
    ],
    ids=["missing", "not-an-email"],
)
def test_the_coordinators_email_is_required_and_checked(
    waiting_request: EventRequest,
    assert_nothing_was_assigned: AssertNothingWasAssigned,
    payload: dict[str, Any],
    expected: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        assign_coordinator_to_request(REFERENCE, payload, assigned_by=LEAD_ID)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"coordinator_email": [expected]}
    assert_nothing_was_assigned(waiting_request, None)


def test_an_invalid_payload_is_refused_before_the_reference_is_looked_up(
    db_session: Session,
) -> None:
    """The body is the caller's own, so checking it first reveals no request."""
    with pytest.raises(ValidationError) as exc_info:
        assign_coordinator_to_request("EVR-ZZZZZZZZ", {}, assigned_by=LEAD_ID)

    assert exc_info.value.details == {"coordinator_email": ["Missing data for required field."]}


@pytest.mark.parametrize(("status", "coordinator_id", "expected"), FIRST_FAILURE_CASES)
def test_the_first_failure_decides_the_answer(
    saved_users: list[User],
    save: Save,
    make_event_request: MakeEventRequest,
    status: EventRequestStatus,
    coordinator_id: int | None,
    expected: type[AppError],
) -> None:
    """Every check after the one each case names would fail on this request too.

    The email lookup is last, so a refused assignment never resolves an address.
    """
    save(make_event_request(status=status, coordinator_id=coordinator_id))

    with pytest.raises(expected):
        assign_coordinator_to_request(
            REFERENCE, {"coordinator_email": "nobody@example.com"}, assigned_by=LEAD_ID
        )
