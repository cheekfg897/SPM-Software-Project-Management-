"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": approval waits.

AC3: while a clarification request is outstanding, the coordinator can't approve
the request: a 409 ``clarification_outstanding``, checked after the payload. They may
still reject it, and once the organiser has answered they may approve it. The
coordinator can't pull the request back to under review themselves either
(ADR-0029).

Runs against ``db_session`` with ``saved_users`` and ``EVR-AAAAAAAA`` (organiser
7's, assigned to Event Coordinator 3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import ValidationError
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    CLARIFICATION_OUTSTANDING_MESSAGE,
    NOT_REVIEWABLE_MESSAGE,
    ClarificationOutstandingError,
    RequestNotReviewableError,
)
from tests.events.cases import CLARIFICATION_QUESTION, CLARIFICATION_RESPONSE, REJECTION_REASON

pytestmark = pytest.mark.scrum_32

Decide = Callable[..., EventRequest]
StartReview = Callable[[int], EventRequest]
AskClarification = Callable[[int, Any], EventRequest]
Resubmit = Callable[[int, Any], EventRequest]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssertStatusUnchanged = Callable[[EventRequestStatus], None]

COORDINATOR_ID = 3
ORGANISER_ID = 7


# --------------------------------------------------------------------------
# AC3 — no approval while the organiser's answer is outstanding
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason", [None, "The brief is clear enough."], ids=["no-reason", "a-reason"]
)
def test_approval_is_refused_while_a_clarification_request_is_outstanding(
    decide: Decide,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    reason: str | None,
) -> None:
    with pytest.raises(ClarificationOutstandingError) as exc_info:
        decide(COORDINATOR_ID, "approved", reason)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "clarification_outstanding")
    assert refused.message == CLARIFICATION_OUTSTANDING_MESSAGE
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)


def test_a_request_can_still_be_rejected_while_a_clarification_request_is_outstanding(
    decide: Decide,
    awaiting_clarification_request: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    decide(COORDINATOR_ID, "rejected", REJECTION_REASON)

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert reloaded.status is EventRequestStatus.REJECTED
    assert history_of(awaiting_clarification_request.id) == [
        (
            EventHistoryKind.DECISION_RECORDED,
            COORDINATOR_ID,
            {"outcome": "rejected", "reason": REJECTION_REASON},
        )
    ]


def test_the_outstanding_check_comes_after_the_payload_check(
    decide: Decide,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    """A malformed body is a 400 even while the answer is outstanding (ADR-0029)."""
    with pytest.raises(ValidationError) as exc_info:
        decide(COORDINATOR_ID, "maybe")

    assert exc_info.value.details == {"outcome": ["Outcome must be approved or rejected."]}
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)


def test_approval_is_allowed_once_the_organiser_has_answered(
    ask_clarification: AskClarification,
    resubmit: Resubmit,
    decide: Decide,
    reload_event_request: ReloadEventRequest,
    under_review_request: EventRequest,
) -> None:
    ask_clarification(COORDINATOR_ID, {"message": CLARIFICATION_QUESTION})
    resubmit(ORGANISER_ID, {"response": CLARIFICATION_RESPONSE})

    decide(COORDINATOR_ID, "approved")

    reloaded = reload_event_request(under_review_request.id)
    assert reloaded.status is EventRequestStatus.APPROVED


def test_the_coordinator_cannot_pull_the_request_back_to_under_review_themselves(
    start_review: StartReview,
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    """Only the organiser's answer returns it to review (ADR-0029)."""
    with pytest.raises(RequestNotReviewableError) as exc_info:
        start_review(COORDINATOR_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == NOT_REVIEWABLE_MESSAGE
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)
