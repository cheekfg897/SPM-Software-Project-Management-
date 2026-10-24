"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": the exchange shown.

AC4: the clarification exchange is visible on the event record. Every question the
coordinator asked is shown in the order asked, each with the organiser's answer, or
with none while it is outstanding; no other history entry is taken for an answer.
The names are looked up when the record is read, so a removed user shows as ``None``
(as SCRUM-31's decision does, ADR-0028). Both the organiser's and the coordinator's
view of the record show it (ADR-0026).

The service tests run against ``db_session`` with ``saved_users``; the history entries
are written directly with ``record_event_history`` so their times can be pinned out of
insertion order.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest

from app.modules.events.models import EventHistoryKind, EventRequest
from app.modules.events.services import ClarificationAsShown, EventRecord, OrganiserEventRecord

pytestmark = pytest.mark.scrum_32

OpenRecord = Callable[[], EventRecord]
RecordEntry = Callable[..., None]
OpenRecordRoute = Callable[[OrganiserEventRecord], dict[str, Any]]

#: The Event Organiser who owns ``saved_event_request``; ``saved_users`` names them.
ORGANISER_ID = 7
ORGANISER_NAME = "Alice Example"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
COORDINATOR_NAME = "Coordinator Three"
#: A user id no saved user has: someone removed since.
REMOVED_USER_ID = 99

FIRST_QUESTION = "How many of the guests need wheelchair access?"
FIRST_ANSWER = "Four of them."
SECOND_QUESTION = "Will the guests need parking?"
FIRST_ASKED_AT = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
FIRST_ANSWERED_AT = datetime(2026, 9, 15, 2, 30, tzinfo=timezone.utc)
SECOND_ASKED_AT = datetime(2026, 9, 15, 4, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# AC4 — the record shows each question with its answer
# --------------------------------------------------------------------------


def test_the_record_shows_each_question_with_its_answer(
    open_record: OpenRecord, record_entry: RecordEntry
) -> None:
    # Written out of order, so only the times can put them in the order asked.
    record_entry(
        EventHistoryKind.CLARIFICATION_REQUESTED,
        SECOND_ASKED_AT,
        actor_id=COORDINATOR_ID,
        details={"message": SECOND_QUESTION},
    )
    record_entry(
        EventHistoryKind.CLARIFICATION_ANSWERED,
        FIRST_ANSWERED_AT,
        actor_id=ORGANISER_ID,
        details={"response": FIRST_ANSWER},
    )
    record_entry(
        EventHistoryKind.CLARIFICATION_REQUESTED,
        FIRST_ASKED_AT,
        actor_id=COORDINATOR_ID,
        details={"message": FIRST_QUESTION},
    )

    record = open_record()

    assert record.clarifications == (
        ClarificationAsShown(
            message=FIRST_QUESTION,
            requested_by=COORDINATOR_NAME,
            requested_at=FIRST_ASKED_AT,
            response=FIRST_ANSWER,
            answered_by=ORGANISER_NAME,
            answered_at=FIRST_ANSWERED_AT,
        ),
        ClarificationAsShown(
            message=SECOND_QUESTION,
            requested_by=COORDINATOR_NAME,
            requested_at=SECOND_ASKED_AT,
        ),
    )


def test_a_request_with_no_exchange_shows_an_empty_list(
    open_record: OpenRecord, record_entry: RecordEntry
) -> None:
    record_entry(
        EventHistoryKind.REVIEW_STARTED, FIRST_ASKED_AT, actor_id=COORDINATOR_ID, details=None
    )

    record = open_record()

    assert record.clarifications == ()


def test_a_removed_users_name_is_null(open_record: OpenRecord, record_entry: RecordEntry) -> None:
    record_entry(
        EventHistoryKind.CLARIFICATION_REQUESTED,
        FIRST_ASKED_AT,
        actor_id=REMOVED_USER_ID,
        details={"message": FIRST_QUESTION},
    )
    record_entry(
        EventHistoryKind.CLARIFICATION_ANSWERED,
        FIRST_ANSWERED_AT,
        actor_id=REMOVED_USER_ID,
        details={"response": FIRST_ANSWER},
    )

    record = open_record()

    assert record.clarifications == (
        ClarificationAsShown(
            message=FIRST_QUESTION,
            requested_by=None,
            requested_at=FIRST_ASKED_AT,
            response=FIRST_ANSWER,
            answered_by=None,
            answered_at=FIRST_ANSWERED_AT,
        ),
    )


def test_an_entry_with_no_details_is_shown_without_its_text(
    open_record: OpenRecord, record_entry: RecordEntry
) -> None:
    record_entry(
        EventHistoryKind.CLARIFICATION_REQUESTED,
        FIRST_ASKED_AT,
        actor_id=COORDINATOR_ID,
        details=None,
    )
    record_entry(
        EventHistoryKind.CLARIFICATION_ANSWERED,
        FIRST_ANSWERED_AT,
        actor_id=ORGANISER_ID,
        details=None,
    )

    record = open_record()

    assert record.clarifications == (
        ClarificationAsShown(
            message=None,
            requested_by=COORDINATOR_NAME,
            requested_at=FIRST_ASKED_AT,
            response=None,
            answered_by=ORGANISER_NAME,
            answered_at=FIRST_ANSWERED_AT,
        ),
    )


def test_an_answer_with_no_question_before_it_is_ignored(
    open_record: OpenRecord, record_entry: RecordEntry
) -> None:
    record_entry(
        EventHistoryKind.CLARIFICATION_ANSWERED,
        FIRST_ANSWERED_AT,
        actor_id=ORGANISER_ID,
        details={"response": FIRST_ANSWER},
    )

    record = open_record()

    assert record.clarifications == ()


def test_other_history_entries_are_not_taken_for_answers(
    open_record: OpenRecord, record_entry: RecordEntry
) -> None:
    """A request can be reassigned while its question is outstanding (ADR-0029)."""
    record_entry(
        EventHistoryKind.CLARIFICATION_REQUESTED,
        FIRST_ASKED_AT,
        actor_id=COORDINATOR_ID,
        details={"message": FIRST_QUESTION},
    )
    record_entry(
        EventHistoryKind.COORDINATOR_REASSIGNED,
        FIRST_ANSWERED_AT,
        actor_id=COORDINATOR_ID,
        details={
            "previous_coordinator_id": COORDINATOR_ID,
            "previous_coordinator_name": COORDINATOR_NAME,
            "coordinator_id": 9,
            "coordinator_name": "Coordinator Nine",
        },
    )

    record = open_record()

    assert record.clarifications == (
        ClarificationAsShown(
            message=FIRST_QUESTION,
            requested_by=COORDINATOR_NAME,
            requested_at=FIRST_ASKED_AT,
        ),
    )


# --------------------------------------------------------------------------
# AC4 — the record route shows it as ``clarifications``
# --------------------------------------------------------------------------


def test_the_record_route_shows_the_exchange_in_business_time(
    open_record_route: OpenRecordRoute, make_event_request: Callable[..., EventRequest]
) -> None:
    answered = ClarificationAsShown(
        message=FIRST_QUESTION,
        requested_by=COORDINATOR_NAME,
        requested_at=FIRST_ASKED_AT,
        response=FIRST_ANSWER,
        answered_by=ORGANISER_NAME,
        answered_at=FIRST_ANSWERED_AT,
    )
    outstanding = ClarificationAsShown(
        message=SECOND_QUESTION, requested_by=COORDINATOR_NAME, requested_at=SECOND_ASKED_AT
    )
    record = OrganiserEventRecord(
        event_request=make_event_request(),
        coordinator=None,
        clarifications=(answered, outstanding),
    )

    body = open_record_route(record)

    assert body["clarifications"] == [
        {
            "message": FIRST_QUESTION,
            "requested_by": COORDINATOR_NAME,
            "requested_at": "2026-09-15T09:00:00+08:00",
            "response": FIRST_ANSWER,
            "answered_by": ORGANISER_NAME,
            "answered_at": "2026-09-15T10:30:00+08:00",
        },
        {
            "message": SECOND_QUESTION,
            "requested_by": COORDINATOR_NAME,
            "requested_at": "2026-09-15T12:00:00+08:00",
            "response": None,
            "answered_by": None,
            "answered_at": None,
        },
    ]
