"""Unit tests for SCRUM-57 AC9: a Pending change request holds up the event's decisions.

While a change request is Pending, the event can't be approved or rejected (SCRUM-31),
rejected during planning or confirmed (SCRUM-49), and the refusal tells the coordinator
to decide the change request first. It works like SCRUM-32 AC3's outstanding
clarification. Direct edits and asking for clarification are not held up. Each of the
four actions locks the event's row before it looks for a Pending request, so one raised
while it waited for the lock is seen (technical note, ADR-0127).

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7's, assigned to Event Coordinator 3). Before each action
the event is put in the status it needs, with the Safety Officer's approval and an
approved venue, so the only thing that could stop it is the change request.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, NamedTuple

import pytest
from sqlalchemy import Connection, insert
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.events.models import (
    ChangeRequestStatus,
    EventChangeRequest,
    EventHistoryKind,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    ChangeRequestPendingError,
    EventEdit,
    confirm_event_request,
    decide_event_request,
    reject_event_during_planning,
)
from app.modules.venue.models import BookingRequestStatus
from tests.events.cases import Arrange

pytestmark = pytest.mark.scrum_57

SaveChangeRequest = Callable[..., EventChangeRequest]
ReloadEventRequest = Callable[[int], EventRequest]
HistoryOf = Callable[[int], list[tuple[EventHistoryKind, int | None, dict[str, Any] | None]]]
DetailedNotificationsOf = Callable[[int], list[tuple[Any, ...]]]
OnEventRowLock = Callable[[Callable[[Connection], None]], None]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
COORDINATOR_ID = 3
PENDING_MESSAGE = (
    "The organiser has a change request waiting for your decision. Decide the change request first."
)


def _approve() -> EventRequest:
    return decide_event_request(COORDINATOR_ID, REFERENCE, {"outcome": "approved"})


def _reject() -> EventRequest:
    payload = {"outcome": "rejected", "reason": "No venue fits."}
    return decide_event_request(COORDINATOR_ID, REFERENCE, payload)


def _reject_during_planning() -> EventRequest:
    return reject_event_during_planning(COORDINATOR_ID, REFERENCE, {"reason": "No venue fits."})


def _confirm() -> EventRequest:
    return confirm_event_request(COORDINATOR_ID, REFERENCE)


class HeldUpAction(NamedTuple):
    """One of the event's decisions AC9 holds up, and the status it needs and leaves."""

    status_before: EventRequestStatus
    act: Callable[[], EventRequest]
    status_after: EventRequestStatus


HELD_UP_ACTIONS = [
    pytest.param(
        HeldUpAction(EventRequestStatus.UNDER_REVIEW, _approve, EventRequestStatus.APPROVED),
        id="approve",
    ),
    pytest.param(
        HeldUpAction(EventRequestStatus.UNDER_REVIEW, _reject, EventRequestStatus.REJECTED),
        id="reject",
    ),
    pytest.param(
        HeldUpAction(
            EventRequestStatus.APPROVED, _reject_during_planning, EventRequestStatus.REJECTED
        ),
        id="reject-during-planning",
    ),
    pytest.param(
        HeldUpAction(EventRequestStatus.SAFETY_REVIEW, _confirm, EventRequestStatus.CONFIRMED),
        id="confirm",
    ),
]
held_up_action = pytest.mark.parametrize("action", HELD_UP_ACTIONS)


@pytest.fixture()
def ready_for(
    saved_users: list[User],
    approved_for_safety: Callable[[EventRequestStatus], EventRequest],
    arrange: Arrange,
) -> Callable[[HeldUpAction], EventRequest]:
    """Put ``saved_event_request`` where ``action`` would go ahead, but for AC9."""

    def _ready(action: HeldUpAction) -> EventRequest:
        event_request = approved_for_safety(action.status_before)
        arrange(BookingRequestStatus.APPROVED)
        return event_request

    return _ready


def _assert_refused_and_nothing_changed(
    action: HeldUpAction,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    detailed_notifications_of: DetailedNotificationsOf,
    event_request: EventRequest,
) -> None:
    history_before = history_of(event_request.id)

    with pytest.raises(ChangeRequestPendingError) as exc_info:
        action.act()

    refused = exc_info.value
    assert (refused.status_code, refused.error_code) == (409, "change_request_pending")
    assert refused.message == PENDING_MESSAGE
    assert reload_event_request(event_request.id).status is action.status_before
    assert history_of(event_request.id) == history_before
    assert detailed_notifications_of(ORGANISER_ID) == []


# --------------------------------------------------------------------------
# AC9 — each of the four is refused while a change request is Pending
# --------------------------------------------------------------------------


@held_up_action
def test_the_action_is_refused_while_a_change_request_is_pending(
    ready_for: Callable[[HeldUpAction], EventRequest],
    save_change_request: SaveChangeRequest,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    detailed_notifications_of: DetailedNotificationsOf,
    action: HeldUpAction,
) -> None:
    event_request = ready_for(action)
    save_change_request(event_request)

    _assert_refused_and_nothing_changed(
        action, reload_event_request, history_of, detailed_notifications_of, event_request
    )


@held_up_action
def test_the_action_is_refused_when_a_request_is_raised_while_it_waits_for_the_lock(
    ready_for: Callable[[HeldUpAction], EventRequest],
    on_event_row_lock: OnEventRowLock,
    reload_event_request: ReloadEventRequest,
    history_of: HistoryOf,
    detailed_notifications_of: DetailedNotificationsOf,
    action: HeldUpAction,
) -> None:
    """Technical note: the request committed first, so it holds the action up."""
    event_request = ready_for(action)
    raised = insert(EventChangeRequest).values(
        event_request_id=event_request.id,
        requested_by=ORGANISER_ID,
        requested_values={"expected_attendance": 300},
        previous_values={"expected_attendance": 250},
        reason="More partners are coming.",
        status=ChangeRequestStatus.PENDING,
        raised_at=datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc),
    )
    on_event_row_lock(lambda connection: connection.execute(raised))

    _assert_refused_and_nothing_changed(
        action, reload_event_request, history_of, detailed_notifications_of, event_request
    )


@pytest.mark.parametrize(
    "status",
    [ChangeRequestStatus.APPROVED, ChangeRequestStatus.REJECTED, ChangeRequestStatus.WITHDRAWN],
    ids=lambda status: status.value,
)
@held_up_action
def test_a_decided_or_withdrawn_change_request_holds_nothing_up(
    ready_for: Callable[[HeldUpAction], EventRequest],
    save_change_request: SaveChangeRequest,
    reload_event_request: ReloadEventRequest,
    action: HeldUpAction,
    status: ChangeRequestStatus,
) -> None:
    event_request = ready_for(action)
    save_change_request(event_request, status)

    action.act()

    assert reload_event_request(event_request.id).status is action.status_after


@held_up_action
def test_another_events_pending_change_request_holds_nothing_up(
    ready_for: Callable[[HeldUpAction], EventRequest],
    make_event_request: Callable[..., EventRequest],
    save: Callable[..., None],
    save_change_request: SaveChangeRequest,
    reload_event_request: ReloadEventRequest,
    action: HeldUpAction,
) -> None:
    event_request = ready_for(action)
    other_event = make_event_request(reference="EVR-BBBBBBBB", coordinator_id=COORDINATOR_ID)
    save(other_event)
    save_change_request(other_event)

    action.act()

    assert reload_event_request(event_request.id).status is action.status_after


# --------------------------------------------------------------------------
# AC9 — direct edits and clarification are not held up
# --------------------------------------------------------------------------


def test_the_coordinator_can_still_edit_the_event_directly(
    edit_event: Callable[[int, dict[str, Any] | None], EventEdit],
    save_change_request: SaveChangeRequest,
    reload_event_request: ReloadEventRequest,
    approved_event_request: EventRequest,
) -> None:
    save_change_request(approved_event_request)

    edit_event(COORDINATOR_ID, {"expected_attendance": 120})

    assert reload_event_request(approved_event_request.id).expected_attendance == 120


def test_the_coordinator_can_still_ask_for_clarification(
    ask_clarification: Callable[[int, Any], EventRequest],
    save_change_request: SaveChangeRequest,
    reload_event_request: ReloadEventRequest,
    under_review_request: EventRequest,
    db_session: Session,
) -> None:
    save_change_request(under_review_request)

    ask_clarification(COORDINATOR_ID, {"message": "Which hall did you mean?"})

    assert (
        reload_event_request(under_review_request.id).status
        is EventRequestStatus.AWAITING_CLARIFICATION
    )
