"""Unit tests for SCRUM-31 "Review and decide a submitted request": starting a review.

AC3: the assigned coordinator moves a submitted request to under review. AC5: nobody
else may; another coordinator's request, or one with no coordinator, gets the same 404
as an unknown reference (ADR-0019). Only a submitted request can be moved; any other
status is a 409 (ADR-0028). The move is written to the event history in the same
commit, with who did it and when, and nobody is notified.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, submitted, assigned to Event Coordinator 3); the one-commit test
uses ``mock_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_REVIEWABLE_MESSAGE,
    RequestNotReviewableError,
    start_event_request_review,
)

pytestmark = pytest.mark.scrum_31

StartReview = Callable[[int], EventRequest]
SetStatus = Callable[[EventRequestStatus], None]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssertNothingChanged = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
#: Every status a coordinator can see that isn't submitted. A draft is out of scope
#: here: it is hidden from coordinators altogether (SCRUM-20, ADR-0024).
NOT_REVIEWABLE = [
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.APPROVED,
    EventRequestStatus.CONFIRMED,
    EventRequestStatus.COMPLETED,
    EventRequestStatus.CANCELLED,
    EventRequestStatus.REJECTED,
]


@pytest.fixture()
def assert_nothing_changed(
    saved_event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> AssertNothingChanged:
    """Check the request still has this status and no history was written."""

    def _assert(status: EventRequestStatus) -> None:
        assert reload_event_request(saved_event_request.id).status is status
        assert history_of(saved_event_request.id) == []

    return _assert


# --------------------------------------------------------------------------
# AC3 — the assigned coordinator moves a submitted request to under review
# --------------------------------------------------------------------------


def test_the_assigned_coordinator_moves_a_submitted_request_to_under_review(
    start_review: StartReview,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
) -> None:
    reviewed = start_review(COORDINATOR_ID)

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.UNDER_REVIEW
    assert reviewed.reference == REFERENCE


def test_starting_review_is_recorded_with_who_did_it_and_when(
    start_review: StartReview,
    history_of: HistoryOf,
    saved_event_request: EventRequest,
    db_session: Session,
) -> None:
    before = datetime.now(timezone.utc)

    start_review(COORDINATOR_ID)

    after = datetime.now(timezone.utc)
    assert history_of(saved_event_request.id) == [
        (EventHistoryKind.REVIEW_STARTED, COORDINATOR_ID, None)
    ]
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert before <= entry.occurred_at <= after


def test_the_status_and_its_history_entry_are_saved_in_one_commit(
    mock_session: MagicMock, make_event_request: Callable[..., EventRequest]
) -> None:
    """At the first commit, the status has moved and the entry is already added."""
    event_request = make_event_request(coordinator_id=COORDINATOR_ID)
    mock_session.scalar.return_value = event_request
    seen_at_commit: list[tuple[EventRequestStatus, list[EventHistoryKind]]] = []

    def note_what_is_saved() -> None:
        added_kinds = [call.args[0].kind for call in mock_session.add.call_args_list]
        seen_at_commit.append((event_request.status, added_kinds))

    mock_session.commit.side_effect = note_what_is_saved

    start_event_request_review(COORDINATOR_ID, REFERENCE, session=mock_session)

    assert seen_at_commit == [(EventRequestStatus.UNDER_REVIEW, [EventHistoryKind.REVIEW_STARTED])]


def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_users: list[User],
    saved_event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
) -> None:
    start_event_request_review(COORDINATOR_ID, "  evr-aaaaaaaa ")

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.UNDER_REVIEW


def test_starting_review_notifies_nobody(
    start_review: StartReview, notifications_of: Callable[[int], list[tuple[Any, ...]]]
) -> None:
    start_review(COORDINATOR_ID)

    for user_id in [2, 3, 4, 5, 7, 9]:
        assert notifications_of(user_id) == []


# --------------------------------------------------------------------------
# AC5 — nobody but the assigned coordinator; only a submitted request
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [EventRequestStatus.SUBMITTED, EventRequestStatus.COMPLETED],
    ids=lambda status: status.value,
)
def test_only_the_assigned_coordinator_may_start_review(
    start_review: StartReview,
    set_status: SetStatus,
    assert_nothing_changed: AssertNothingChanged,
    status: EventRequestStatus,
) -> None:
    """Another coordinator gets the "not yours" 404 whatever the status (ADR-0019)."""
    set_status(status)

    with pytest.raises(NotFoundError) as exc_info:
        start_review(OTHER_COORDINATOR_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(status)


def test_an_unassigned_request_cannot_be_reviewed(
    start_review: StartReview,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    assert_nothing_changed: AssertNothingChanged,
) -> None:
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    with pytest.raises(NotFoundError) as exc_info:
        start_review(COORDINATOR_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(EventRequestStatus.SUBMITTED)


@pytest.mark.parametrize("status", NOT_REVIEWABLE, ids=lambda status: status.value)
def test_a_request_that_is_not_submitted_cannot_be_moved_to_under_review(
    start_review: StartReview,
    set_status: SetStatus,
    assert_nothing_changed: AssertNothingChanged,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    with pytest.raises(RequestNotReviewableError) as exc_info:
        start_review(COORDINATOR_ID)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "request_not_reviewable")
    assert refused.message == NOT_REVIEWABLE_MESSAGE
    assert_nothing_changed(status)


def test_a_draft_is_not_found_by_its_coordinator(
    start_review: StartReview,
    set_status: SetStatus,
    assert_nothing_changed: AssertNothingChanged,
) -> None:
    """Staff never see a draft (ADR-0024): reviewing one is a 404, like no request."""
    set_status(EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError) as exc_info:
        start_review(COORDINATOR_ID)

    assert exc_info.value.status_code == 404
    assert_nothing_changed(EventRequestStatus.DRAFT)


def test_an_unknown_reference_is_404(
    saved_users: list[User], assert_nothing_changed: AssertNothingChanged
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        start_event_request_review(COORDINATOR_ID, "EVR-ZZZZZZZZ")

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(EventRequestStatus.SUBMITTED)
