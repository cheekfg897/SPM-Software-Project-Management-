"""Unit tests for SCRUM-32 "Ask the Organiser for clarification": who is told.

AC1: the organiser who submitted the request is told of the coordinator's question,
with a ``clarification_requested`` notification whose ``detail`` is the question.
AC2: the request's current coordinator is told of the answer, with a
``clarification_answered`` notification whose ``detail`` is the response; with no
coordinator to tell, the answer is still saved and the gap is logged (ADR-0029). An
amendment that could affect equipment already requested asks Technical Support to
reassess it, as an edit does (ADR-0025). Nobody else is told, a refused question
notifies nobody, and a failed notification write doesn't fail the saved change
(ADR-0015).

They are SCRUM-39's AC2 evidence too, so they also carry its marker (ADR-0030).

Runs against ``db_session`` with ``saved_users`` and ``EVR-AAAAAAAA`` (organiser
7's, assigned to Event Coordinator 3); the failed-write tests use ``mock_session``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.equipment.models import EquipmentType
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import request_clarification, resubmit_event_request
from app.modules.notifications.models import Notification
from app.modules.notifications.services import NotificationKind
from tests.events.cases import CLARIFICATION_QUESTION, CLARIFICATION_RESPONSE

pytestmark = [pytest.mark.scrum_32, pytest.mark.scrum_39]

AskClarification = Callable[[int, Any], EventRequest]
Resubmit = Callable[[int, Any], EventRequest]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]
ReloadEventRequest = Callable[[int], EventRequest]

REFERENCE = "EVR-AAAAAAAA"
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9
ORGANISER_ID = 7
QUESTION = {"message": CLARIFICATION_QUESTION}
ANSWER = {"response": CLARIFICATION_RESPONSE}
#: What a failed notification write is logged as, for each notification kind.
FAILED_WRITE_LOG = "event_request_notification_failed reference=EVR-AAAAAAAA kind={kind}"


def _lose_the_notification_write(mock_session: MagicMock) -> None:
    """Let the change's own commit succeed, then fail the notifications' commit."""
    lost_connection = OperationalError("INSERT INTO notifications ...", {}, Exception("gone"))
    mock_session.commit.side_effect = [None, lost_connection]


# --------------------------------------------------------------------------
# AC1 — the organiser is told of the question, with its text
# --------------------------------------------------------------------------


def test_the_organiser_is_told_of_the_question_with_its_text(
    ask_clarification: AskClarification, detailed_notifications_of: DetailedNotificationsOf
) -> None:
    ask_clarification(COORDINATOR_ID, QUESTION)

    assert detailed_notifications_of(ORGANISER_ID) == [
        (REFERENCE, NotificationKind.CLARIFICATION_REQUESTED, CLARIFICATION_QUESTION)
    ]


@pytest.mark.parametrize(
    "user_id",
    [2, 3, 4, 5, 8, 9],
    ids=[
        "technical-support-2",
        "the-asking-coordinator",
        "venue-staff",
        "technical-support-5",
        "a-colleague-in-the-same-organisation",
        "another-coordinator",
    ],
)
def test_nobody_else_is_told_of_the_question(
    ask_clarification: AskClarification,
    detailed_notifications_of: DetailedNotificationsOf,
    other_organisers: list[User],
    user_id: int,
) -> None:
    """Only the organiser who submitted it is told, not their whole organisation."""
    ask_clarification(COORDINATOR_ID, QUESTION)

    assert detailed_notifications_of(user_id) == []


def test_a_refused_question_notifies_nobody(
    ask_clarification: AskClarification, db_session: Session
) -> None:
    with pytest.raises(ValidationError):
        ask_clarification(COORDINATOR_ID, {})

    assert db_session.scalars(select(Notification)).all() == []


# --------------------------------------------------------------------------
# AC2 — the current coordinator is told of the answer, with its text
# --------------------------------------------------------------------------


def test_the_coordinator_is_told_of_the_answer_with_its_text(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    resubmit(ORGANISER_ID, ANSWER)

    assert detailed_notifications_of(COORDINATOR_ID) == [
        (REFERENCE, NotificationKind.CLARIFICATION_ANSWERED, CLARIFICATION_RESPONSE)
    ]


def test_the_answer_goes_to_the_current_coordinator_after_a_reassignment(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    save: Callable[..., None],
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    """Whoever holds the request when the answer comes back is told, not who asked."""
    awaiting_clarification_request.coordinator_id = OTHER_COORDINATOR_ID
    save(awaiting_clarification_request)

    resubmit(ORGANISER_ID, ANSWER)

    assert detailed_notifications_of(OTHER_COORDINATOR_ID) == [
        (REFERENCE, NotificationKind.CLARIFICATION_ANSWERED, CLARIFICATION_RESPONSE)
    ]
    assert detailed_notifications_of(COORDINATOR_ID) == []


@pytest.mark.parametrize(
    "user_id",
    [2, 4, 5, 7, 8, 9],
    ids=[
        "technical-support-2",
        "venue-staff",
        "technical-support-5",
        "the-answering-organiser",
        "a-colleague-in-the-same-organisation",
        "another-coordinator",
    ],
)
def test_nobody_else_is_told_of_the_answer(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    detailed_notifications_of: DetailedNotificationsOf,
    other_organisers: list[User],
    user_id: int,
) -> None:
    resubmit(ORGANISER_ID, ANSWER)

    assert detailed_notifications_of(user_id) == []


def test_a_significant_amendment_asks_technical_support_to_reassess_the_equipment(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    equipment_type: EquipmentType,
    make_equipment_line: Callable[..., EventEquipmentLine],
    save: Callable[..., None],
    detailed_notifications_of: DetailedNotificationsOf,
) -> None:
    save(make_equipment_line(awaiting_clarification_request, equipment_type))

    resubmit(ORGANISER_ID, {**ANSWER, "expected_attendance": 300})

    for technical_support_id in [2, 5]:
        assert detailed_notifications_of(technical_support_id) == [
            (REFERENCE, NotificationKind.SIGNIFICANT_CHANGE, None)
        ]


def test_an_answer_with_no_coordinator_to_tell_is_logged(
    resubmit: Resubmit,
    awaiting_clarification_request: EventRequest,
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The answer is still saved: refusing it would leave the organiser stuck."""
    awaiting_clarification_request.coordinator_id = None
    save(awaiting_clarification_request)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        resubmit(ORGANISER_ID, ANSWER)

    reloaded = reload_event_request(awaiting_clarification_request.id)
    assert reloaded.status is EventRequestStatus.UNDER_REVIEW
    assert [record.getMessage() for record in caplog.records] == [
        "event_request_unassigned reference=EVR-AAAAAAAA"
    ]


# --------------------------------------------------------------------------
# ADR-0015 — a failed notification write doesn't fail the saved change
# --------------------------------------------------------------------------


def test_a_failed_notification_write_still_returns_the_queried_request(
    mock_session: MagicMock,
    make_event_request: Callable[..., EventRequest],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The question is committed first; failing its reply would invite a retry."""
    mock_session.scalar.return_value = make_event_request(
        status=EventRequestStatus.UNDER_REVIEW, coordinator_id=COORDINATOR_ID
    )
    _lose_the_notification_write(mock_session)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        asked = request_clarification(COORDINATOR_ID, REFERENCE, QUESTION, session=mock_session)

    assert asked.status is EventRequestStatus.AWAITING_CLARIFICATION
    assert mock_session.commit.call_count == 2
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        FAILED_WRITE_LOG.format(kind="clarification_requested")
    ]


def test_a_failed_notification_write_still_returns_the_resubmitted_request(
    mock_session: MagicMock,
    organiser_is_found: None,
    make_event_request: Callable[..., EventRequest],
    today: date,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The answer is committed first; failing its reply would invite a retry."""
    mock_session.scalar.return_value = make_event_request(
        status=EventRequestStatus.AWAITING_CLARIFICATION, coordinator_id=COORDINATOR_ID
    )
    _lose_the_notification_write(mock_session)

    with caplog.at_level(logging.WARNING, logger="connectsphere.events"):
        resubmitted = resubmit_event_request(
            ORGANISER_ID, REFERENCE, ANSWER, session=mock_session, today=today
        )

    assert resubmitted.status is EventRequestStatus.UNDER_REVIEW
    assert mock_session.commit.call_count == 2
    mock_session.rollback.assert_called_once()
    assert [record.getMessage() for record in caplog.records] == [
        FAILED_WRITE_LOG.format(kind="clarification_answered")
    ]
