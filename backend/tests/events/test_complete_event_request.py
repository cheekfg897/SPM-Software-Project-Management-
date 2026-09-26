"""Unit tests for SCRUM-68 "Mark an event as completed after it has taken place".

AC1: the assigned coordinator can mark a confirmed event completed once its end
(``end_date`` + ``end_time``, a wall-clock time in business time, ADR-0002) has
passed. AC2: before then it is refused. AC3: a cancelled, rejected or otherwise
unconfirmed event can't be completed; a draft is not found at all (ADR-0024).
AC4: a completed event can no longer be edited (SCRUM-33's rule, ADR-0025); the
registrations half waits for SCRUM-52. AC5: completing writes an ``event_completed``
history entry naming who did it and when, in the same commit as the status (ADR-0027).
A refusal changes nothing.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3, 2026-10-15 09:00-17:00), so
lookups are real SQL; the one-commit test uses ``mock_session``. Every call pins
``now``, since that event is still in the future on the real clock, except the one
test of the default, which uses an event in 2020.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

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
    NOT_CONFIRMED_MESSAGE,
    NOT_EDITABLE_MESSAGE,
    NOT_YET_ENDED_MESSAGE,
    HistoryEntryAsShown,
    RequestNotCompletableError,
    RequestNotEditableError,
    complete_event_request,
    list_event_history,
    update_event_request,
)
from tests.events.cases import NON_DRAFT_STATUSES

pytestmark = pytest.mark.scrum_68

Complete = Callable[[int, datetime], EventRequest]
AssertNothingChanged = Callable[[EventRequestStatus], None]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
ReloadEventRequest = Callable[[int], EventRequest]
SetStatus = Callable[[EventRequestStatus], None]

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
OTHER_COORDINATOR_ID = 9

SINGAPORE = ZoneInfo("Asia/Singapore")
#: When ``saved_event_request`` ends: 2026-10-15 17:00 business time.
ENDS_AT = datetime(2026, 10, 15, 17, 0, tzinfo=SINGAPORE)
JUST_BEFORE_THE_END = ENDS_AT - timedelta(seconds=1)
AFTER_THE_END = ENDS_AT + timedelta(hours=1)

NOT_CONFIRMED_STATUSES = [
    status for status in NON_DRAFT_STATUSES if status is not EventRequestStatus.CONFIRMED
]


def _assert_not_completable(refused: RequestNotCompletableError, message: str) -> None:
    assert (refused.status_code, refused.error_code) == (409, "request_not_completable")
    assert refused.message == message


@pytest.fixture()
def confirmed_event_request(
    set_status: SetStatus, saved_event_request: EventRequest
) -> EventRequest:
    """``saved_event_request``, moved to ``confirmed``."""
    set_status(EventRequestStatus.CONFIRMED)
    return saved_event_request


@pytest.fixture()
def complete(saved_users: list[User], saved_event_request: EventRequest) -> Complete:
    """Complete ``saved_event_request`` as ``actor_id`` at the instant ``now``."""

    def _complete(actor_id: int, now: datetime) -> EventRequest:
        return complete_event_request(actor_id, REFERENCE, now=now)

    return _complete


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
# AC1 — a confirmed event that has ended is marked completed
# --------------------------------------------------------------------------


def test_a_confirmed_event_that_has_ended_is_completed(
    complete: Complete,
    confirmed_event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
) -> None:
    completed = complete(COORDINATOR_ID, AFTER_THE_END)

    assert completed is confirmed_event_request
    reloaded = reload_event_request(confirmed_event_request.id)
    assert reloaded.status is EventRequestStatus.COMPLETED
    assert history_of(confirmed_event_request.id) == [
        (EventHistoryKind.EVENT_COMPLETED, COORDINATOR_ID, None)
    ]


def test_the_end_instant_itself_counts_as_passed(
    complete: Complete,
    confirmed_event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
) -> None:
    """17:00 is business time: read as UTC, it would still be eight hours away."""
    complete(COORDINATOR_ID, ENDS_AT)

    reloaded = reload_event_request(confirmed_event_request.id)
    assert reloaded.status is EventRequestStatus.COMPLETED


# --------------------------------------------------------------------------
# AC2 — an event that hasn't ended yet can't be completed
# --------------------------------------------------------------------------


def test_an_event_that_has_not_ended_is_refused(
    complete: Complete,
    confirmed_event_request: EventRequest,
    assert_nothing_changed: AssertNothingChanged,
) -> None:
    with pytest.raises(RequestNotCompletableError) as exc_info:
        complete(COORDINATOR_ID, JUST_BEFORE_THE_END)

    _assert_not_completable(exc_info.value, NOT_YET_ENDED_MESSAGE)
    assert_nothing_changed(EventRequestStatus.CONFIRMED)


def test_the_end_is_the_end_date_not_the_proposed_date(
    complete: Complete,
    saved_event_request: EventRequest,
    set_status: SetStatus,
    assert_nothing_changed: AssertNothingChanged,
) -> None:
    """A two-day event hasn't ended at 17:00 on its first day."""
    saved_event_request.end_date = date(2026, 10, 16)
    set_status(EventRequestStatus.CONFIRMED)
    evening_of_the_first_day = datetime(2026, 10, 15, 18, 0, tzinfo=SINGAPORE)

    with pytest.raises(RequestNotCompletableError) as exc_info:
        complete(COORDINATOR_ID, evening_of_the_first_day)

    _assert_not_completable(exc_info.value, NOT_YET_ENDED_MESSAGE)
    assert_nothing_changed(EventRequestStatus.CONFIRMED)


# --------------------------------------------------------------------------
# AC3 — only a confirmed event can be completed; a draft is never found
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", NOT_CONFIRMED_STATUSES, ids=lambda status: status.value)
def test_a_cancelled_rejected_or_otherwise_unconfirmed_event_cannot_be_completed(
    complete: Complete,
    set_status: SetStatus,
    assert_nothing_changed: AssertNothingChanged,
    status: EventRequestStatus,
) -> None:
    set_status(status)

    with pytest.raises(RequestNotCompletableError) as exc_info:
        complete(COORDINATOR_ID, AFTER_THE_END)

    _assert_not_completable(exc_info.value, NOT_CONFIRMED_MESSAGE)
    assert_nothing_changed(status)


def test_a_draft_is_not_found_by_its_coordinator(
    complete: Complete,
    set_status: SetStatus,
    assert_nothing_changed: AssertNothingChanged,
) -> None:
    """Staff never see a draft (ADR-0024): a 409 would say that one exists."""
    set_status(EventRequestStatus.DRAFT)

    with pytest.raises(NotFoundError) as exc_info:
        complete(COORDINATOR_ID, AFTER_THE_END)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(EventRequestStatus.DRAFT)


# --------------------------------------------------------------------------
# ADR-0027 — only the event's own coordinator, and the order of the checks
# --------------------------------------------------------------------------


def test_only_the_events_assigned_coordinator_may_complete_it(
    complete: Complete,
    confirmed_event_request: EventRequest,
    assert_nothing_changed: AssertNothingChanged,
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        complete(OTHER_COORDINATOR_ID, AFTER_THE_END)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(EventRequestStatus.CONFIRMED)


def test_an_unknown_reference_is_404(
    saved_users: list[User], assert_nothing_changed: AssertNothingChanged
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        complete_event_request(COORDINATOR_ID, "EVR-ZZZZZZZZ", now=AFTER_THE_END)

    assert exc_info.value.status_code == 404
    assert exc_info.value.message == EVENT_REQUEST_NOT_FOUND_MESSAGE
    assert_nothing_changed(EventRequestStatus.SUBMITTED)


def test_ownership_is_checked_before_status(complete: Complete, set_status: SetStatus) -> None:
    """Another coordinator learns no more about a cancelled event than an open one."""
    set_status(EventRequestStatus.CANCELLED)

    with pytest.raises(NotFoundError):
        complete(OTHER_COORDINATOR_ID, AFTER_THE_END)


def test_status_is_checked_before_the_end_time(complete: Complete) -> None:
    """A submitted event that hasn't ended is refused for its status, not its end."""
    with pytest.raises(RequestNotCompletableError) as exc_info:
        complete(COORDINATOR_ID, JUST_BEFORE_THE_END)

    _assert_not_completable(exc_info.value, NOT_CONFIRMED_MESSAGE)


# --------------------------------------------------------------------------
# AC5 — who completed the event and when, saved with the status
# --------------------------------------------------------------------------


def test_completing_records_who_did_it_and_when(
    complete: Complete, confirmed_event_request: EventRequest
) -> None:
    complete(COORDINATOR_ID, AFTER_THE_END)

    history = list_event_history(COORDINATOR_ID, REFERENCE, viewer_role=Role.EVENT_COORDINATOR)
    assert history == [
        HistoryEntryAsShown(
            kind=EventHistoryKind.EVENT_COMPLETED,
            occurred_at=AFTER_THE_END,
            actor_name="Coordinator Three",
            details={},
        )
    ]


def test_now_defaults_to_the_current_instant(
    saved_users: list[User],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    reload_event_request: ReloadEventRequest,
    db_session: Session,
) -> None:
    """An event long over, so the real clock is past its end whenever this runs."""
    long_over = make_event_request(
        reference="EVR-BBBBBBBB",
        status=EventRequestStatus.CONFIRMED,
        coordinator_id=COORDINATOR_ID,
        proposed_date=date(2020, 1, 1),
    )
    save(long_over)
    before = datetime.now(timezone.utc)

    complete_event_request(COORDINATOR_ID, "EVR-BBBBBBBB")

    after = datetime.now(timezone.utc)
    assert reload_event_request(long_over.id).status is EventRequestStatus.COMPLETED
    entry = db_session.scalars(select(EventHistoryEntry)).one()
    assert before <= entry.occurred_at <= after


def test_the_status_and_its_history_are_saved_in_one_commit(
    mock_session: MagicMock, make_event_request: Callable[..., EventRequest]
) -> None:
    """At the only commit, the status is set and the entry already added."""
    event_request = make_event_request(
        status=EventRequestStatus.CONFIRMED, coordinator_id=COORDINATOR_ID
    )
    mock_session.scalar.return_value = event_request
    seen_at_commit: list[tuple[EventRequestStatus, list[EventHistoryKind]]] = []

    def note_what_is_saved() -> None:
        added_kinds = [call.args[0].kind for call in mock_session.add.call_args_list]
        seen_at_commit.append((event_request.status, added_kinds))

    mock_session.commit.side_effect = note_what_is_saved

    complete_event_request(COORDINATOR_ID, REFERENCE, session=mock_session, now=AFTER_THE_END)

    assert seen_at_commit == [(EventRequestStatus.COMPLETED, [EventHistoryKind.EVENT_COMPLETED])]


# --------------------------------------------------------------------------
# AC4 — a completed event can no longer be edited (SCRUM-33's rule, ADR-0025)
# --------------------------------------------------------------------------


def test_a_completed_event_can_no_longer_be_edited(
    complete: Complete,
    confirmed_event_request: EventRequest,
    reload_event_request: ReloadEventRequest,
    today: date,
) -> None:
    """A regression guard: the refusal is SCRUM-33's, the status it refuses is ours."""
    complete(COORDINATOR_ID, AFTER_THE_END)

    with pytest.raises(RequestNotEditableError) as exc_info:
        update_event_request(COORDINATOR_ID, REFERENCE, {"description": "Late change"}, today=today)

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "request_not_editable")
    assert refused.message == NOT_EDITABLE_MESSAGE
    assert reload_event_request(confirmed_event_request.id).description is None
