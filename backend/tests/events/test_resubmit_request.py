"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": resubmitting.

AC2: an organiser answers the coordinator's question, amends the request if they
wish, and resubmits it; it goes back to ``under_review``. Any organiser of the
request's client organisation may (SCRUM-7, ADR-0029). Each amended field is a
``field_changed`` history entry by the organiser, and the answer a
``clarification_answered`` entry holding the response, all at one instant and in the
same commit as the status (AC4). Only a request awaiting clarification can be
resubmitted: anything else is a 409, checked before the payload. The payload rules
are in ``test_resubmit_request_validation.py``.

Runs against ``db_session`` with ``saved_users`` and ``awaiting_clarification_request``
(``EVR-AAAAAAAA``, organiser 7's, filed under client organisation 3, proposed
2026-10-15 09:00-17:00 for 250, assigned to Event Coordinator 3); the one-commit
test uses ``mock_session``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.events.models import (
    EventHistoryEntry,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    EVENT_REQUEST_NOT_FOUND_MESSAGE,
    NOT_AWAITING_CLARIFICATION_MESSAGE,
    OrganiserWithoutOrganisationError,
    RequestNotAwaitingClarificationError,
    list_event_history,
    resubmit_event_request,
)
from tests.events.cases import CLARIFICATION_QUESTION, CLARIFICATION_RESPONSE

pytestmark = pytest.mark.scrum_32

Resubmit = Callable[[int, Any], EventRequest]
AskClarification = Callable[[int, Any], EventRequest]
SetStatus = Callable[[EventRequestStatus], None]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
AssertStatusUnchanged = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
#: From ``other_organisers``: a colleague in organisation 3, an organiser of
#: organisation 4, and one linked to no organisation.
COLLEAGUE_ID = 8
OTHER_ORGANISATIONS_ORGANISER_ID = 6
UNLINKED_ORGANISER_ID = 10
COORDINATOR_ID = 3
ANSWER = {"response": CLARIFICATION_RESPONSE}
ANSWERED = (EventHistoryKind.CLARIFICATION_ANSWERED, ORGANISER_ID, ANSWER)
#: Every status but ``awaiting_clarification``, a draft included: the organiser can
#: see their own draft, so it is refused rather than not found.
NOT_AWAITING_CLARIFICATION = [
    status
    for status in EventRequestStatus
    if status is not EventRequestStatus.AWAITING_CLARIFICATION
]


def _field_changed(
    field: str, previous_value: Any, new_value: Any, significant: bool
) -> tuple[EventHistoryKind, int, dict[str, Any]]:
    """A ``field_changed`` entry by the organiser, as ``history_of`` reads it back."""
    details = {
        "field": field,
        "previous_value": previous_value,
        "new_value": new_value,
        "significant": significant,
    }
    return (EventHistoryKind.FIELD_CHANGED, ORGANISER_ID, details)


def _assert_not_found(exc_info: pytest.ExceptionInfo[NotFoundError]) -> None:
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE


# --------------------------------------------------------------------------
# AC2 — the organiser answers, and the request goes back to under review
# --------------------------------------------------------------------------


def test_the_organiser_answers_and_the_request_returns_to_under_review(
    resubmit: Resubmit,
    reload_event_request: ReloadEventRequest,
    awaiting_clarification_request: EventRequest,
) -> None:
    resubmitted = resubmit(ORGANISER_ID, ANSWER)

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert reloaded.status is EventRequestStatus.UNDER_REVIEW
    assert resubmitted.reference == REFERENCE


def test_the_answer_is_recorded_with_who_answered(
    resubmit: Resubmit,
    history_of: HistoryOf,
    awaiting_clarification_request: EventRequest,
    db_session: Session,
) -> None:
    before = datetime.now(timezone.utc)

    resubmit(ORGANISER_ID, ANSWER)

    after = datetime.now(timezone.utc)
    assert history_of(awaiting_clarification_request.id) == [ANSWERED]
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert before <= entry.occurred_at <= after


def test_amended_fields_are_saved_and_each_change_is_in_the_history(
    resubmit: Resubmit,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    awaiting_clarification_request: EventRequest,
) -> None:
    payload = {**ANSWER, "accessibility_needs": "A ramp to the stage", "expected_attendance": 300}

    resubmit(ORGANISER_ID, payload)

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert (reloaded.accessibility_needs, reloaded.expected_attendance) == (
        "A ramp to the stage",
        300,
    )
    assert history_of(awaiting_clarification_request.id) == [
        _field_changed("expected_attendance", 250, 300, True),
        _field_changed("accessibility_needs", None, "A ramp to the stage", False),
        ANSWERED,
    ]


def test_the_amendments_and_the_answer_share_one_instant(
    resubmit: Resubmit, awaiting_clarification_request: EventRequest, db_session: Session
) -> None:
    resubmit(ORGANISER_ID, {**ANSWER, "expected_attendance": 300, "purpose": "Partner day"})

    instants = set(db_session.scalars(select(EventHistoryEntry.occurred_at)))
    assert len(instants) == 1


def test_a_value_equal_to_the_current_one_is_not_a_change(
    resubmit: Resubmit, history_of: HistoryOf, awaiting_clarification_request: EventRequest
) -> None:
    resubmit(ORGANISER_ID, {**ANSWER, "expected_attendance": 250})

    assert history_of(awaiting_clarification_request.id) == [ANSWERED]


def test_a_colleague_of_the_organiser_may_answer(
    resubmit: Resubmit,
    other_organisers: list[User],
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    awaiting_clarification_request: EventRequest,
) -> None:
    resubmit(COLLEAGUE_ID, ANSWER)

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert reloaded.status is EventRequestStatus.UNDER_REVIEW
    assert history_of(awaiting_clarification_request.id) == [
        (EventHistoryKind.CLARIFICATION_ANSWERED, COLLEAGUE_ID, ANSWER)
    ]


def test_the_status_amendments_and_answer_are_saved_in_one_commit(
    mock_session: MagicMock,
    organiser_is_found: None,
    make_event_request: Callable[..., EventRequest],
    today: date,
) -> None:
    """At the first commit, the status has moved and every entry is already added."""
    event_request = make_event_request(
        status=EventRequestStatus.AWAITING_CLARIFICATION, coordinator_id=COORDINATOR_ID
    )
    mock_session.scalar.return_value = event_request
    seen_at_commit: list[tuple[EventRequestStatus, list[tuple[Any, ...]]]] = []

    def note_what_is_saved() -> None:
        added = []
        for call in mock_session.add.call_args_list:
            added.append((call.args[0].kind, call.args[0].actor_id))
        seen_at_commit.append((event_request.status, added))

    mock_session.commit.side_effect = note_what_is_saved

    resubmit_event_request(
        ORGANISER_ID,
        REFERENCE,
        {**ANSWER, "expected_attendance": 300},
        session=mock_session,
        today=today,
    )

    assert seen_at_commit[:1] == [
        (
            EventRequestStatus.UNDER_REVIEW,
            [
                (EventHistoryKind.FIELD_CHANGED, ORGANISER_ID),
                (EventHistoryKind.CLARIFICATION_ANSWERED, ORGANISER_ID),
            ],
        )
    ]


def test_the_reference_ignores_case_and_surrounding_spaces(
    saved_users: list[User],
    awaiting_clarification_request: EventRequest,
    reload_event_request: ReloadEventRequest,
    today: date,
) -> None:
    resubmit_event_request(ORGANISER_ID, "  evr-aaaaaaaa ", ANSWER, today=today)

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert reloaded.status is EventRequestStatus.UNDER_REVIEW


# --------------------------------------------------------------------------
# AC4 — the question and the answer both stay visible
# --------------------------------------------------------------------------


def test_the_exchange_is_shown_in_the_history_to_the_organiser_and_to_staff(
    ask_clarification: AskClarification, resubmit: Resubmit
) -> None:
    ask_clarification(COORDINATOR_ID, {"message": CLARIFICATION_QUESTION})
    resubmit(ORGANISER_ID, ANSWER)

    expected = [
        (
            EventHistoryKind.CLARIFICATION_REQUESTED,
            "Coordinator Three",
            {"message": CLARIFICATION_QUESTION},
        ),
        (EventHistoryKind.CLARIFICATION_ANSWERED, "Alice Example", ANSWER),
    ]
    for viewer_id, viewer_role in [
        (ORGANISER_ID, Role.EVENT_ORGANISER),
        (COORDINATOR_ID, Role.EVENT_COORDINATOR),
    ]:
        history = list_event_history(viewer_id, REFERENCE, viewer_role=viewer_role)
        shown = [(entry.kind, entry.actor_name, entry.details) for entry in history]
        assert shown == expected


# --------------------------------------------------------------------------
# AC2 — only a request awaiting clarification, only the organisation's organisers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NOT_AWAITING_CLARIFICATION, ids=lambda status: status.value)
def test_only_a_request_awaiting_clarification_can_be_resubmitted(
    resubmit: Resubmit,
    set_status: SetStatus,
    assert_status_unchanged: AssertStatusUnchanged,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    with pytest.raises(RequestNotAwaitingClarificationError) as exc_info:
        resubmit(ORGANISER_ID, ANSWER)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "request_not_awaiting_clarification")
    assert refused.message == NOT_AWAITING_CLARIFICATION_MESSAGE
    assert_status_unchanged(status)


def test_another_organisations_request_is_not_found(
    resubmit: Resubmit,
    other_organisers: list[User],
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        resubmit(OTHER_ORGANISATIONS_ORGANISER_ID, ANSWER)

    _assert_not_found(exc_info)
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)


def test_an_organiser_without_an_organisation_is_refused(
    resubmit: Resubmit,
    other_organisers: list[User],
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
) -> None:
    with pytest.raises(OrganiserWithoutOrganisationError) as exc_info:
        resubmit(UNLINKED_ORGANISER_ID, ANSWER)

    assert exc_info.value.status_code == 403
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)


def test_an_unknown_reference_is_404(
    saved_users: list[User],
    awaiting_clarification_request: EventRequest,
    assert_status_unchanged: AssertStatusUnchanged,
    today: date,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        resubmit_event_request(ORGANISER_ID, "EVR-ZZZZZZZZ", ANSWER, today=today)

    _assert_not_found(exc_info)
    assert_status_unchanged(EventRequestStatus.AWAITING_CLARIFICATION)


def test_the_status_is_checked_before_the_payload(
    resubmit: Resubmit, set_status: SetStatus, assert_status_unchanged: AssertStatusUnchanged
) -> None:
    """A request that can't be resubmitted says so, whatever the body (ADR-0029)."""
    set_status(EventRequestStatus.UNDER_REVIEW)

    with pytest.raises(RequestNotAwaitingClarificationError):
        resubmit(ORGANISER_ID, {})

    assert_status_unchanged(EventRequestStatus.UNDER_REVIEW)
