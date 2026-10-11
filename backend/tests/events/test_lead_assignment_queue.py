"""Unit tests for SCRUM-95 — the Event Coordinator Lead assigns each submitted request.

This file starts with AC7, the role itself: an account can be given the Event
Coordinator Lead role (ADR-0036). AC1 follows: submitting a request no longer
assigns anybody, so it arrives in the Lead's queue unassigned, superseding
SCRUM-30's least-loaded assignment (ADR-0018) and SCRUM-28 AC3's notice to the
coordinators.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.permissions import EXTERNAL_ROLES, INTERNAL_ROLES, Role, is_internal_role
from app.modules.auth.services import create_staff_user
from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.events.services import submit_draft_event_request
from app.modules.notifications.services import NotificationKind
from tests.events.cases import COMPLETE_DRAFT_PAYLOAD, DRAFT_REFERENCE

pytestmark = pytest.mark.scrum_95

ORGANISER_ID = 7

#: The coordinators ``saved_users`` saves, either of whom SCRUM-30 would have assigned.
COORDINATOR_IDS = [3, 9]

HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssignmentNoticesOf = Callable[[int], list[NotificationKind]]
SaveDraft = Callable[[int, dict[str, Any]], EventRequest]


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
