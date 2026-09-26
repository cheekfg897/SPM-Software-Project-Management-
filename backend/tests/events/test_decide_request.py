"""Unit tests for SCRUM-31 "Review and decide a submitted request": deciding.

AC1: a decision is the assigned coordinator's ruling, approved or rejected. AC4:
approving moves the request to ``approved``; rejecting moves it to ``rejected`` and
needs a reason. A request may be decided straight from ``submitted`` or from
``under_review`` (ADR-0028). AC5: nobody but the assigned coordinator may decide;
another coordinator's request, or one with no coordinator, gets the same 404 as an
unknown reference. AC8: every decision is in the event history with its reason, the
coordinator and the time, saved in the same commit as the status. A request past
review is a 409, checked before the payload.

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

from app.common.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import EventHistoryKind, EventRequest, EventRequestStatus
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_DECIDABLE_MESSAGE,
    REASON_REQUIRED_MESSAGE,
    RequestNotDecidableError,
    decide_event_request,
    list_event_history,
)
from tests.events.cases import APPROVAL_REASON, REJECTION_REASON

pytestmark = pytest.mark.scrum_31

Decide = Callable[..., EventRequest]
StartReview = Callable[[int], EventRequest]
SetStatus = Callable[[EventRequestStatus], None]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssertStatusUnchanged = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
ORGANISER_ID = 7
#: The two statuses a first decision may be made from (ADR-0028).
AWAITING_DECISION = [EventRequestStatus.SUBMITTED, EventRequestStatus.UNDER_REVIEW]
#: Statuses past review. A draft is out of scope here: it is hidden from coordinators
#: altogether (SCRUM-20, ADR-0024).
PAST_REVIEW = [
    EventRequestStatus.CONFIRMED,
    EventRequestStatus.COMPLETED,
    EventRequestStatus.CANCELLED,
]
OUTCOME_MESSAGE = "Outcome must be approved or rejected."


def _assert_payload_refused(
    exc_info: pytest.ExceptionInfo[ValidationError], details: dict[str, list[str]]
) -> None:
    assert exc_info.value.status_code == 400
    assert exc_info.value.details == details


# --------------------------------------------------------------------------
# AC1, AC4 — approving and rejecting move the request, from submitted or under review
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", AWAITING_DECISION, ids=lambda status: status.value)
def test_approving_moves_the_request_to_approved(
    decide: Decide,
    set_status: SetStatus,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    decided = decide(COORDINATOR_ID, "approved")

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.APPROVED
    assert decided.reference == REFERENCE


@pytest.mark.parametrize("status", AWAITING_DECISION, ids=lambda status: status.value)
def test_rejecting_with_a_reason_moves_the_request_to_rejected(
    decide: Decide,
    set_status: SetStatus,
    reload_event_request: ReloadEventRequest,
    saved_event_request: EventRequest,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    decide(COORDINATOR_ID, "rejected", REJECTION_REASON)

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.REJECTED


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        ({"outcome": "rejected"}, {"reason": [REASON_REQUIRED_MESSAGE]}),
        ({"outcome": "rejected", "reason": None}, {"reason": [REASON_REQUIRED_MESSAGE]}),
        ({"outcome": "rejected", "reason": ""}, {"reason": ["Must not be blank."]}),
        ({"outcome": "rejected", "reason": "   "}, {"reason": ["Must not be blank."]}),
    ],
    ids=["omitted", "null", "empty", "only-spaces"],
)
def test_rejecting_requires_a_reason(
    saved_users: list[User],
    saved_event_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    payload: dict[str, Any],
    details: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        decide_event_request(COORDINATOR_ID, REFERENCE, payload)

    _assert_payload_refused(exc_info, details)
    assert_status_unchanged(EventRequestStatus.SUBMITTED)


def test_a_first_approval_needs_no_reason(
    decide: Decide, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    decide(COORDINATOR_ID, "approved")

    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.DECISION_RECORDED,
            COORDINATOR_ID,
            {"outcome": "approved", "reason": None},
        )
    ]


def test_an_approval_may_carry_a_reason_which_is_trimmed(
    decide: Decide, history_of: HistoryOf, saved_event_request: EventRequest
) -> None:
    decide(COORDINATOR_ID, "approved", f"  {APPROVAL_REASON}  ")

    assert history_of(saved_event_request.id) == [
        (
            EventHistoryKind.DECISION_RECORDED,
            COORDINATOR_ID,
            {"outcome": "approved", "reason": APPROVAL_REASON},
        )
    ]


def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_users: list[User],
    saved_event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
) -> None:
    decide_event_request(COORDINATOR_ID, "  evr-aaaaaaaa ", {"outcome": "approved"})

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.APPROVED


# --------------------------------------------------------------------------
# AC8 — every decision is in the history with its reason, coordinator and time
# --------------------------------------------------------------------------


def test_every_decision_stays_in_the_history_with_its_reason_coordinator_and_time(
    start_review: StartReview, decide: Decide
) -> None:
    start_review(COORDINATOR_ID)
    before = datetime.now(timezone.utc)

    decide(COORDINATOR_ID, "rejected", REJECTION_REASON)

    after = datetime.now(timezone.utc)
    history = list_event_history(ORGANISER_ID, REFERENCE, viewer_role=Role.EVENT_ORGANISER)
    shown = [(entry.kind, entry.actor_name, entry.details) for entry in history]
    assert shown == [
        (EventHistoryKind.REVIEW_STARTED, "Coordinator Three", {}),
        (
            EventHistoryKind.DECISION_RECORDED,
            "Coordinator Three",
            {"outcome": "rejected", "reason": REJECTION_REASON},
        ),
    ]
    assert before <= history[1].occurred_at <= after


def test_the_status_and_the_decision_are_saved_in_one_commit(
    mock_session: MagicMock, make_event_request: Callable[..., EventRequest]
) -> None:
    """At the first commit, the status has moved and the entry is already added."""
    event_request = make_event_request(coordinator_id=COORDINATOR_ID)
    mock_session.scalar.return_value = event_request
    seen_at_commit: list[tuple[EventRequestStatus, list[tuple[Any, ...]]]] = []

    def note_what_is_saved() -> None:
        added = []
        for call in mock_session.add.call_args_list:
            added.append((call.args[0].kind, call.args[0].details))
        seen_at_commit.append((event_request.status, added))

    mock_session.commit.side_effect = note_what_is_saved

    decide_event_request(COORDINATOR_ID, REFERENCE, {"outcome": "approved"}, session=mock_session)

    assert seen_at_commit[:1] == [
        (
            EventRequestStatus.APPROVED,
            [(EventHistoryKind.DECISION_RECORDED, {"outcome": "approved", "reason": None})],
        )
    ]


# --------------------------------------------------------------------------
# AC1 — the payload: an outcome, a reason, and nothing else
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        ({}, {"outcome": ["Missing data for required field."]}),
        ({"outcome": "maybe"}, {"outcome": [OUTCOME_MESSAGE]}),
        ({"outcome": "under_review"}, {"outcome": [OUTCOME_MESSAGE]}),
        ({"outcome": 1}, {"outcome": [OUTCOME_MESSAGE]}),
    ],
    ids=["missing", "unknown-word", "a-status", "a-number"],
)
def test_the_outcome_must_be_approved_or_rejected(
    saved_users: list[User],
    saved_event_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    payload: dict[str, Any],
    details: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        decide_event_request(COORDINATOR_ID, REFERENCE, payload)

    _assert_payload_refused(exc_info, details)
    assert_status_unchanged(EventRequestStatus.SUBMITTED)


def test_fields_outside_the_decision_are_refused(
    saved_users: list[User],
    saved_event_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    payload = {"outcome": "approved", "status": "confirmed"}

    with pytest.raises(ValidationError) as exc_info:
        decide_event_request(COORDINATOR_ID, REFERENCE, payload)

    _assert_payload_refused(exc_info, {"status": ["Unknown field."]})
    assert_status_unchanged(EventRequestStatus.SUBMITTED)


def test_the_body_must_be_a_json_object(
    saved_users: list[User],
    saved_event_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        decide_event_request(COORDINATOR_ID, REFERENCE, ["approved"])  # type: ignore[arg-type]

    assert exc_info.value.message == "Request body must be a JSON object."
    assert_status_unchanged(EventRequestStatus.SUBMITTED)


# --------------------------------------------------------------------------
# AC5 — nobody but the assigned coordinator; nothing past review
# --------------------------------------------------------------------------


def test_only_the_assigned_coordinator_may_decide(
    decide: Decide, assert_status_unchanged: AssertStatusUnchanged
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        decide(OTHER_COORDINATOR_ID, "approved")

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_status_unchanged(EventRequestStatus.SUBMITTED)


def test_an_unassigned_request_cannot_be_decided(
    decide: Decide,
    saved_event_request: EventRequest,
    save: Callable[..., None],
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    saved_event_request.coordinator_id = None
    save(saved_event_request)

    with pytest.raises(NotFoundError) as exc_info:
        decide(COORDINATOR_ID, "approved")

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_status_unchanged(EventRequestStatus.SUBMITTED)


@pytest.mark.parametrize("status", PAST_REVIEW, ids=lambda status: status.value)
def test_a_request_past_review_cannot_be_decided(
    decide: Decide,
    set_status: SetStatus,
    assert_status_unchanged: AssertStatusUnchanged,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    with pytest.raises(RequestNotDecidableError) as exc_info:
        decide(COORDINATOR_ID, "approved")

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "request_not_decidable")
    assert refused.message == NOT_DECIDABLE_MESSAGE
    assert_status_unchanged(status)


def test_the_status_is_checked_before_the_payload(
    saved_users: list[User],
    set_status: SetStatus,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    """A request that can't be decided says so, whatever the body (ADR-0028)."""
    set_status(EventRequestStatus.CONFIRMED)

    with pytest.raises(RequestNotDecidableError):
        decide_event_request(COORDINATOR_ID, REFERENCE, {})

    assert_status_unchanged(EventRequestStatus.CONFIRMED)


def test_a_draft_is_not_found_by_its_coordinator(
    decide: Decide, set_status: SetStatus, assert_status_unchanged: AssertStatusUnchanged
) -> None:
    """Staff never see a draft (ADR-0024): deciding one is a 404, like no request."""
    set_status(EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError) as exc_info:
        decide(COORDINATOR_ID, "approved")

    assert exc_info.value.status_code == 404
    assert_status_unchanged(EventRequestStatus.DRAFT)


def test_an_unknown_reference_is_404(
    saved_users: list[User],
    saved_event_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        decide_event_request(COORDINATOR_ID, "EVR-ZZZZZZZZ", {"outcome": "approved"})

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_status_unchanged(EventRequestStatus.SUBMITTED)
