"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": asking.

AC1: from under review, the assigned coordinator asks the organiser a question, and
the request goes back to the organiser as ``awaiting_clarification``. AC4: the
question stays visible, as a ``clarification_requested`` history entry holding the
message and who asked, saved in the same commit as the status. Only the request's
own coordinator may ask; anyone else, or a request with no coordinator, gets the same
404 as an unknown reference (ADR-0019). Any status but ``under_review`` is a 409,
including a second question while one is outstanding. The checks run reference,
coordinator, status, then payload (ADR-0029).

Runs against ``db_session`` with ``saved_users`` and ``under_review_request``
(``EVR-AAAAAAAA``, under review, assigned to Event Coordinator 3); the one-commit
test uses ``mock_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CLARIFICATION_NOT_ALLOWED_MESSAGE,
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    ClarificationNotAllowedError,
    EventEdit,
    request_clarification,
)
from tests.events.cases import CLARIFICATION_QUESTION

pytestmark = pytest.mark.scrum_32

AskClarification = Callable[[int, Any], EventRequest]
EditEvent = Callable[[int, dict[str, Any] | None], EventEdit]
SetStatus = Callable[[EventRequestStatus], None]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssertStatusUnchanged = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``under_review_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
QUESTION = {"message": CLARIFICATION_QUESTION}
#: Every status a coordinator can see but ``under_review``, including
#: ``awaiting_clarification``: a second question while one is outstanding. A draft is
#: out of scope here: it is hidden from coordinators altogether (SCRUM-20, ADR-0024).
NOT_UNDER_REVIEW = [
    status
    for status in EventRequestStatus
    if status not in {EventRequestStatus.DRAFT, EventRequestStatus.UNDER_REVIEW}
]


def _assert_not_found(exc_info: pytest.ExceptionInfo[NotFoundError]) -> None:
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


# --------------------------------------------------------------------------
# AC1, AC4 — the assigned coordinator asks, and the question is kept
# --------------------------------------------------------------------------


def test_the_assigned_coordinator_sends_the_request_back_to_the_organiser(
    ask_clarification: AskClarification,
    reload_event_request: ReloadEventRequest,
    under_review_request: EventRequest,
) -> None:
    asked = ask_clarification(COORDINATOR_ID, QUESTION)

    reloaded = reload_event_request(under_review_request.id)
    assert reloaded.status is EventRequestStatus.AWAITING_CLARIFICATION
    assert asked.reference == REFERENCE


def test_the_question_is_recorded_with_who_asked_it(
    ask_clarification: AskClarification,
    history_of: HistoryOf,
    under_review_request: EventRequest,
    db_session: Session,
) -> None:
    before = datetime.now(timezone.utc)

    ask_clarification(COORDINATOR_ID, QUESTION)

    after = datetime.now(timezone.utc)
    assert history_of(under_review_request.id) == [
        (EventHistoryKind.CLARIFICATION_REQUESTED, COORDINATOR_ID, QUESTION)
    ]
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert before <= entry.occurred_at <= after


def test_the_message_is_trimmed(
    ask_clarification: AskClarification, history_of: HistoryOf, under_review_request: EventRequest
) -> None:
    ask_clarification(COORDINATOR_ID, {"message": f"  {CLARIFICATION_QUESTION}\n"})

    assert history_of(under_review_request.id) == [
        (EventHistoryKind.CLARIFICATION_REQUESTED, COORDINATOR_ID, QUESTION)
    ]


def test_the_status_and_the_question_are_saved_in_one_commit(
    mock_session: MagicMock, make_event_request: Callable[..., EventRequest]
) -> None:
    """At the first commit, the status has moved and the entry is already added."""
    event_request = make_event_request(
        status=EventRequestStatus.UNDER_REVIEW, coordinator_id=COORDINATOR_ID
    )
    mock_session.scalar.return_value = event_request
    seen_at_commit: list[tuple[EventRequestStatus, list[tuple[Any, ...]]]] = []

    def note_what_is_saved() -> None:
        added = []
        for call in mock_session.add.call_args_list:
            added.append((call.args[0].kind, call.args[0].details))
        seen_at_commit.append((event_request.status, added))

    mock_session.commit.side_effect = note_what_is_saved

    request_clarification(COORDINATOR_ID, REFERENCE, QUESTION, session=mock_session)

    assert seen_at_commit[:1] == [
        (
            EventRequestStatus.AWAITING_CLARIFICATION,
            [(EventHistoryKind.CLARIFICATION_REQUESTED, QUESTION)],
        )
    ]


def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_users: list[User],
    under_review_request: EventRequest,
    reload_event_request: ReloadEventRequest,
) -> None:
    request_clarification(COORDINATOR_ID, "  evr-aaaaaaaa ", QUESTION)

    reloaded = reload_event_request(under_review_request.id)
    assert reloaded.status is EventRequestStatus.AWAITING_CLARIFICATION


def test_the_coordinator_can_record_an_amendment_while_the_question_is_open(
    edit_event: EditEvent,
    awaiting_clarification_request: EventRequest,
    reload_event_request: ReloadEventRequest,
) -> None:
    """SCRUM-33 lets the coordinator edit; the question stays open (ADR-0101)."""
    edit_event(COORDINATOR_ID, {"description": "Changed"})

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert reloaded.description == "Changed"
    assert reloaded.status is EventRequestStatus.AWAITING_CLARIFICATION


# --------------------------------------------------------------------------
# AC1 — the payload: a question, and nothing else
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        ({}, {"message": ["Missing data for required field."]}),
        ({"message": ""}, {"message": ["Must not be blank."]}),
        ({"message": "   "}, {"message": ["Must not be blank."]}),
        ({"message": None}, {"message": ["Field may not be null."]}),
        ({"message": 5}, {"message": ["Not a valid string."]}),
    ],
    ids=["missing", "empty", "spaces", "null", "a-number"],
)
def test_a_message_is_required(
    ask_clarification: AskClarification,
    assert_status_unchanged: AssertStatusUnchanged,
    payload: dict[str, Any],
    details: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ask_clarification(COORDINATOR_ID, payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == details
    assert_status_unchanged(EventRequestStatus.UNDER_REVIEW)


def test_fields_outside_the_question_are_refused(
    ask_clarification: AskClarification, assert_status_unchanged: AssertStatusUnchanged
) -> None:
    payload = {**QUESTION, "status": "submitted"}

    with pytest.raises(ValidationError) as exc_info:
        ask_clarification(COORDINATOR_ID, payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"status": ["Unknown field."]}
    assert_status_unchanged(EventRequestStatus.UNDER_REVIEW)


def test_the_body_must_be_a_json_object(
    ask_clarification: AskClarification, assert_status_unchanged: AssertStatusUnchanged
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ask_clarification(COORDINATOR_ID, [CLARIFICATION_QUESTION])

    assert exc_info.value.message == "Request body must be a JSON object."
    assert_status_unchanged(EventRequestStatus.UNDER_REVIEW)


# --------------------------------------------------------------------------
# AC1 — only the assigned coordinator, only while under review
# --------------------------------------------------------------------------


def test_only_the_assigned_coordinator_may_ask(
    ask_clarification: AskClarification, assert_status_unchanged: AssertStatusUnchanged
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        ask_clarification(OTHER_COORDINATOR_ID, QUESTION)

    _assert_not_found(exc_info)
    assert_status_unchanged(EventRequestStatus.UNDER_REVIEW)


def test_an_unassigned_request_cannot_be_queried(
    ask_clarification: AskClarification,
    under_review_request: EventRequest,
    save: Callable[..., None],
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    under_review_request.coordinator_id = None
    save(under_review_request)

    with pytest.raises(NotFoundError) as exc_info:
        ask_clarification(COORDINATOR_ID, QUESTION)

    _assert_not_found(exc_info)
    assert_status_unchanged(EventRequestStatus.UNDER_REVIEW)


@pytest.mark.parametrize("status", NOT_UNDER_REVIEW, ids=lambda status: status.value)
def test_clarification_can_only_be_asked_while_under_review(
    ask_clarification: AskClarification,
    set_status: SetStatus,
    assert_status_unchanged: AssertStatusUnchanged,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    with pytest.raises(ClarificationNotAllowedError) as exc_info:
        ask_clarification(COORDINATOR_ID, QUESTION)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "clarification_not_allowed")
    assert refused.message == CLARIFICATION_NOT_ALLOWED_MESSAGE
    assert_status_unchanged(status)


def test_ownership_is_checked_before_status(
    ask_clarification: AskClarification,
    set_status: SetStatus,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    """Another coordinator gets the "not yours" 404 whatever the status (ADR-0019)."""
    set_status(EventRequestStatus.COMPLETED)

    with pytest.raises(NotFoundError) as exc_info:
        ask_clarification(OTHER_COORDINATOR_ID, QUESTION)

    _assert_not_found(exc_info)
    assert_status_unchanged(EventRequestStatus.COMPLETED)


def test_the_status_is_checked_before_the_payload(
    ask_clarification: AskClarification,
    set_status: SetStatus,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    """A request that can't be queried says so, whatever the body (ADR-0029)."""
    set_status(EventRequestStatus.SUBMITTED)

    with pytest.raises(ClarificationNotAllowedError):
        ask_clarification(COORDINATOR_ID, {})

    assert_status_unchanged(EventRequestStatus.SUBMITTED)


def test_a_draft_is_not_found_by_its_coordinator(
    ask_clarification: AskClarification,
    set_status: SetStatus,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    """Staff never see a draft (ADR-0024): asking about one is a 404, like none."""
    set_status(EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError) as exc_info:
        ask_clarification(COORDINATOR_ID, QUESTION)

    assert exc_info.value.status_code == 404
    assert_status_unchanged(EventRequestStatus.DRAFT)


def test_an_unknown_reference_is_404(
    saved_users: list[User],
    under_review_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        request_clarification(COORDINATOR_ID, "EVR-ZZZZZZZZ", QUESTION)

    _assert_not_found(exc_info)
    assert_status_unchanged(EventRequestStatus.UNDER_REVIEW)
