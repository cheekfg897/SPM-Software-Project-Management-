"""Unit tests for SCRUM-95 — the Event Coordinator Lead assigns each submitted request.

This file starts with AC7, the role itself: an account can be given the Event
Coordinator Lead role (ADR-0036). AC1 follows: submitting a request no longer
assigns anybody, so it arrives in the Lead's queue unassigned, superseding
SCRUM-30's least-loaded assignment (ADR-0018) and SCRUM-28 AC3's notice to the
coordinators.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import EXTERNAL_ROLES, INTERNAL_ROLES, Role, is_internal_role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.schemas import UnassignedRequestSchema
from app.modules.events.services import list_unassigned_requests, submit_draft_event_request
from app.modules.notifications.services import NotificationKind
from tests.events.cases import COMPLETE_DRAFT_PAYLOAD, DRAFT_REFERENCE

pytestmark = pytest.mark.scrum_95

ORGANISER_ID = 7

#: The coordinators ``saved_users`` saves, either of whom SCRUM-30 would have assigned.
COORDINATOR_IDS = [3, 9]

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssignmentNoticesOf = Callable[[int], list[NotificationKind]]
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
    submitted_request: EventRequest, coordinator_of: Callable[[int], int | None]
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


@pytest.mark.parametrize(
    "status",
    [EventRequestStatus.DRAFT, EventRequestStatus.UNDER_REVIEW, EventRequestStatus.APPROVED],
)
def test_only_a_submitted_request_is_queued(
    queued: MakeEventRequest, status: EventRequestStatus
) -> None:
    """A draft is not waiting for the Lead yet; a later request has a coordinator."""
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


def test_each_queue_entry_shows_exactly_what_ac2_lists(
    make_event_request: MakeEventRequest,
) -> None:
    """Name, date, times, expected attendance and submission time, in business time."""
    event_request = make_event_request()
    event_request.created_at = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)

    shown = UnassignedRequestSchema().dump(event_request)

    assert shown == {
        "name": "Partner Summit",
        "proposed_date": "2026-10-15",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "expected_attendance": 250,
        "submitted_at": "2026-10-01T17:00:00+08:00",
    }
